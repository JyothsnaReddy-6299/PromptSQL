"""Validate join meaning and metric grain on the existing SQL execution path."""
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlalchemy import inspect
from app.services import relationship_service as service


def guard_query(sql, owner, selected=None, required_tables=None):
    tree = sqlglot.parse_one(sql, read='mysql')
    tables = list(dict.fromkeys(t.name for t in tree.find_all(exp.Table)))
    # Single-dataset CTEs need no relationship and retain existing behavior.
    physical = {d['table_name'] for d in service.catalog(owner)}
    used = [t for t in tables if t in physical]
    from sqlglot.optimizer.scope import traverse_scope
    actual_sources = [src for scope in traverse_scope(tree) for src in scope.sources.values() if isinstance(src, exp.Table)]
    if any(src.name not in physical or src.db or src.catalog for src in actual_sources):
        raise service.RelationshipError('A query dataset is not owned by the authenticated user.')
    if required_tables and not set(required_tables).issubset(used):
        raise service.RelationshipError('Generated SQL omitted a required dataset. Rephrase the question with the required metric source and dataset names.')
    if len(used) < 2:
        # Multiple occurrences (self joins) can also multiply a metric.
        if sum(t.name in physical for t in tree.find_all(exp.Table)) > 1:
            raise service.RelationshipError('Self joins require an explicit grain strategy and are not supported yet.')
        return sql, None
    if any(t not in physical for t in tables):
        raise service.RelationshipError('Multi-dataset CTEs/subqueries require an explicit grain strategy; use a direct approved join.')
    path = service.resolve_paths(owner, used, selected)
    if not isinstance(tree, exp.Select) or any(isinstance(n, (exp.Subquery, exp.CTE, exp.Union, exp.Window)) for n in tree.walk()):
        raise service.RelationshipError('Nested or windowed multi-dataset analysis is not supported safely yet.')
    # Resolve unqualified columns before measuring ownership of expressions.
    schema = {t: {c['name']: 'UNKNOWN' for c in inspect(service.engine).get_columns(t)} for t in used}
    raw_sources = {t.alias_or_name.lower(): t.name for t in tree.find_all(exp.Table)}
    for col in tree.find_all(exp.Column):
        source_tables = [raw_sources[col.table.lower()]] if col.table.lower() in raw_sources else used
        candidates = [(t,c) for t in source_tables for c in schema[t] if c.lower() == col.name.lower()]
        if len(candidates) == 1:
            col.set('this', exp.to_identifier(candidates[0][1], quoted=True))
        elif len(candidates) > 1 and not col.table:
            raise service.RelationshipError('Qualify an ambiguous column with its dataset alias.')
    tree = qualify(tree, dialect='mysql', schema=schema, expand_stars=True, validate_qualify_columns=True)
    sources = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    if len(sources) != len(used):
        raise service.RelationshipError('Repeated dataset joins require an explicit grain strategy.')
    joins = tree.args.get('joins', [])
    if len(joins) != len(used)-1:
        raise service.RelationshipError('Every dataset must be connected by an approved equality join.')
    verified = []
    joined_tables = {tree.args['from_'].this.name}
    for join in joins:
        right = join.this
        if not isinstance(right, exp.Table): raise service.RelationshipError('Only direct dataset joins are supported.')
        kind = 'LEFT' if join.side.upper() == 'LEFT' else 'INNER'
        if join.side.upper() not in ('', 'LEFT') or join.kind.upper() not in ('', 'INNER', 'OUTER') or not join.args.get('on'):
            raise service.RelationshipError('Only INNER and LEFT equality joins are supported.')
        if join.kind.upper() == 'OUTER' and kind != 'LEFT': raise service.RelationshipError('Unsupported join type.')
        condition = join.args['on']
        predicates = list(condition.flatten()) if isinstance(condition, exp.And) else [condition]
        mappings = []
        for predicate in predicates:
            if not isinstance(predicate, exp.EQ) or not isinstance(predicate.left, exp.Column) or not isinstance(predicate.right, exp.Column):
                raise service.RelationshipError('Join conditions must consist only of approved column equalities.')
            a,b = predicate.left, predicate.right
            mappings.append(((sources.get(a.table), a.name), (sources.get(b.table), b.name)))
        candidates = []
        for rel in path:
            expected = {frozenset(((rel['left_table'],k['left']), (rel['right_table'],k['right']))) for k in rel['keys']}
            actual = {frozenset(pair) for pair in mappings}
            if expected == actual and len(mappings) == len(rel['keys']): candidates.append(rel)
        if len(candidates) != 1: raise service.RelationshipError('SQL join keys do not match the selected approved relationship.')
        rel = candidates[0]
        if rel['join_type'] != kind: raise service.RelationshipError('SQL join type differs from the approved relationship.')
        if kind == 'LEFT' and (right.name != rel['right_table'] or rel['left_table'] not in joined_tables):
            raise service.RelationshipError('LEFT joins must preserve the approved left dataset.')
        other = rel['left_table'] if right.name == rel['right_table'] else rel['right_table']
        if other not in joined_tables: raise service.RelationshipError('Join path is disconnected.')
        # Re-profile at execution: SQL success cannot establish cardinality.
        measured = service.profile(rel['left_table'], rel['right_table'], rel['keys'], rel['join_type'])
        rel = dict(rel, profile=measured)
        verified.append((join, rel))
        joined_tables.add(right.name)
    aggregates = list(tree.find_all(exp.AggFunc))
    metrics = []
    preaggregation = []
    for agg in aggregates:
        if isinstance(agg.this, exp.Distinct):
            raise service.RelationshipError('DISTINCT aggregates across datasets need explicit metric semantics; SUM(DISTINCT amount) is not a fanout fix.')
        owners = {sources.get(c.table) for c in agg.find_all(exp.Column)}
        if len(owners) != 1 or None in owners:
            raise service.RelationshipError('Specify a metric from one source dataset, for example SUM(orders.amount) or COUNT(items.item_id), instead of COUNT(*).')
        source = next(iter(owners))
        if not isinstance(agg, (exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Count)):
            raise service.RelationshipError('This cross-dataset aggregation is not supported safely yet.')
        metrics.append(dict(source=source, expression=agg.sql(dialect='mysql'), grain='One original record in '+source, ownership='Dataset owning the aggregate input columns'))
    metric_sources = {m['source'] for m in metrics}
    for join, rel in verified:
        a,b = rel['left_table'],rel['right_table']
        for source in metric_sources:
            if source not in (a,b):
                # For multi-hop aggregates, every edge must be one-to-one.
                if rel['profile']['cardinality'] != 'one-to-one':
                    raise service.RelationshipError('Multi-hop fanout aggregation requires an explicit source-grain plan.')
                continue
            other = b if source == a else a
            side = 'right' if other == b else 'left'
            if rel['profile'][side]['maximum_key_frequency'] <= 1: continue
            # MIN/MAX alone are duplicate invariant, but SUM/AVG/COUNT are not.
            sensitive = [agg for agg in aggregates if isinstance(agg, (exp.Sum, exp.Avg, exp.Count)) and any(sources.get(c.table)==source for c in agg.find_all(exp.Column))]
            if not sensitive: continue
            if len(joins) != 1 or len(metric_sources) != 1:
                raise service.RelationshipError('Multiple source grains would be repeated by this join. Separate the metrics or pre-aggregate each source explicitly.')
            aliases = [alias for alias,t in sources.items() if t == other]
            other_alias = aliases[0]
            # Reduction is valid only when the detail side supplies membership,
            # not selected dimensions, values, or predicates.
            for col in tree.find_all(exp.Column):
                if col.table == other_alias and col.find_ancestor(exp.Join) is None:
                    raise service.RelationshipError('A detail dimension or filter would repeat this source metric. Choose a detail-level metric or an explicit allocation rule.')
            if join.this.name != other:
                raise service.RelationshipError('Place the metric source first, then join the detail dataset; reverse fanout reduction is not supported.')
            key_names = [k['right' if other == b else 'left'] for k in rel['keys']]
            # GROUP BY keys pre-aggregates detail membership; it does not dedup amounts.
            reduction = exp.select(*[exp.column(k, quoted=True) for k in key_names]).from_(exp.to_table(other, quoted=True)).group_by(*[exp.column(k, quoted=True) for k in key_names])
            join.set('this', exp.Subquery(this=reduction, alias=exp.TableAlias(this=exp.to_identifier(other_alias, quoted=True))))
            preaggregation.append(dict(dataset=other, keys=key_names, strategy='Group detail records to one record per complete join key before joining the metric source.'))
    warnings = []
    for _,rel in verified:
        for side in ('left','right'):
            n = rel['profile'][side]['unmatched_source_records']
            if n: warnings.append(f"{rel[side+'_table']}: {n} unmatched source records (including incomplete keys); {rel['join_type']} semantics apply.")
    explanation = dict(datasets=used, relationships=[dict(id=r['id'], name=r['name'], left_dataset=r['left_table'], right_dataset=r['right_table'], keys=r['keys'], join_type=r['join_type'], cardinality=r['profile']['cardinality'], profile=r['profile']) for _,r in verified], metrics=metrics, preaggregation=preaggregation, warnings=warnings, verification='User-approved analytical relationship, not an inferred or verified database foreign key.', freshness='Schema fingerprints and application mutation revisions; immutable dataset versions are not available.')
    return tree.sql(dialect='mysql'), explanation
