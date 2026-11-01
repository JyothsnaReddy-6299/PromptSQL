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


def select_datasets(question, active_reference, datasets, selected_ids=None):
    active = canonical_dataset(active_reference, datasets)
    if selected_ids:
        return list(dict.fromkeys(canonical_dataset(ref, datasets)['table_name'] for ref in selected_ids))
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
    if explicit:
        if anchor and active not in explicit: explicit.insert(0,active)
        return [d['table_name'] for d in explicit]
    if anchor: return [active['table_name']]
    def columns(d):
        raw = {c['name'].casefold() for c in d['columns']}
        normalized = {c.replace('_',' ') for c in raw}
        quantity = any(any(t in c.split() for t in ('quantity','qty','units')) for c in normalized)
        monetary = any(c in {'total sales','total sales amount','revenue','amount','sales amount'} for c in normalized)
        monetary |= quantity and any(c in {'unit price','price'} for c in normalized)
        concepts = {'region':any('region' in c.split() for c in normalized),
                    'quantity':quantity,'amount':monetary,'revenue':monetary}
        # Explicitly quoted columns retain literal schema semantics.
        return raw | {concept for concept,present in concepts.items() if present and not re.search(r'[`"\[]'+concept+r'[`"\]]',question,re.I)}
    active_cols = columns(active)
    mentioned = {c['name'].casefold() for d in datasets for c in d['columns']
                 if c['name'].casefold() not in _SEMANTIC_WORDS and mentions(question,c['name'])}
    providers = set().union(*(columns(d) for d in datasets))
    mentioned |= {concept for concept in ('revenue','region','quantity','amount') if concept in providers and mentions(question,concept)}
    missing = mentioned-active_cols
    if not missing: return [active['table_name']]
    # Prefer one dataset that can answer all referenced fields, otherwise minimal
    # combinations with the active dataset. Never select every available schema.
    options = [[d] for d in datasets if mentioned.issubset(columns(d))] if not active_cols&mentioned else []
    if not options:
        others = [d for d in datasets if d['id']!=active['id'] and columns(d)&missing]
        for size in range(1,min(3,len(others))+1):
            for group in combinations(others,size):
                if missing.issubset(set().union(*(columns(d) for d in group))): options.append([active,*group])
            if options: break
    if len(options)>1:
        raise DatasetChoice([dict(id='datasets_'+str(i),label=' + '.join(d['name'] for d in group),description='Use these datasets for the referenced columns.',dataset_ids=[d['id'] for d in group]) for i,group in enumerate(options[:12])])
    return [d['table_name'] for d in options[0]] if options else [active['table_name']]
