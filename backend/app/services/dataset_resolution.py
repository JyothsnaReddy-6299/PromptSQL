"""Resolve owned dataset references once, before selecting relationship paths."""
import re
from itertools import combinations
from app.services.relationship_service import RelationshipError, DatasetChoice


def canonical_dataset(reference, datasets):
    matches = [d for d in datasets if str(reference).casefold() in
               {d['id'].casefold(), d['name'].casefold(), d['table_name'].casefold()}]
    if len(matches) != 1:
        raise RelationshipError(f"Dataset '{reference}' is unavailable, ambiguous or not owned by the authenticated user.")
    return matches[0]


def path_error(tables, all_rels, selected=None):
    related = [r for r in all_rels if r['left_table'] in tables or r['right_table'] in tables or r['id'] in (selected or [])]
    details = []
    for r in related:
        states = []
        if not r['approved']: states.append('unapproved')
        if not r['active']: states.append('inactive')
        if r['needs_revalidation']: states.append('stale: requires revalidation')
        if selected and r['id'] not in selected: states.append('not selected')
        details.append(f"{r['name']} [{r['id']}] {r['left_table']} <-> {r['right_table']}: {', '.join(states) or 'approved, active and fresh'}")
    error = RelationshipError('Resolved datasets: ' + ', '.join(tables) +
        '. No eligible approved relationship path connects these datasets. ' +
        ('Connections: ' + '; '.join(details) if details else 'Missing connection: no saved relationship touches these datasets.') +
        '. Create, activate or revalidate the required connection in Relationships.')
    error.resolved_datasets = tables
    return error


_GENERIC_DATASETS = {'orders', 'order', 'items', 'sales', 'data', 'table', 'records', 'customers'}
_SEMANTIC_WORDS = {'orders','order','sales','revenue','total','count','records','items','name','id','key'}


def mentions(question, term):
    matches = []
    for variant in {term.casefold(), term.casefold().replace('_', ' ')}:
        pattern = r'(?<![\w])' + re.escape(variant).replace(r'\ ', r'\s+') + r'(?![\w])'
        matches.extend(re.finditer(pattern, question, re.I))
    return matches


def field_term(name):
    """Compare identifier spelling, not MySQL value semantics or table names."""
    # Split BEFORE case-folding: OrderID/CustomerID/CustomerName retain word
    # boundaries which are lost in "orderid". Preserve plural acronym IDs too.
    name = re.sub(r'(?<=[a-z0-9])ID(s)?\b', r' Id\1', name)
    name = re.sub(r'(?<![A-Za-z0-9])IDs(?![A-Za-z0-9])', 'Ids', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    return ' '.join({'ids':'id','keys':'key'}.get(token,token)
                    for token in re.findall(r'[^\W_]+',name.casefold()))


def field_mentions(question, term):
    words = term.split()
    if not words: return False
    parts = [r'ids?' if word=='id' else r'keys?' if word=='key' else re.escape(word) for word in words]
    return bool(re.search(r'(?<!\w)' + r'[\s_]*'.join(parts) + r'(?!\w)',question,re.I))


def mask_filter_values(question, datasets):
    """Filter literals are values, even if another schema uses them as names."""
    fields = {field_term(c['name']) for d in datasets for c in d['columns']}
    spans = []
    for field in fields:
        parts = [r'ids?' if word=='id' else r'keys?' if word=='key' else re.escape(word) for word in field.split()]
        if not parts: continue
        pattern = (r'(?<!\w)' + r'[\s_]*'.join(parts) + r'(?!\w)\s*'
                   r'(?:is|equals?|equal to|=|like|contains)\s*'
                   r"""(?P<value>'[^']*'|"[^"]*"|[^\s,;.?!]+)""")
        spans.extend(match.span('value') for match in re.finditer(pattern,question,re.I))
    masked = list(question)
    for start,end in spans: masked[start:end] = ' '*(end-start)
    return ''.join(masked)


def source_affinity(dataset, required, coverage):
    # A field qualified by an entity ("order IDs") favors the matching dataset
    # entity ("orders"), when active context alone cannot answer the question.
    # Do not infer source dependencies from unrelated registered metrics.
    singular = lambda word: word[:-1] if len(word)>3 and word.endswith('s') and not word.endswith(('ss','us')) else word
    label = [singular(t) for t in field_term(dataset['name']).split()]
    score = 0
    for term in required & coverage:
        words = term.split()
        if len(words)>1 and words[-1] in {'id','key'}:
            entity = [singular(t) for t in words[:-1]]
            if label == entity: score += 2
            elif all(t in label for t in entity): score += 1
    return score


def select_datasets(question, active_reference, datasets, selected_ids=None, plan_is_eligible=None):
    active = canonical_dataset(active_reference, datasets)
    if selected_ids:
        return list(dict.fromkeys(canonical_dataset(ref, datasets)['table_name'] for ref in selected_ids))
    question = mask_filter_values(question,datasets)
    candidates, spans, explicit = [], [], []
    for d in datasets:
        for alias in {d['name'],d['table_name']}:
            for match in mentions(question,alias):
                prefix = question[max(0,match.start()-30):match.start()].casefold()
                quoted = match.start()>0 and question[match.start()-1] in '`"['
                if alias.casefold() in _GENERIC_DATASETS and not quoted:
                    named_context = re.search(r'(?:from|join|involving|dataset|table|with)\s+$',prefix)
                    conjunction_context = re.search(r'and\s+$',prefix) and re.search(r'\b(?:from|join|involving|datasets?|tables?)\b',question[:match.start()],re.I)
                    if not (named_context or conjunction_context): continue
                candidates.append((match.start(),match.end(),d))
    for start,end,d in sorted(candidates,key=lambda m:m[1]-m[0],reverse=True):
        if any(start<b and end>a for a,b in spans): continue
        spans.append((start,end)); explicit.append(d)
    explicit = list({d['id']:d for d in explicit}.values())
    anchor = bool(re.search(r'\b(?:this|active|current)\s+(?:table|dataset)\b',question,re.I))
    if anchor and active not in explicit: explicit.insert(0,active)
    if anchor and len(explicit)==1: return [active['table_name']]
    def columns(d):
        raw = {field_term(c['name']) for c in d['columns']}
        normalized = raw
        quantity = any(any(t in c.split() for t in ('quantity','qty','units')) for c in normalized)
        monetary = any(c in {'total sales','total sales amount','revenue','amount','sales amount'} for c in normalized)
        monetary |= quantity and any(c in {'unit price','price'} for c in normalized)
        concepts = {'region':any('region' in c.split() for c in normalized),
                    'quantity':quantity,'amount':monetary,'revenue':monetary}
        # Explicitly quoted columns retain literal schema semantics.
        return raw | {concept for concept,present in concepts.items() if present and not re.search(r'[`"\[]'+concept+r'[`"\]]',question,re.I)}
    coverage = {d['id']:columns(d) for d in datasets}
    active_cols = coverage[active['id']]
    mentioned = {field_term(c['name']) for d in datasets for c in d['columns']
                 if field_term(c['name']) not in _SEMANTIC_WORDS and field_mentions(question,field_term(c['name']))}
    providers = set().union(*coverage.values())
    mentioned |= {concept for concept in ('revenue','region','quantity','amount') if concept in providers and mentions(question,concept)}
    if not mentioned: return [d['table_name'] for d in explicit] if explicit else [active['table_name']]
    if not explicit and mentioned.issubset(active_cols): return [active['table_name']]
    fixed = explicit
    fixed_ids = {d['id'] for d in fixed}
    supplied = set().union(*(coverage[d['id']] for d in fixed)) if fixed else set()
    if fixed and mentioned.issubset(supplied): return [d['table_name'] for d in fixed]
    missing = mentioned-supplied
    candidates = [d for d in datasets if d['id'] not in fixed_ids and coverage[d['id']]&missing]
    options = []
    # Search inclusion-minimal covers, without making active context a mandatory
    # source. Actual bridge datasets are resolved by the approved graph later.
    for size in range(1,min(3,len(candidates))+1):
        for group in combinations(candidates,size):
            ids = {d['id'] for d in group}
            if any(extra_ids.issubset(ids) for extra_ids,_ in options): continue
            if missing.issubset(set().union(*(coverage[d['id']] for d in group))):
                options.append((ids,[*fixed,*group]))
    groups = [group for _,group in options]
    connected = [group for group in groups if plan_is_eligible and plan_is_eligible([d['table_name'] for d in group])]
    if connected:
        # Connectivity is evidence; the active UI dataset and an entity-name
        # score cannot silently choose between multiple executable meanings.
        groups = connected
    elif groups:
        # No eligible plan: retain the best semantic interpretation so final path
        # validation explains the missing/inactive/stale connection. Never execute it.
        scores = [sum(source_affinity(d,mentioned,coverage[d['id']]) for d in group) for group in groups]
        best = max(scores)
        groups = [group for group,score in zip(groups,scores) if score==best]
    if len(groups)>1:
        raise DatasetChoice([dict(id='datasets_'+str(i),label=' + '.join(d['name'] for d in group),description='These datasets supply the requested columns, filters and metrics.',dataset_ids=[d['id'] for d in group]) for i,group in enumerate(groups[:12])])
    return [d['table_name'] for d in groups[0]] if groups else [d['table_name'] for d in fixed] if fixed else [active['table_name']]
