"""Isolated relationship and join-grain acceptance tests; no production access."""
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.migrations.runner import migrate
from app.services import relationship_service as service
from app.services.join_guard import guard_query
from app.routes import relationships as routes

class RelationshipTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=__import__('sqlalchemy').pool.StaticPool)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.patches = [patch.object(service, 'engine', self.engine), patch.object(service, 'SessionLocal', self.sessions)]
        for p in self.patches: p.start()
        migrate(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE orders_usr_1 (order_id TEXT, amount REAL, region TEXT)'))
            conn.execute(text("INSERT INTO orders_usr_1 VALUES ('O1',100,'North'),('O2',200,'South')"))
            conn.execute(text('CREATE TABLE items_usr_1 (order_id TEXT, item_id TEXT, quantity INTEGER)'))
            conn.execute(text("INSERT INTO items_usr_1 VALUES ('O1','A',1),('O1','B',2),('O2','C',1)"))
            conn.execute(text('CREATE TABLE private_usr_2 (order_id TEXT)'))
        self.ds = {d['name']:d for d in service.catalog('usr_1')}

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.engine.dispose()

    def approve(self, join_type='INNER', name='Order contents', keys=None, left='orders', right='items'):
        data = dict(name=name, left_dataset_id=self.ds[left]['id'], right_dataset_id=self.ds[right]['id'], keys=keys or [{'left':'order_id','right':'order_id'}], join_type=join_type, approved=True)
        req = routes.RelationshipRequest(**data)
        req.preview_digest = routes.preview('usr_1', req)['preview_digest']
        return routes.create(req, 'usr_1')

    def result(self, sql, selected=None):
        guarded, explanation = guard_query(sql, 'usr_1', selected)
        with self.engine.connect() as conn:
            return conn.execute(text(guarded)).all(), explanation, guarded

    def test_order_revenue_does_not_expand(self):
        self.approve()
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT SUM(amount) FROM orders_usr_1')).scalar(), 300)
            self.assertEqual(conn.execute(text('SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')).scalar(), 400)
        rows, info, sql = self.result('SELECT SUM(o.amount) AS revenue FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0], 300)
        self.assertTrue(info['preaggregation'])
        self.assertNotIn('SUM(DISTINCT', sql)
        self.assertEqual(info['metrics'][0]['source'], 'orders_usr_1')

    def test_equal_amounts_are_legitimate_records(self):
        with self.engine.begin() as conn: conn.execute(text('UPDATE orders_usr_1 SET amount=100'))
        self.approve()
        rows,_,sql = self.result('SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0], 200)
        self.assertNotIn('DISTINCT', sql)

    def test_detail_quantity_is_valid(self):
        self.approve()
        rows,info,_ = self.result('SELECT SUM(i.quantity) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0], 4)
        self.assertFalse(info['preaggregation'])

    def test_detail_dimension_requires_allocation(self):
        self.approve()
        with self.assertRaises(service.RelationshipError):
            self.result('SELECT i.item_id, SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id GROUP BY i.item_id')

    def test_many_to_many_membership_and_raw_expansion(self):
        with self.engine.begin() as conn: conn.execute(text("INSERT INTO orders_usr_1 VALUES ('O1',50,'North')"))
        rel = self.approve()
        self.assertEqual(rel['profile']['cardinality'], 'many-to-many')
        self.assertEqual(rel['profile']['expected_join_records'], 5)
        rows,_,_ = self.result('SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0], 350)
        with self.assertRaises(service.RelationshipError):
            self.result('SELECT SUM(o.amount), SUM(i.quantity) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')

    def test_one_to_one(self):
        with self.engine.begin() as conn: conn.execute(text("DELETE FROM items_usr_1 WHERE item_id='B'"))
        rel = self.approve()
        self.assertEqual(rel['profile']['cardinality'], 'one-to-one')
        rows,info,_ = self.result('SELECT SUM(o.amount), SUM(i.quantity) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(tuple(rows[0]), (300,2))
        self.assertFalse(info['preaggregation'])

    def test_null_duplicate_unmatched_counts_and_left(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO orders_usr_1 VALUES ('O3',50,'East'), (NULL,25,'East')"))
            conn.execute(text("INSERT INTO items_usr_1 VALUES ('O9','D',5),(NULL,'E',9)"))
        p = service.profile('orders_usr_1','items_usr_1',[{'left':'order_id','right':'order_id'}], 'LEFT')
        self.assertEqual(p['left']['total_records'], 4)
        self.assertEqual(p['left']['incomplete_key_records'], 1)
        self.assertEqual(p['left']['matched_source_records'], 2)
        self.assertEqual(p['left']['unmatched_source_records'], 2)
        self.assertEqual(p['right']['matched_source_records'], 3)
        self.assertEqual(p['right']['unmatched_source_records'], 2)
        self.assertEqual(p['right']['duplicate_key_groups'], 1)
        self.assertEqual(p['expected_inner_join_records'], 3)
        self.assertEqual(p['expected_join_records'], 5)
        rel = self.approve('LEFT')
        rows,info,_ = self.result('SELECT SUM(o.amount) FROM orders_usr_1 o LEFT JOIN items_usr_1 i ON o.order_id=i.order_id', [rel['id']])
        self.assertEqual(rows[0][0], 375)
        self.assertTrue(info['warnings'])
        routes.deactivate(rel['id'],'usr_1')
        self.approve('INNER')
        rows,_,_ = self.result('SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0], 300)

    def test_composite_keys_and_leading_zeros(self):
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE a_usr_1 (code TEXT, tenant TEXT, amount REAL)'))
            conn.execute(text('CREATE TABLE b_usr_1 (code TEXT, tenant TEXT)'))
            conn.execute(text("INSERT INTO a_usr_1 VALUES ('001','X',10),('1','X',20),('001','Y',30)"))
            conn.execute(text("INSERT INTO b_usr_1 VALUES ('001','X'),('001','Y')"))
        self.ds.update({d['name']:d for d in service.catalog('usr_1')})
        rel = self.approve(left='a',right='b',keys=[{'left':'code','right':'code'},{'left':'tenant','right':'tenant'}])
        self.assertEqual(rel['profile']['expected_join_records'], 2)
        rows,_,sql = self.result('SELECT SUM(a.amount) FROM a_usr_1 a JOIN b_usr_1 b ON a.code=b.code AND a.tenant=b.tenant')
        self.assertEqual(rows[0][0], 40)
        self.assertNotIn('CAST',sql)
        with self.assertRaises(service.RelationshipError):
            self.result('SELECT SUM(a.amount) FROM a_usr_1 a JOIN b_usr_1 b ON a.code=b.code')

    def test_incompatible_types_rejected(self):
        with self.assertRaises(service.RelationshipError): service.profile('orders_usr_1','items_usr_1',[{'left':'order_id','right':'quantity'}])

    def test_ambiguous_path_requires_choice(self):
        first = self.approve(name='Order contents')
        self.approve(name='Alternative business meaning')
        with self.assertRaises(service.RelationshipChoice) as ctx:
            service.resolve_paths('usr_1',['orders_usr_1','items_usr_1'])
        self.assertEqual(len(ctx.exception.options),2)
        self.result('SELECT SUM(i.quantity) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id', [first['id']])

    def test_missing_connection_and_wrong_keys_refused(self):
        sql = 'SELECT SUM(i.quantity) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id'
        with self.assertRaises(service.RelationshipError): self.result(sql)
        self.approve()
        with self.assertRaises(service.RelationshipError): self.result(sql.replace('o.order_id=i.order_id','o.region=i.item_id'))

    def test_mutation_and_schema_change_require_revalidation(self):
        rel = self.approve()
        service.invalidate_dataset('orders_usr_1')
        self.assertTrue(service.relationships('usr_1')[0]['needs_revalidation'])
        with self.assertRaises(service.RelationshipError): service.resolve_paths('usr_1',['orders_usr_1','items_usr_1'])
        data = dict(name=rel['name'], left_dataset_id=rel['left_dataset_id'], right_dataset_id=rel['right_dataset_id'], keys=rel['keys'], join_type='INNER', approved=True)
        req = routes.RelationshipRequest(**data)
        req.preview_digest = routes.preview('usr_1',req)['preview_digest']
        routes.edit(rel['id'],req,'usr_1')
        with self.engine.begin() as conn: conn.execute(text('ALTER TABLE items_usr_1 ADD COLUMN new_field TEXT'))
        self.assertTrue(service.relationships('usr_1')[0]['needs_revalidation'])

    def test_preview_changes_require_new_approval(self):
        req = routes.RelationshipRequest(left_dataset_id=self.ds['orders']['id'],right_dataset_id=self.ds['items']['id'],keys=[routes.Key(left='order_id',right='order_id')], approved=True)
        req.preview_digest = routes.preview('usr_1',req)['preview_digest']
        with self.engine.begin() as conn: conn.execute(text("INSERT INTO items_usr_1 VALUES ('O2','Z',1)"))
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): routes.create(req,'usr_1')

    def test_cross_user_rejected(self):
        other = service.catalog('usr_2')[0]
        with self.sessions() as db:
            with self.assertRaises(service.RelationshipError): service.owned(db,other['id'],'usr_1')
        rel = self.approve()
        self.assertEqual(service.relationships('usr_2'),[])
        with self.assertRaises(service.RelationshipError): service.resolve_paths('usr_2',['orders_usr_1','items_usr_1'],[rel['id']])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): routes.deactivate(rel['id'],'usr_2')

    def test_migration_is_idempotent_and_preserves_data(self):
        self.approve()
        migrate(self.engine)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM orders_usr_1')).scalar(),2)
            self.assertEqual(conn.execute(text('SELECT COUNT(*) FROM dataset_relationships')).scalar(),1)

    def test_guard_rejects_other_owner_even_without_second_owned_source(self):
        with self.assertRaises(service.RelationshipError):
            guard_query('SELECT * FROM private_usr_2', 'usr_1')

    def test_guard_rejects_omitted_required_dataset(self):
        with self.assertRaises(service.RelationshipError):
            guard_query('SELECT SUM(amount) FROM orders_usr_1', 'usr_1', required_tables=['orders_usr_1','items_usr_1'])

    def test_multihop_and_ambiguous_indirect_paths(self):
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE bridge_usr_1 (order_id TEXT)'))
            conn.execute(text("INSERT INTO bridge_usr_1 VALUES ('O1'),('O2')"))
        self.ds.update({d['name']:d for d in service.catalog('usr_1')})
        self.approve(left='orders',right='bridge')
        self.approve(left='bridge',right='items')
        paths = service.resolve_paths('usr_1',['orders_usr_1','items_usr_1'])
        self.assertEqual(len(paths),2)
        self.approve()
        with self.assertRaises(service.RelationshipChoice):
            service.resolve_paths('usr_1',['orders_usr_1','items_usr_1'])

    def test_registered_metric_context_is_preserved_in_join_generator(self):
        # The same generator receives approved keys and registered metric context.
        from app.services import sql_generator
        with patch('app.services.metric_service.list_metrics', return_value=[dict(name='Revenue', approved_aliases=['sales'], supported_aggregation='SUM', expression='amount')]), patch.object(sql_generator, 'schema_to_prompt', return_value='amount REAL'), patch.object(sql_generator, 'call_llm', return_value='SELECT SUM(orders.amount) FROM orders JOIN items ON orders.order_id=items.order_id') as llm:
            # Generator obtains engine lazily from the existing connection module.
            import app.database.connection as connection
            with patch.object(connection, 'engine', self.engine):
                self.approve()
                sql_generator.generate_sql('Revenue from orders and items', 'orders_usr_1', 'usr_1')
        self.assertIn('APPROVED ANALYTICAL RELATIONSHIPS', llm.call_args.args[1])
        self.assertIn('REGISTERED METRICS', llm.call_args.args[1])
        self.assertIn('SUM(amount)', llm.call_args.args[1])

    def test_http_relationship_choice_query_and_history(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.services.auth_service import get_current_user_id
        from app.routes import ask, metrics, history, report
        from app.services import sql_executor, sql_validator
        from app.database.connection import Base
        Base.metadata.create_all(self.engine)
        self.approve(name='Contents')
        self.approve(name='Alternative meaning')
        app = FastAPI()
        app.include_router(routes.router)
        app.include_router(ask.router)
        app.include_router(metrics.clarification_router)
        app.dependency_overrides[get_current_user_id] = lambda: 'usr_1'
        sql = 'SELECT SUM(o.amount) AS revenue FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id'
        with patch.object(ask,'engine',self.engine), patch.object(ask,'SessionLocal',self.sessions), patch.object(metrics,'SessionLocal',self.sessions), patch.object(sql_executor,'engine',self.engine), patch.object(sql_validator,'engine',self.engine), patch.object(ask,'generate_sql',return_value=sql):
            with TestClient(app) as client:
                response = client.post('/ask',headers={'X-Table-Name':'orders_usr_1'},json={'question':'Total revenue from orders involving items'})
                self.assertEqual(response.status_code,200)
                choice = response.json()
                self.assertTrue(choice['needs_clarification'])
                response = client.post('/api/clarification/resolve',json={'clarification_id':choice['clarification_id'],'selected_option_id':choice['options'][0]['id']})
                result = response.json()
                self.assertTrue(result['success'],result)
                self.assertEqual(result['result'][0]['revenue'],300)
                self.assertTrue(result['join_explanation']['preaggregation'])
                bad = client.post('/api/relationships/preview',json={'left_dataset_id':self.ds['orders']['id'],'right_dataset_id':service.catalog('usr_2')[0]['id'],'keys':[{'left':'order_id','right':'order_id'}]})
                self.assertEqual(bad.status_code,400)
                self.assertEqual(len(client.get('/api/relationships').json()['relationships']),2)
        with self.sessions() as db:
            entries = history.get_history('usr_1',db)
            self.assertEqual(entries[0].result_count,1)
            self.assertIn('Metric source:',entries[0].summary)
            payload = report.ReportCreateSchema(title='Verified revenue',table_name='orders_usr_1',question='Revenue',generated_sql=result['generated_sql'],summary=result['summary'],records=result['result'])
            saved = report.create_report(payload,'usr_1',db)
            detail = report.get_report_detail(saved.id,'usr_1',db)
            self.assertEqual(detail.records[0]['revenue'],300)
            self.assertIn('Approved relationship', detail.summary)

    def test_raw_detail_rows_and_expansion_are_explained(self):
        self.approve()
        rows,info,_ = self.result('SELECT o.order_id, i.item_id FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(len(rows),3)
        self.assertEqual(info['relationships'][0]['profile']['expansion_per_left_record'],1.5)

    def test_unsupported_joins_and_distinct_shortcut_refused(self):
        self.approve()
        for sql in [
            'SELECT SUM(DISTINCT o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id',
            'SELECT o.order_id FROM orders_usr_1 o CROSS JOIN items_usr_1 i',
            'SELECT SUM(o.amount) FROM orders_usr_1 o LEFT JOIN items_usr_1 i ON o.order_id=i.order_id',
            'SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id WHERE i.quantity > 1',
        ]:
            with self.subTest(sql=sql), self.assertRaises(service.RelationshipError): self.result(sql)

    def test_cleaner_tracking_invalidates_before_write(self):
        self.approve()
        from types import SimpleNamespace
        @service.track_changes
        def mutation(ctx):
            self.assertTrue(service.relationships('usr_1')[0]['needs_revalidation'])
            return {'success':True}
        mutation(SimpleNamespace(table_name='items_usr_1'))

    def test_measured_suggestion_never_auto_approves(self):
        data = routes.suggestions(self.ds['orders']['id'],self.ds['items']['id'],'usr_1')
        self.assertEqual(data['suggestions'][0]['profile']['cardinality'],'one-to-many')
        self.assertEqual(service.relationships('usr_1'),[])

    def test_fresh_cardinality_is_measured_at_execution(self):
        rel = self.approve()
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO items_usr_1 VALUES ('O2','NEW',8)"))
        rows,info,_ = self.result('SELECT SUM(o.amount) FROM orders_usr_1 o JOIN items_usr_1 i ON o.order_id=i.order_id')
        self.assertEqual(rows[0][0],300)
        self.assertEqual(info['relationships'][0]['profile']['expected_join_records'],4)
        self.assertEqual(rel['profile']['expected_join_records'],3)

    def test_http_authentication_is_required(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI(); app.include_router(routes.router)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/relationships/datasets').status_code,401)

    def test_deactivation_disallows_execution(self):
        rel = self.approve()
        routes.deactivate(rel['id'],'usr_1')
        with self.assertRaises(service.RelationshipError): service.resolve_paths('usr_1',['orders_usr_1','items_usr_1'])

if __name__ == '__main__': unittest.main()
