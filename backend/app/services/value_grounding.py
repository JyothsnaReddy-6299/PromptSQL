"""Bind mentioned literals to measured owned values, not guessed identifiers."""
import hashlib
import json
import re
from collections import defaultdict
from sqlalchemy import inspect, text, bindparam
import sqlglot
from sqlglot import exp
from app.services import relationship_service as service
from app.services.dataset_resolution import field_term, canonical_dataset

class ValueChoice(service.RelationshipError):
    def __init__(self, options):
        super().__init__('This value matches multiple fields or records. Which meaning should the query use?')
        self.options = options

class GroundingError(ValueError):
    pass

# Language scaffolding is not evidence of a data value. Quoted literals are still
# eligible; there are no person names, dataset names or physical columns here.
FUNCTION_WORDS = set('a an the me show give get list find what which who whose did does is are was were be been by from of to for with in on and or all this that table dataset name names id ids key keys total highest lowest revenue sales average count'.split())
MAX_WORDS = 6

def key(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()[:24]

def occurrences(question, field):
    words = field_term(field).split()
    parts = [r'ids?' if w=='id' else r'keys?' if w=='key' else re.escape(w) for w in words]
    return list(re.finditer(r'(?<!\w)'+r'[\s_]*'.join(parts)+r'(?!\w)',question,re.I)) if parts else []

def literal_spans(question, datasets):
    protected = []
    for d in datasets:
        for name in [d['name'],d['table_name'],*[c['name'] for c in d['columns']]]:
            protected.extend(m.span() for m in occurrences(question,name))
    words = list(re.finditer(r"[^\W_]+(?:['’\-][^\W_]+)*",question,re.UNICODE))
    values = defaultdict(list)
    for start in range(len(words)):
        for end in range(start,min(len(words),start+MAX_WORDS)):
            a,b=words[start].start(),words[end].end()
            value=question[a:b]
            if end>start and not re.fullmatch(r'\s+',question[words[end-1].end():words[end].start()]): break
            quoted = a>0 and question[a-1] in '\"\''
            if any(a<x[1] and b>x[0] for x in protected) and not quoted: continue
            if not any(c.isalpha() for c in value): continue
            if value.casefold() in FUNCTION_WORDS and not quoted: continue
            values[value.casefold()].append((a,b))
    return values

def explicitly_bound(question,column,spans):
    for field in occurrences(question,column):
        for start,_ in spans:
            if field.end()<=start and re.fullmatch(r"\s*(?:(?:is|equals?|equal to|=)\s*)?['\"]?",question[field.end():start],re.I):
                return True
    return False

def resolve_values(owner,question,active_reference,choices=None):
    datasets=service.catalog(owner)
    active=canonical_dataset(active_reference,datasets)['table_name']
    spans=literal_spans(question,datasets)
    if not spans: return []
    choices=choices or {}
    rels=[r for r in service.relationships(owner) if r['approved'] and r['active'] and not r['needs_revalidation']]
    # Equality domains are defined only by eligible user-approved keys.
    adjacency=defaultdict(set)
    identities=defaultdict(set)
    for r in rels:
        for k in r['keys']:
            a=(r['left_table'],k['left']); b=(r['right_table'],k['right'])
            adjacency[a].add(b);adjacency[b].add(a)
            identities[a[0]].add(a[1]);identities[b[0]].add(b[1])
    for d in datasets:
        identities[d['table_name']].update(inspect(service.engine).get_pk_constraint(d['table_name']).get('constrained_columns',[]))
    matches=defaultdict(list)
    with service.engine.connect() as conn:
        for d in datasets:
            table=d['table_name']
            for col in d['columns']:
                # Text lookup never coerces a person's name into numeric ID zero.
                if service.family(col['type'])!='text': continue
                column=col['name']
                query=text(f'SELECT DISTINCT {service.quote(column)} FROM {service.quote(table)} WHERE LOWER({service.quote(column)}) IN :values LIMIT 65').bindparams(bindparam('values',expanding=True))
                rows=conn.execute(query,{'values':list(spans)}).all()
                if len(rows)>64: raise GroundingError('Too many matching values; use a more specific question.')
                for row in rows:
                    value=row[0]
                    if value is None or str(value).casefold() not in spans: continue
                    normalized=str(value).casefold()
                    role='identifier' if column in identities[table] else 'attribute'
                    binding=dict(table=table,column=column,value=str(value),role=role)
                    matches[normalized].append(dict(filters=[binding],explicit=explicitly_bound(question,column,spans[normalized]),label=f'{d["name"]}.{column}',alternatives=[binding]))
    # A full stored value takes precedence over an overlapping shorter value.
    occupied=[]; selected_values=[]
    for value in sorted(matches,key=len,reverse=True):
        free=[(a,b) for a,b in spans[value] if not any(a<y and b>x for x,y in occupied)]
        if free: selected_values.append(value);occupied.extend(free)
    result=[]
    for value in selected_values:
        candidates=matches[value]
        explicit=[c for c in candidates if c['explicit']]
        if explicit: candidates=explicit
        # Collapse equivalent key references, not distinct name-vs-ID meanings.
        merged=[]
        for candidate in candidates:
            binding=candidate['filters'][0]
            equivalent=set(); pending=[(binding['table'],binding['column'])]
            while pending:
                node=pending.pop()
                if node in equivalent: continue
                equivalent.add(node);pending.extend(adjacency[node]-equivalent)
            prior=next((c for c in merged if (c['filters'][0]['table'],c['filters'][0]['column']) in equivalent),None)
            if prior:
                prior['alternatives']+=candidate['alternatives']
                if binding['table']==active:
                    prior['filters']=candidate['filters'];prior['label']=candidate['label']
            else: merged.append(candidate)
        candidates=merged
        eligible=[]
        for candidate in candidates:
            try:
                service.query_context(owner,question,active,filter_bindings=candidate['filters'])
                eligible.append(candidate)
            except (service.DatasetChoice,service.RelationshipChoice):
                eligible.append(candidate)
            except service.RelationshipError:
                pass
        if eligible: candidates=eligible
        # A bare attribute matching different identifiable records needs a choice.
        expanded=[]
        for candidate in candidates:
            binding=candidate['filters'][0]
            ids=sorted(identities[binding['table']]-{binding['column']})
            if not candidate['explicit'] and binding['role']=='attribute' and ids:
                with service.engine.connect() as conn:
                    sql=text(f'SELECT DISTINCT {", ".join(service.quote(c) for c in ids)} FROM {service.quote(binding["table"])} WHERE {service.quote(binding["column"])} = :value LIMIT 13')
                    records=conn.execute(sql,{'value':binding['value']}).all()
                if len(records)>1:
                    candidate=dict(candidate,label=candidate['label']+' (all matching records)')
                    expanded.append(candidate)
                    for row in records[:12]:
                        identity=[dict(table=binding['table'],column=c,value=str(v),role='identifier') for c,v in zip(ids,row) if v is not None]
                        if len(identity)==len(ids):
                            expanded.append(dict(filters=[binding,*identity],alternatives=candidate['alternatives'],explicit=False,label=candidate['label'].split(' (all')[0]+'; '+', '.join(f'{c}={v}' for c,v in zip(ids,row))))
                    continue
            expanded.append(candidate)
        candidates=expanded
        for c in candidates: c['id']=key(c['filters'])
        selected=next((c for c in candidates if c['id']==choices.get(key(value))),None)
        if choices.get(key(value)) and selected is None:
            raise GroundingError('The selected value meaning is no longer available. Ask again.')
        if selected is None and len(candidates)>1:
            raise ValueChoice([dict(id=c['id'],label=c['label'],description='Measured value '+repr(c['filters'][0]['value'])+'; '+c['filters'][0]['role'],value_choices={**choices,key(value):c['id']}) for c in candidates])
        selected=selected or candidates[0]
        for binding in selected['filters']:
            result.append(dict(binding,alternatives=selected['alternatives'] if binding==selected['filters'][0] else [binding]))
    return result

def grounding_prompt(bindings):
    return ('\nMEASURED FILTER BINDINGS (use these exact dataset/column/value meanings; do not move names onto keys):\n'+json.dumps(bindings,ensure_ascii=False)+'\nUse every binding as a filter. Approved join key mappings determine joins; generic primary keys do not.\n') if bindings else ''

def validate_bindings(sql,bindings):
    """Reject syntactically valid SQL which filters the wrong semantic field."""
    if not bindings: return sql
    tree=sqlglot.parse_one(sql,read='mysql')
    tables=list(tree.find_all(exp.Table))
    aliases={t.alias_or_name.casefold():t.name for t in tables}
    where=tree.args.get('where')
    if where is None: raise GroundingError('The query omitted its measured value filters.'+grounding_prompt(bindings))
    groups=defaultdict(list)
    for b in bindings: groups[(b['table'],b['column'])].append(b)
    for (_,column),group in groups.items():
        expected={b['value'].casefold() for b in group}
        alternatives={(a['table'].casefold(),a['column'].casefold()) for b in group for a in b.get('alternatives',[b])}
        def target(node):
            if isinstance(node,exp.Lower): node=node.this
            if not isinstance(node,exp.Column): return False
            source=aliases.get(node.table.casefold()) if node.table else tables[0].name if len(tables)==1 else None
            return source is not None and (source.casefold(),node.name.casefold()) in alternatives
        def values(node):
            if isinstance(node,exp.Paren): return values(node.this)
            if isinstance(node,exp.And):
                left,right=values(node.left),values(node.right)
                return left if expected.issubset(left) else right
            if isinstance(node,exp.Or):
                left,right=values(node.left),values(node.right)
                return left|right if left and right else set()
            if isinstance(node,exp.EQ):
                col,lit=(node.left,node.right) if target(node.left) else (node.right,node.left)
                literals=[lit] if target(col) else []
            elif isinstance(node,exp.In) and target(node.this): literals=node.expressions
            else: return set()
            if not literals or any(not isinstance(l,exp.Literal) for l in literals): return set()
            found={str(l.this).casefold() for l in literals}
            if not found.issubset(expected): return set()
            for literal in literals:
                actual=next(b['value'] for b in group if b['value'].casefold()==str(literal.this).casefold())
                # Preserve a case-sensitive database's actual spelling. LOWER uses lower-case.
                lower=isinstance(col,exp.Lower) if isinstance(node,exp.EQ) else isinstance(node.this,exp.Lower)
                literal.replace(exp.Literal.string(actual.lower() if lower else actual))
            return found
        if not expected.issubset(values(where.this)):
            raise GroundingError(f'The requested value belongs to {group[0]["table"]}.{column}, not a guessed identifier; its filter is missing, mismatched or bypassed.'+grounding_prompt(group))
    return tree.sql(dialect='mysql')
