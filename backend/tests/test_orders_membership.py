"""Orders/Customers resolution with an unrelated active ecommerce schema."""
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
from app.services import relationship_service as relationships, metric_service, query_planner, schema_service, sql_executor, sql_validator, sql_generator
from app.routes import ask, metrics, relationships as routes

O='orders_usr_8'; C='customers_usr_8'; E='ecommerce_sales_dataset_usr_8'
QUESTION='Give me order IDs whose membership is Gold.'
SCOPED='Give me order IDs from orders and customers whose membership is Gold.'
SQL=f"SELECT o.`Order ID` FROM `{O}` o INNER JOIN `{C}` c ON o.`Customer ID`=c.`Customer ID` WHERE c.`Membership`='Gold' ORDER BY o.`Order ID`"

class OrdersMembershipTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        self.sessions=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.stack=ExitStack()
        for module in [connection,relationships,metric_service,query_planner,schema_service,sql_executor,sql_validator,ask,metrics]:
            if hasattr(module,'engine'): self.stack.enter_context(patch.object(module,'engine',self.engine))
            if hasattr(module,'SessionLocal'): self.stack.enter_context(patch.object(module,'SessionLocal',self.sessions))
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as c:
            c.execute(text(f'CREATE TABLE {O} (`Order ID` TEXT,`Customer ID` TEXT,amount REAL)'))
            c.execute(text(f"INSERT INTO {O} VALUES ('O1','C1',100),('O2','C2',200),('O3','C1',100),('O4','C3',150)"))
            c.execute(text(f'CREATE TABLE {C} (`Customer ID` TEXT,Membership TEXT)'))
            c.execute(text(f"INSERT INTO {C} VALUES ('C1','Gold'),('C2','Silver'),('C3','Gold')"))
            c.execute(text(f'CREATE TABLE {E} (Order_ID TEXT,Total_Sales REAL,Quantity_Ordered REAL)'))
            c.execute(text(f"INSERT INTO {E} VALUES ('UNRELATED',900,1)"))
            c.execute(text('CREATE TABLE private_usr_9 (Membership TEXT)'))
        self.catalog=relationships.catalog('usr_8')
        self.ds={d['name']:d for d in self.catalog}
        req=routes.RelationshipRequest(name='Orders customer membership',left_dataset_id=self.ds['orders']['id'],right_dataset_id=self.ds['customers']['id'],keys=[routes.Key(left='Customer ID',right='Customer ID')],approved=True)
        req.preview_digest=routes.preview('usr_8',req)['preview_digest']
        self.rel=routes.create(req,'usr_8')
        metric_service.create_or_update_metric(user_id='usr_8',name='Ecommerce only metric',source_dataset=E,expression='Total_Sales',approved_aliases=['membership','order IDs','Gold'])

    def tearDown(self):
        self.stack.close(); self.engine.dispose()

    def query(self,q,active):
        with patch.object(sql_generator,'call_llm',return_value=SQL) as llm,patch.object(ask,'generate_summary',return_value='Gold membership orders.'):
            result=ask.ask_question(ask.AskRequest(question=q),active,'usr_8')
        return result,llm

    def test_original_and_explicit_questions_execute_for_each_active_dataset(self):
        for active in [O,C,E]:
            for q in [QUESTION,SCOPED]:
                with self.subTest(active=active,question=q):
                    result,llm=self.query(q,active)
                    self.assertTrue(result['success'],result)
                    self.assertEqual(result['result'],[{'Order ID':'O1'},{'Order ID':'O3'},{'Order ID':'O4'}])
                    self.assertEqual(set(result['resolved_datasets']),{O,C})
                    self.assertEqual(set(result['join_explanation']['datasets']),{O,C})
                    self.assertEqual([r['id'] for r in result['join_explanation']['relationships']],[self.rel['id']])
                    self.assertNotIn(E,result['generated_sql'])
                    self.assertIn("'Gold'",result['generated_sql'])
                    prompt=llm.call_args.args[1]
                    self.assertIn(q,prompt)
                    self.assertIn(O,prompt); self.assertIn(C,prompt)
                    self.assertNotIn(E,prompt); self.assertNotIn('Ecommerce only metric',prompt)

    def test_customer_filter_completes_an_explicit_orders_scope(self):
        result,_=self.query('Give me order IDs from orders whose membership is Gold.',E)
        self.assertTrue(result['success'],result)
        self.assertEqual(set(result['resolved_datasets']),{O,C})
        self.assertEqual(len(result['result']),3)

    def test_only_required_pair_is_passed_to_path_lookup(self):
        real=relationships.resolve_paths
        with patch.object(relationships,'resolve_paths',wraps=real) as lookup:
            result,_=self.query(QUESTION,E)
        self.assertTrue(result['success'],result)
        self.assertTrue(lookup.call_args_list)
        for call in lookup.call_args_list:
            self.assertEqual(set(call.args[1]),{O,C})

    def test_irrelevant_active_table_is_not_in_dataset_clarification(self):
        required,_=relationships.query_context('usr_8',QUESTION,E)
        self.assertEqual(set(required),{O,C})

    def test_unapproved_inactive_and_stale_connections_remain_blocked(self):
        from app.models.relationship import DatasetRelationship
        for state in ['unapproved','inactive','stale']:
            with self.subTest(state=state):
                with self.sessions() as db:
                    r=db.get(DatasetRelationship,self.rel['id'])
                    r.approved=state!='unapproved'; r.active=state!='inactive'; r.needs_revalidation=state=='stale'
                    db.commit()
                result,llm=self.query(QUESTION,E)
                self.assertFalse(result['success'])
                self.assertIn(state,result['error'].lower())
                self.assertEqual(set(result['resolved_datasets']),{O,C})
                self.assertNotIn(E,result['error'])
                llm.assert_not_called()

    def test_cross_owner_active_reference_still_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as exc:
            self.query(QUESTION,'private_usr_9')
        self.assertEqual(exc.exception.status_code,403)

    def test_repair_context_retains_only_required_sources(self):
        from app.services import sql_regenerator
        with patch.object(sql_regenerator,'call_llm',return_value=SQL) as llm:
            sql_regenerator.regenerate_sql(QUESTION,O,'SELECT bad','Unknown column','usr_8',relationship_ids=[self.rel['id']],required_tables=[O,C])
        self.assertNotIn(E,llm.call_args.args[1])
        self.assertNotIn('Ecommerce only metric',llm.call_args.args[1])
        self.assertIn(self.rel['name'],llm.call_args.args[1])

    def test_literal_gold_does_not_select_an_unrelated_column_or_dataset(self):
        with self.engine.begin() as c:
            c.execute(text(f'ALTER TABLE {E} ADD COLUMN Gold TEXT'))
            c.execute(text('CREATE TABLE gold_usr_8 (Gold TEXT)'))
        result,_=self.query(QUESTION,E)
        self.assertTrue(result['success'],result)
        self.assertEqual(set(result['resolved_datasets']),{O,C})
        self.assertEqual(len(result['result']),3)

    def test_legitimate_bridge_is_added_by_approved_path_not_active_context(self):
        bridge='membership_bridge_usr_8'
        with self.engine.begin() as c:
            c.execute(text(f'CREATE TABLE {bridge} (`Customer ID` TEXT)'))
            c.execute(text(f"INSERT INTO {bridge} VALUES ('C1'),('C2'),('C3')"))
        catalog={d['table_name']:d for d in relationships.catalog('usr_8')}
        routes.deactivate(self.rel['id'],'usr_8')
        for left,right in [(O,bridge),(bridge,C)]:
            req=routes.RelationshipRequest(name=left+' to '+right,left_dataset_id=catalog[left]['id'],right_dataset_id=catalog[right]['id'],keys=[routes.Key(left='Customer ID',right='Customer ID')],approved=True)
            req.preview_digest=routes.preview('usr_8',req)['preview_digest']; routes.create(req,'usr_8')
        sql=f"SELECT o.`Order ID` FROM `{O}` o JOIN `{bridge}` b ON o.`Customer ID`=b.`Customer ID` JOIN `{C}` c ON b.`Customer ID`=c.`Customer ID` WHERE c.Membership='Gold' ORDER BY o.`Order ID`"
        with patch.object(sql_generator,'call_llm',return_value=sql),patch.object(ask,'generate_summary',return_value='Gold orders.'):
            result=ask.ask_question(ask.AskRequest(question=QUESTION),E,'usr_8')
        self.assertTrue(result['success'],result)
        self.assertEqual(set(result['resolved_datasets']),{O,C})
        self.assertEqual(set(result['join_explanation']['datasets']),{O,bridge,C})
        self.assertEqual(len(result['result']),3)
        self.assertNotIn(E,result['generated_sql'])

if __name__=='__main__': unittest.main()
