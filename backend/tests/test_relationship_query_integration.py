"""Isolated end-to-end regressions for relationship-to-query dataset resolution."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.connection import Base
from app.services import relationship_service as service, sql_executor, sql_validator, metric_service, query_planner
from app.routes import ask, metrics, relationships as routes
import app.database.connection as connection

H = 'qa_header_nov01_usr_8'
I = 'qa_items_nov01_usr_8'
E = 'ecommerce_sales_dataset_usr_8'
NAIVE = f'SELECT SUM(h.amount) AS amount, SUM(i.quantity) AS quantity FROM {H} h JOIN {I} i ON h.order_key=i.order_key'
SNAPSHOT = Path(__file__).resolve().parents[1]/'uploads'/'ecommerce_sales_dataset.csv'

class QueryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ecommerce = None
        if SNAPSHOT.exists():
            import pandas as pd
            from app.services.data_cleaner import clean_numeric
            frame = pd.read_csv(SNAPSHOT)
            frame.columns = frame.columns.str.strip()
            frame['Total_Sales'] = clean_numeric(frame['Total_Sales'])
            cls.ecommerce = frame[['Sales_Region','Total_Sales','Quantity_Ordered','Unit_Price']].to_dict('records')

    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        self.sessions=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.stack=ExitStack()
        for module in [connection, service, sql_executor, sql_validator, metric_service, query_planner, ask, metrics]:
            if hasattr(module,'engine'): self.stack.enter_context(patch.object(module,'engine',self.engine))
            if hasattr(module,'SessionLocal'): self.stack.enter_context(patch.object(module,'SessionLocal',self.sessions))
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(text(f'CREATE TABLE {H} (order_key TEXT, amount REAL)'))
            c.execute(text(f"INSERT INTO {H} VALUES ('QA-O1',100),('QA-O2',200),('QA-O3',100)"))
            c.execute(text(f'CREATE TABLE {I} (order_key TEXT, quantity REAL)'))
            c.execute(text(f"INSERT INTO {I} VALUES ('QA-O1',1),('QA-O1',2),('QA-O2',1),('QA-O3',1)"))
            c.execute(text('CREATE TABLE orders_archive_usr_8 (order_key TEXT, Amount REAL, revenue REAL)'))
            c.execute(text('CREATE TABLE orders_usr_8 (order_key TEXT, amount REAL)'))
            c.execute(text(f'CREATE TABLE {E} (Sales_Region TEXT, Total_Sales REAL, Quantity_Ordered REAL, Unit_Price REAL)'))
            if self.ecommerce:
                c.execute(text(f'INSERT INTO {E} VALUES (:Sales_Region,:Total_Sales,:Quantity_Ordered,:Unit_Price)'),self.ecommerce)
        self.ds={d['name']:d for d in service.catalog('usr_8')}
        self.rel=self.approve()

    def tearDown(self):
        self.stack.close(); self.engine.dispose()

    def approve(self, relationship_id=None):
        req=routes.RelationshipRequest(name='QA order contents',left_dataset_id=self.ds['qa_header_nov01']['id'],right_dataset_id=self.ds['qa_items_nov01']['id'],keys=[routes.Key(left='order_key',right='order_key')],approved=True)
        req.preview_digest=routes.preview('usr_8',req)['preview_digest']
        return routes.edit(relationship_id,req,'usr_8') if relationship_id else routes.create(req,'usr_8')

    def query(self, question, sql=None, active=H, **kwargs):
        with patch.object(ask,'generate_sql',return_value=sql) as generate, patch.object(ask,'generate_summary',return_value='Query complete.'):
            result=ask.ask_question(ask.AskRequest(question=question,**kwargs),active,'usr_8')
            self.last_generator=generate
            return result

    def test_header_select_without_relationship_requirement(self):
        routes.deactivate(self.rel['id'],'usr_8')
        for ref in [H,'qa_header_nov01',self.ds['qa_header_nov01']['id']]:
            with self.subTest(ref=ref):
                r=self.query('Show order_key, amount from this table',f'SELECT order_key, amount FROM {H}',active=ref)
                self.assertTrue(r['success'],r)
                self.assertEqual(r['result'],[{'order_key':'QA-O1','amount':100},{'order_key':'QA-O2','amount':200},{'order_key':'QA-O3','amount':100}])
                self.assertEqual(self.last_generator.call_args.kwargs['required_tables'],[H])

    def test_header_total_is_400(self):
        r=self.query('Total amount from this table',f'SELECT SUM(amount) AS amount FROM {H}')
        self.assertTrue(r['success'],r); self.assertEqual(r['result'][0]['amount'],400)

    def test_detail_join_returns_four_records(self):
        r=self.query('Show order_key, amount and quantity from qa_header_nov01 and qa_items_nov01',f'SELECT h.order_key,h.amount,i.quantity FROM {H} h JOIN {I} i ON h.order_key=i.order_key')
        self.assertTrue(r['success'],r); self.assertEqual(len(r['result']),4)

    def test_combined_totals_are_400_and_5(self):
        with self.engine.connect() as c:
            self.assertEqual(tuple(c.execute(text(NAIVE)).first()),(500,5))
            self.assertEqual(c.execute(text(f'SELECT SUM(DISTINCT amount) FROM {H}')).scalar(),300)
        r=self.query('Combined amount and quantity totals from qa_header_nov01 and qa_items_nov01',NAIVE)
        self.assertTrue(r['success'],r)
        self.assertEqual(r['result'],[{'amount':400,'quantity':5}])
        self.assertNotIn('DISTINCT',r['generated_sql'])
        self.assertTrue(r['join_explanation']['preaggregation'])

    def test_combined_weighted_average_and_count(self):
        sql=f'SELECT SUM(h.amount) AS amount, AVG(i.quantity) AS average_quantity, COUNT(i.quantity) AS quantity_records FROM {H} h JOIN {I} i ON h.order_key=i.order_key'
        r=self.query('Combined amounts and quantity from qa_header_nov01 and qa_items_nov01',sql)
        self.assertTrue(r['success'],r)
        self.assertEqual(r['result'],[{'amount':400,'average_quantity':1.25,'quantity_records':4}])

    def test_combined_grouping_by_parent_key(self):
        sql=NAIVE.replace('SELECT ','SELECT h.order_key, ')+' GROUP BY h.order_key ORDER BY h.order_key'
        r=self.query('Amount and quantity by order_key from qa_header_nov01 and qa_items_nov01',sql)
        self.assertTrue(r['success'],r)
        self.assertEqual(r['result'],[{'order_key':'QA-O1','amount':100,'quantity':3},{'order_key':'QA-O2','amount':200,'quantity':1},{'order_key':'QA-O3','amount':100,'quantity':1}])

    def test_stale_revalidation_restores_query_eligibility(self):
        service.invalidate_dataset(H)
        with self.engine.begin() as c: c.execute(text(f"UPDATE {H} SET amount=125 WHERE order_key='QA-O3'"))
        r=self.query('Combined totals from qa_header_nov01 and qa_items_nov01',NAIVE)
        self.assertFalse(r['success']); self.assertIn('stale',r['error'])
        self.assertIn(H,r['error']); self.assertIn(I,r['error'])
        self.approve(self.rel['id'])
        r=self.query('Combined totals from qa_header_nov01 and qa_items_nov01',NAIVE)
        self.assertTrue(r['success'],r); self.assertEqual(r['result'],[{'amount':425,'quantity':5}])

    def test_inactive_unapproved_and_missing_connection_diagnostics(self):
        for state in ['inactive','unapproved','missing']:
            with self.sessions() as db:
                from app.models.relationship import DatasetRelationship
                rel=db.get(DatasetRelationship,self.rel['id'])
                if state=='inactive': rel.active=False
                if state=='unapproved': rel.active=True; rel.approved=False
                if state=='missing': db.delete(rel)
                db.commit()
            r=self.query('Totals from qa_header_nov01 and qa_items_nov01',NAIVE)
            self.assertFalse(r['success']); self.assertIn(state,r['error'].lower())
            self.assertIn(H,r['error']); self.assertIn(I,r['error'])
            self.last_generator.assert_not_called()

    def test_logical_ids_and_names_find_identical_graph_path(self):
        for refs in [[H,I],['qa_header_nov01','qa_items_nov01'],[self.ds['qa_header_nov01']['id'],self.ds['qa_items_nov01']['id']]]:
            self.assertEqual(service.resolve_paths('usr_8',refs)[0]['id'],self.rel['id'])

    def test_generation_and_repair_never_expand_selected_scope(self):
        from app.services import sql_generator, sql_regenerator
        metric=dict(name='Amount',supported_aggregation='SUM',expression='amount')
        with patch.object(sql_generator,'schema_to_prompt',return_value='order_key TEXT, amount REAL'), patch.object(metric_service,'list_metrics',return_value=[metric]), patch.object(sql_generator,'call_llm',return_value=f'SELECT amount FROM {H}') as llm:
            sql_generator.generate_sql('Show amount from this table',H,'usr_8',required_tables=[H])
            prompt=llm.call_args.args[1]
            self.assertNotIn(I,prompt); self.assertNotIn(E,prompt)
            self.assertIn(H,prompt)
        with patch.object(sql_generator,'schema_to_prompt',return_value='amount REAL'), patch.object(metric_service,'list_metrics',return_value=[]), patch.object(sql_regenerator,'call_llm',return_value=f'SELECT amount FROM {H}') as llm:
            sql_regenerator.regenerate_sql('Show amount',H,'SELECT invalid','bad column','usr_8',required_tables=[H])
            self.assertNotIn(I,llm.call_args.args[1])

    def test_ambiguous_dataset_selection_resumes_existing_clarification(self):
        # Both items and another dataset can supply quantity; active header cannot.
        with self.engine.begin() as c: c.execute(text('CREATE TABLE other_items_usr_8 (order_key TEXT, quantity REAL)'))
        r=self.query('Show quantity')
        self.assertTrue(r.get('needs_clarification'),r)
        self.assertTrue(r['clarification_id'].startswith('ds_'))
        self.last_generator.assert_not_called()
        option=next(o for o in r['options'] if 'qa_items_nov01' in o['label'])
        with patch.object(ask,'generate_sql',return_value=f'SELECT quantity FROM {I}'), patch.object(ask,'generate_summary',return_value='Quantities.'):
            result=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=r['clarification_id'],selected_option_id=option['id']),'usr_8')
        self.assertTrue(result['success'],result); self.assertEqual(len(result['result']),4)

    def test_reversed_inner_join_combined_totals(self):
        sql=f'SELECT SUM(h.amount) AS amount,SUM(i.quantity) AS quantity FROM {I} i JOIN {H} h ON i.order_key=h.order_key'
        r=self.query('Totals from qa_header_nov01 and qa_items_nov01',sql)
        self.assertTrue(r['success'],r); self.assertEqual(r['result'],[{'amount':400,'quantity':5}])

    def test_combined_left_join_preserves_unmatched_header(self):
        with self.engine.begin() as c: c.execute(text(f"INSERT INTO {H} VALUES ('QA-O4',50)"))
        req=routes.RelationshipRequest(name='QA left contents',left_dataset_id=self.ds['qa_header_nov01']['id'],right_dataset_id=self.ds['qa_items_nov01']['id'],keys=[routes.Key(left='order_key',right='order_key')],join_type='LEFT',approved=True)
        req.preview_digest=routes.preview('usr_8',req)['preview_digest']
        routes.edit(self.rel['id'],req,'usr_8')
        sql=NAIVE.replace(' JOIN ',' LEFT JOIN ')
        r=self.query('Totals from qa_header_nov01 and qa_items_nov01',sql)
        self.assertTrue(r['success'],r); self.assertEqual(r['result'],[{'amount':450,'quantity':5}])
        self.assertTrue(r['join_explanation']['warnings'])

    def test_dataset_choice_can_be_followed_by_relationship_choice(self):
        self.approve()  # second approved meaning for the same pair
        with self.engine.begin() as c: c.execute(text('CREATE TABLE other_items_usr_8 (order_key TEXT,quantity REAL)'))
        choice=self.query('Combined amount and quantity totals')
        self.assertTrue(choice['clarification_id'].startswith('ds_'),choice)
        option=next(o for o in choice['options'] if 'qa_header_nov01' in o['label'] and 'qa_items_nov01' in o['label'])
        relation_choice=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=choice['clarification_id'],selected_option_id=option['id']),'usr_8')
        self.assertTrue(relation_choice['clarification_id'].startswith('rel_'),relation_choice)
        with patch.object(ask,'generate_sql',return_value=NAIVE):
            result=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=relation_choice['clarification_id'],selected_option_id=relation_choice['options'][0]['id']),'usr_8')
        self.assertTrue(result['success'],result); self.assertEqual(result['result'],[{'amount':400,'quantity':5}])

    def test_unapproved_wrong_keys_and_join_type_stay_blocked(self):
        for sql in [NAIVE.replace('h.order_key=i.order_key','h.amount=i.quantity'),NAIVE.replace(' JOIN ',' LEFT JOIN ')]:
            r=self.query('Totals from qa_header_nov01 and qa_items_nov01',sql)
            self.assertFalse(r['success']); self.assertTrue(r['relationship_limitation'])

    @unittest.skipUnless(SNAPSHOT.exists(),'Local ecommerce snapshot is absent; live data is never fetched.')
    def test_ecommerce_total_28110784_23(self):
        # The local existing CSV is copied to isolated SQLite, never queried live.
        for question in ['Total revenue across all orders','Total revenue from ecommerce_sales_dataset']:
            r=self.query(question,active=E)
            self.assertTrue(r['success'],r)
            self.assertAlmostEqual(r['result'][0]['Revenue'],28110784.23,places=2)
            self.last_generator.assert_not_called()

    @unittest.skipUnless(SNAPSHOT.exists(),'Local ecommerce snapshot is absent; live data is never fetched.')
    def test_ecommerce_four_region_totals(self):
        r=self.query('Revenue by region',active=E)
        self.assertTrue(r['success'],r); self.assertEqual(len(r['result']),4)
        actual={row['Sales_Region']:round(row['Revenue'],2) for row in r['result']}
        self.assertEqual(actual,{'East':7134297.52,'North':6906958.05,'South':6950825.18,'West':7118703.48})

    @unittest.skipUnless(SNAPSHOT.exists(),'Local ecommerce snapshot is absent; live data is never fetched.')
    def test_highest_sales_revenue_choice_east_7134297_52(self):
        r=self.query('Which region has the highest sales?',active=E)
        self.assertTrue(r.get('needs_clarification'),r)
        result=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=r['clarification_id'],selected_option_id='revenue'),'usr_8')
        self.assertTrue(result['success'],result)
        self.assertEqual(result['result'][0]['Sales_Region'],'East')
        self.assertAlmostEqual(result['result'][0]['Revenue'],7134297.52,places=2)

if __name__=='__main__': unittest.main()
