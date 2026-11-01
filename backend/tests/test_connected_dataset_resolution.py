"""Compact identifiers and connected source-plan selection regressions."""
import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database.connection import Base
import app.database.connection as connection
from app.services import relationship_service as service, metric_service, query_planner, schema_service, sql_executor, sql_validator, sql_generator
from app.services.dataset_resolution import field_term
from app.models.relationship import DatasetRelationship
from app.routes import ask, metrics, relationships as routes

O='orders_usr_8'; C='customers_usr_8'; E='ecommerce_sales_dataset_usr_8'
ORIGINAL='Give me order IDs whose membership is Gold.'
SINGULAR='Give me order ID whose membership is gold.'
SCOPED='Give me order ID from orders and customers whose membership is gold.'
SQL=f"SELECT o.OrderID FROM {O} o JOIN {C} c ON o.CustomerID=c.CustomerID WHERE c.Membership='gold' ORDER BY o.OrderID"

class ConnectedResolutionTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        self.sessions=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.stack=ExitStack()
        for module in [connection,service,metric_service,query_planner,schema_service,sql_executor,sql_validator,ask,metrics]:
            if hasattr(module,'engine'): self.stack.enter_context(patch.object(module,'engine',self.engine))
            if hasattr(module,'SessionLocal'): self.stack.enter_context(patch.object(module,'SessionLocal',self.sessions))
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(text(f'CREATE TABLE {O} (OrderID TEXT, CustomerID TEXT, amount REAL)'))
            c.execute(text(f"INSERT INTO {O} VALUES ('O1','C1',100),('O2','C2',200),('O3','C3',100)"))
            c.execute(text(f'CREATE TABLE {C} (CustomerID TEXT, Membership TEXT COLLATE NOCASE)'))
            c.execute(text(f"INSERT INTO {C} VALUES ('C1','Gold'),('C2','Silver'),('C3','gold')"))
            c.execute(text(f'CREATE TABLE {E} (Order_ID TEXT, CustomerID TEXT, Total_Sales REAL)'))
            c.execute(text(f"INSERT INTO {E} VALUES ('UNRELATED','C1',900)"))
            c.execute(text('CREATE TABLE private_usr_9 (OrderID TEXT, Membership TEXT)'))
        self.ds={d['table_name']:d for d in service.catalog('usr_8')}
        self.rel=self.approve(O,C)

    def tearDown(self):
        self.stack.close();self.engine.dispose()

    def approve(self,left,right):
        req=routes.RelationshipRequest(name=left+' membership via '+right,left_dataset_id=self.ds[left]['id'],right_dataset_id=self.ds[right]['id'],keys=[routes.Key(left='CustomerID',right='CustomerID')],approved=True)
        req.preview_digest=routes.preview('usr_8',req)['preview_digest']
        return routes.create(req,'usr_8')

    def query(self,q,active):
        with patch.object(sql_generator,'call_llm',return_value=SQL) as llm,patch.object(ask,'generate_summary',return_value='Gold orders.'):
            result=ask.ask_question(ask.AskRequest(question=q),active,'usr_8')
        return result,llm

    def assert_orders(self,result):
        self.assertTrue(result['success'],result)
        self.assertFalse(result.get('needs_clarification'),result)
        self.assertEqual(set(result['resolved_datasets']),{O,C})
        self.assertEqual(result['result'],[{'OrderID':'O1'},{'OrderID':'O3'}])
        self.assertNotIn(E,result['generated_sql'])
        self.assertIn("'gold'",result['generated_sql'])

    def test_identifier_spelling_normalization(self):
        for column in ['OrderID','OrderId','OrderIDs','Order ID','Order IDs','Order_ID','Order_IDs']:
            self.assertEqual(field_term(column),'order id',column)
        self.assertEqual(field_term('CustomerID'),'customer id')
        self.assertEqual(field_term('CustomerName'),'customer name')

    def test_singular_original_and_explicit_matrix_on_each_active_dataset(self):
        for active in [O,C,E]:
            for question in [ORIGINAL,SINGULAR,SCOPED]:
                with self.subTest(active=active,question=question):
                    result,llm=self.query(question,active)
                    self.assert_orders(result)
                    prompt=llm.call_args.args[1]
                    self.assertIn('OrderID',prompt); self.assertIn('CustomerID',prompt)
                    self.assertNotIn(E,prompt)

    def test_multiple_eligible_source_plans_ask_regardless_of_active(self):
        self.approve(E,C)
        for active in [O,C,E]:
            with self.subTest(active=active):
                result,llm=self.query(SINGULAR,active)
                self.assertTrue(result.get('needs_clarification'),result)
                self.assertTrue(result['clarification_id'].startswith('ds_'))
                selections={frozenset(o['dataset_ids']) for o in result['options']}
                self.assertEqual(selections,{frozenset([self.ds[O]['id'],self.ds[C]['id']]),frozenset([self.ds[E]['id'],self.ds[C]['id']])})
                llm.assert_not_called()

    def test_explicit_scope_is_not_overridden_by_other_eligible_source(self):
        self.approve(E,C)
        for active in [O,C,E]:
            with self.subTest(active=active): self.assert_orders(self.query(SCOPED,active)[0])

    def test_dataset_choice_resumes_intended_compact_identifier_plan(self):
        self.approve(E,C)
        result,_=self.query(SINGULAR,E)
        option=next(o for o in result['options'] if set(o['dataset_ids'])=={self.ds[O]['id'],self.ds[C]['id']})
        with patch.object(sql_generator,'call_llm',return_value=SQL),patch.object(ask,'generate_summary',return_value='Gold orders.'):
            resolved=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=result['clarification_id'],selected_option_id=option['id']),'usr_8')
        self.assert_orders(resolved)

    def test_ineligible_alternative_is_not_a_valid_choice(self):
        other=self.approve(E,C)
        for state in ['unapproved','inactive','stale']:
            with self.sessions() as db:
                rel=db.get(DatasetRelationship,other['id'])
                rel.approved=state!='unapproved';rel.active=state!='inactive';rel.needs_revalidation=state=='stale'
                db.commit()
            self.assert_orders(self.query(SINGULAR,E)[0])

    def test_missing_eligible_plan_still_blocks_execution(self):
        service.invalidate_dataset(O)
        result,llm=self.query(SINGULAR,E)
        self.assertFalse(result['success']); self.assertIn('stale',result['error'])
        self.assertEqual(set(result['resolved_datasets']),{O,C})
        llm.assert_not_called()

    def test_eligible_connectivity_precedes_a_dataset_label_affinity(self):
        # A renamed source still supplies the requested fields; graph eligibility
        # must beat a misleading entity label on an unconnected source.
        with self.sessions() as db:
            from app.models.relationship import DatasetReference
            db.get(DatasetReference,self.ds[O]['id']).label='purchase_headers'
            db.commit()
        self.assert_orders(self.query(SINGULAR,E)[0])

if __name__=='__main__': unittest.main()
