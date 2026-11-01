"""Relationship catalog, exact SQL key profiling, approval and freshness checks."""
import hashlib
import json
import uuid
from functools import wraps
from sqlalchemy import inspect, text
from app.database.connection import engine, SessionLocal
from app.models.relationship import DatasetReference, DatasetRelationship
from app.utils.tz_helper import get_ist_time

class RelationshipError(ValueError):
    pass

class RelationshipChoice(RelationshipError):
    def __init__(self, options):
        super().__init__('Multiple approved relationship paths have different meanings. Choose one.')
        self.options = options

def quote(name):
    return '`' + name.replace('`', '``') + '`'

def schema(name):
    return [{'name': c['name'], 'type': str(c['type'])} for c in inspect(engine).get_columns(name)]

def fingerprint(name):
    return hashlib.sha256(json.dumps(schema(name), sort_keys=True).encode()).hexdigest()

def catalog(owner):
    # Legacy datasets have no owner table: import only existing user-suffixed
    # tables from the server inspector, never a client-provided physical name.
    tables = [t for t in inspect(engine).get_table_names() if t.endswith('_' + owner)]
    descriptions = {table: schema(table) for table in tables}
    fingerprints = {table: hashlib.sha256(json.dumps(descriptions[table], sort_keys=True).encode()).hexdigest() for table in tables}
    with SessionLocal() as db:
        for table in tables:
            item = db.query(DatasetReference).filter_by(physical_name=table).first()
            fp = fingerprints[table]
            if not item:
                db.add(DatasetReference(id=uuid.uuid4().hex, owner_id=owner,
                    physical_name=table, label=table.rsplit('_' + owner, 1)[0], schema_fingerprint=fp))
            elif item.owner_id == owner and item.schema_fingerprint != fp:
                item.schema_fingerprint = fp
                item.revision += 1
                item.updated_at = get_ist_time()
                _mark(db, item.id)
        db.commit()
        return [{'id': d.id, 'name': d.label, 'table_name': d.physical_name,
                 'revision': d.revision, 'columns': descriptions[d.physical_name]}
                for d in db.query(DatasetReference).filter_by(owner_id=owner).all()
                if d.physical_name in tables]

def owned(db, dataset_id, owner):
    item = db.query(DatasetReference).filter_by(id=dataset_id, owner_id=owner).first()
    if not item or item.physical_name not in inspect(engine).get_table_names():
        raise RelationshipError('Dataset not found or access denied.')
    return item

def _mark(db, dataset_id):
    for rel in db.query(DatasetRelationship).filter(
        (DatasetRelationship.left_dataset_id == dataset_id) | (DatasetRelationship.right_dataset_id == dataset_id)).all():
        rel.needs_revalidation = True
        rel.updated_at = get_ist_time()

def invalidate_dataset(table_name):
    # No catalog before migration is also valid for old standalone test fixtures.
    if not inspect(engine).has_table('dataset_references'):
        return
    with SessionLocal() as db:
        item = db.query(DatasetReference).filter_by(physical_name=table_name).first()
        if item:
            item.revision += 1
            item.updated_at = get_ist_time()
            _mark(db, item.id)
            db.commit()

def track_changes(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        import inspect as python_inspect
        bound = python_inspect.signature(fn).bind_partial(*args, **kwargs)
        ctx = bound.arguments.get('ctx')
        if ctx:
            invalidate_dataset(ctx.table_name)
        return fn(*args, **kwargs)
    return wrapped

def family(type_name):
    t = type_name.lower()
    if any(x in t for x in ['char', 'text']): return 'text'
    if any(x in t for x in ['int', 'decimal', 'numeric', 'float', 'double', 'real']): return 'number'
    if any(x in t for x in ['date', 'time']): return 'date'
    return t

def profile(left, right, keys, join_type='INNER'):
    if left == right or join_type not in ('INNER', 'LEFT') or not keys or len(keys) > 8:
        raise RelationshipError('Choose two different datasets, 1–8 key mappings and INNER or LEFT.')
    cols = [{c['name']: c['type'] for c in schema(t)} for t in (left, right)]
    if len({k['left'] for k in keys}) != len(keys) or len({k['right'] for k in keys}) != len(keys):
        raise RelationshipError('Join keys must not be repeated.')
    for k in keys:
        if k['left'] not in cols[0] or k['right'] not in cols[1]:
            raise RelationshipError('A join column is missing from the dataset schema.')
        if family(cols[0][k['left']]) != family(cols[1][k['right']]):
            raise RelationshipError('Incompatible key types. Convert explicitly before approval; identifiers are never cast automatically.')
    groups = []
    stats = []
    with engine.connect() as conn:
        for side, table in enumerate((left, right)):
            names = [k['left' if side == 0 else 'right'] for k in keys]
            complete = ' AND '.join(f'{quote(c)} IS NOT NULL' for c in names)
            fields = ', '.join(f'{quote(c)} AS k{i}' for i, c in enumerate(names))
            grouping = ', '.join(quote(c) for c in names)
            grouped = f'SELECT {fields}, COUNT(*) AS n FROM {quote(table)} WHERE {complete} GROUP BY {grouping}'
            groups.append(grouped)
            total = int(conn.execute(text(f'SELECT COUNT(*) FROM {quote(table)}')).scalar())
            row = conn.execute(text(f'SELECT COUNT(*), COALESCE(SUM(n),0), COALESCE(SUM(CASE WHEN n>1 THEN 1 ELSE 0 END),0), COALESCE(MAX(n),0) FROM ({grouped}) g')).first()
            distinct, complete_rows, duplicate_keys, max_frequency = map(int, row)
            stats.append(dict(total_records=total, incomplete_key_records=total-complete_rows,
                complete_key_records=complete_rows, distinct_complete_keys=distinct,
                duplicate_key_groups=duplicate_keys, excess_duplicate_records=complete_rows-distinct,
                maximum_key_frequency=max_frequency))
        on = ' AND '.join(f'l.k{i} = r.k{i}' for i in range(len(keys)))
        row = conn.execute(text(f'SELECT COALESCE(SUM(l.n),0), COALESCE(SUM(r.n),0), COALESCE(SUM(l.n*r.n),0) FROM ({groups[0]}) l INNER JOIN ({groups[1]}) r ON {on}')).first()
        lm, rm, inner_rows = map(int, row)
    for st, matched in zip(stats, (lm, rm)):
        st['matched_source_records'] = matched
        st['unmatched_source_records'] = st['total_records'] - matched
    cardinality = ('many' if stats[0]['maximum_key_frequency'] > 1 else 'one') + '-to-' + ('many' if stats[1]['maximum_key_frequency'] > 1 else 'one')
    joined = inner_rows + (stats[0]['unmatched_source_records'] if join_type == 'LEFT' else 0)
    return dict(left=stats[0], right=stats[1], cardinality=cardinality,
        expected_inner_join_records=inner_rows, expected_join_records=joined,
        expansion_per_left_record=joined / stats[0]['total_records'] if stats[0]['total_records'] else 0,
        measured_at=get_ist_time().isoformat(),
        semantics='Counts use complete non-NULL composite keys and database equality/collation. Blank text is a value. Unmatched includes incomplete keys; LEFT preserves those left records. Duplicate groups count keys with frequency >1; excess counts records beyond the first.')

def serialize(rel, db):
    left = db.get(DatasetReference, rel.left_dataset_id)
    right = db.get(DatasetReference, rel.right_dataset_id)
    stale = rel.needs_revalidation
    for d in (left, right):
        if not d or d.physical_name not in inspect(engine).get_table_names(): stale = True
        elif fingerprint(d.physical_name) != d.schema_fingerprint: stale = True
    versions = json.loads(rel.versions_json)
    if left and versions.get(left.id) != left.revision: stale = True
    if right and versions.get(right.id) != right.revision: stale = True
    return dict(id=rel.id, name=rel.name, left_dataset_id=rel.left_dataset_id,
        right_dataset_id=rel.right_dataset_id, left_table=left.physical_name if left else '',
        right_table=right.physical_name if right else '', keys=json.loads(rel.keys_json),
        join_type=rel.join_type, profile=json.loads(rel.profile_json), versions=versions,
        approved=rel.approved, active=rel.active, needs_revalidation=stale,
        created_at=rel.created_at.isoformat(), updated_at=rel.updated_at.isoformat())

def relationships(owner):
    with SessionLocal() as db:
        return [serialize(r, db) for r in db.query(DatasetRelationship).filter_by(owner_id=owner).all()]

def save(owner, data, relationship_id=None):
    with SessionLocal() as db:
        left = owned(db, data['left_dataset_id'], owner)
        right = owned(db, data['right_dataset_id'], owner)
        measured = profile(left.physical_name, right.physical_name, data['keys'], data['join_type'])
        if not data.get('approved'):
            raise RelationshipError('Explicit approval of the measured relationship is required.')
        rel = db.query(DatasetRelationship).filter_by(id=relationship_id, owner_id=owner).first() if relationship_id else DatasetRelationship(id=uuid.uuid4().hex, owner_id=owner)
        if not rel: raise RelationshipError('Relationship not found or access denied.')
        for d in (left, right):
            d.schema_fingerprint = fingerprint(d.physical_name)
        rel.name = data['name'].strip() or 'Approved relationship'
        rel.left_dataset_id, rel.right_dataset_id = left.id, right.id
        rel.keys_json = json.dumps(data['keys'])
        rel.join_type = data['join_type']
        rel.profile_json = json.dumps(measured)
        rel.versions_json = json.dumps({left.id: left.revision, right.id: right.revision})
        rel.approved, rel.active, rel.needs_revalidation = True, data.get('active', True), False
        rel.updated_at = get_ist_time()
        db.add(rel)
        db.commit()
        return serialize(rel, db)

def resolve_paths(owner, tables, selected=None):
    rels = [r for r in relationships(owner) if r['active'] and r['approved'] and not r['needs_revalidation']]
    if selected:
        rels = [r for r in rels if r['id'] in selected]
        if len(rels) != len(set(selected)): raise RelationshipError('Selected relationships are unavailable or require revalidation.')
    if len(tables) < 2: return rels
    paths = []
    def visit(at, edges, visited):
        if set(tables).issubset(visited):
            paths.append(edges); return
        if len(edges) >= 4: return
        for rel in rels:
            a,b = rel['left_table'],rel['right_table']
            nxt = b if at == a else a if at == b else None
            if nxt and nxt not in visited: visit(nxt, edges+[rel], visited|{nxt})
    visit(tables[0], [], {tables[0]})
    unique = {tuple(r['id'] for r in p): p for p in paths}
    paths = list(unique.values())
    if not paths: raise RelationshipError('No active approved relationship path connects these datasets. Create or revalidate it in Relationships first.')
    if len(paths) > 1:
        raise RelationshipChoice([dict(id='path_'+str(i), label=' → '.join(r['name'] for r in p), description='; '.join(str(r['keys']) for r in p), relationship_ids=[r['id'] for r in p]) for i,p in enumerate(paths)])
    return paths[0]

def query_context(owner, question, active_table, selected=None):
    datasets = catalog(owner)
    required = [active_table]
    for d in datasets:
        import re
        label = d['name'].replace('_', ' ')
        if d['table_name'] != active_table and (re.search(r'\b'+re.escape(label)+r'\b', question.replace('_',' '), re.I) or any(c['name'].lower() in question.lower() for c in d['columns'] if len(c['name']) > 5 and not any(c['name'] == a['name'] for ds in datasets if ds['table_name']==active_table for a in ds['columns']))):
            required.append(d['table_name'])
    return required, resolve_paths(owner, required, selected) if len(required)>1 else []
