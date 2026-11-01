"""Measured name-vs-key grounding and approved join semantics (isolated SQLite)."""
import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import sqlglot
from app.database.connection import Base
import app.database.connection as connection
from app.services import relationship_service as service,metric_service,query_planner,schema_service,sql_executor,sql_validator,sql_generator,sql_regenerator
from app.services.value_grounding import resolve_values,validate_bindings,GroundingError
from app.routes import ask,metrics,relationships as routes

O='orders_usr_8'; C='customers_usr_8'

class ValueGroundingTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        self.sessions=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.stack=ExitStack()
        for module in [connection,service,metric_service,query_planner,schema_service,sql_executor,sql_validator,ask,metrics]:
            if hasattr(module,'engine'): self.stack.enter_context(patch.object(module,'engine',self.engine))
            if hasattr(module,'SessionLocal'): self.stack.enter_context(patch.object(module,'SessionLocal',self.sessions))
        Base.metadata.create_all(self.engine)
        self.product='ProductName';self.display='CustomerName';self.join='CustomerID';self.rel=None
        with self.engine.begin() as c:
            c.execute(text(f'CREATE TABLE {O} (id INTEGER PRIMARY KEY, OrderID TEXT,CustomerID TEXT,ProductName TEXT)'))
            c.execute(text(f"INSERT INTO {O} VALUES (22,'O1','C-01','Kettle'),(33,'O2','C-01','Book'),(11,'O3','C-02','Shoes'),(44,'O4','C-03','Pen')"))
            c.execute(text(f'CREATE TABLE {C} (id INTEGER PRIMARY KEY,CustomerID TEXT,CustomerName TEXT)'))
            c.execute(text(f'INSERT INTO {C} VALUES (:id,:key,:name)'),[dict(id=11,key='C-01',name='Alice'),dict(id=22,key='C-02',name='Bob'),dict(id=33,key='C-03',name="Renée O'Neil")])
            c.execute(text('CREATE TABLE private_usr_9 (Name TEXT)'))
            c.execute(text("INSERT INTO private_usr_9 VALUES ('Alice')"))
        self.approve()

    def tearDown(self):
        self.stack.close();self.engine.dispose()

    def approve(self):
        ds={d['table_name']:d for d in service.catalog('usr_8')}
        req=routes.RelationshipRequest(name='Purchaser relationship',left_dataset_id=ds[O]['id'],right_dataset_id=ds[C]['id'],keys=[routes.Key(left=self.join,right=self.join)],approved=True)
        req.preview_digest=routes.preview('usr_8',req)['preview_digest']
        self.rel=routes.edit(self.rel['id'],req,'usr_8') if self.rel else routes.create(req,'usr_8')

    def sql(self,value,column=None,wrong_join=False,extra=''):
        literal="'"+value.replace("'","''")+"'"
        on='o.id=c.id' if wrong_join else f'o.`{self.join}`=c.`{self.join}`'
        return f'SELECT o.`{self.product}` FROM {O} o JOIN {C} c ON {on} WHERE c.`{column or self.display}`={literal} {extra} ORDER BY o.OrderID'

    def execute(self,sql):
        # Production emits MySQL; render its validated AST for the fixture engine
        # so apostrophe escaping is tested without assuming SQLite is MySQL.
        rendered=sqlglot.parse_one(sql,read='mysql').sql(dialect='sqlite')
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(text(rendered))]

    def query(self,question,value,initial=None,active=O):
        with patch.object(sql_generator,'call_llm',return_value=initial or self.sql(value)) as generator,patch.object(sql_regenerator,'call_llm',return_value=self.sql(value)) as repair,patch.object(ask,'execute_sql',side_effect=self.execute) as execute,patch.object(ask,'generate_summary',return_value='Purchased products.'):
            result=ask.ask_question(ask.AskRequest(question=question),active,'usr_8')
        return result,generator,repair,execute

    def test_equivalent_questions_and_paraphrases_for_different_names(self):
        people=[('Alice',['Kettle','Book']),('Bob',['Shoes']),("Renée O'Neil",['Pen'])]
        for name,products in people:
            questions=[f'Give me the product name bought by {name}.',f'Give me the product name bought by customer name {name}.',f'Which product name did {name} purchase?',f'List ProductName purchased by {name}.',f'Which product names were purchased by {name}?']
            for question in questions:
                with self.subTest(name=name,question=question):
                    result,_,_,_=self.query(question,name)
                    self.assertTrue(result['success'],result)
                    self.assertFalse(result.get('needs_clarification'),result)
                    self.assertEqual([r[self.product] for r in result['result']],products)
                    self.assertEqual(set(result['resolved_datasets']),{O,C})
                    self.assertEqual(result['join_explanation']['relationships'][0]['keys'],[{'left':self.join,'right':self.join}])

    def test_wrong_identifier_filter_is_repaired_before_execution(self):
        result,generator,repair,execute=self.query('Give me the product name bought by Alice.','Alice',initial=self.sql('alice',column=self.join))
        self.assertTrue(result['success'],result)
        self.assertEqual(result['result'],[{'ProductName':'Kettle'},{'ProductName':'Book'}])
        repair.assert_called_once();execute.assert_called_once()
        self.assertIn('MEASURED FILTER BINDINGS',generator.call_args.args[1])
        self.assertIn(self.display,repair.call_args.args[1])
        self.assertIn('not a guessed identifier',repair.call_args.args[1])
        self.assertNotIn("CustomerID` = 'alice'",execute.call_args.args[0])

    def test_repeat_wrong_identifier_filter_never_executes(self):
        wrong=self.sql('alice',column=self.join)
        with patch.object(sql_generator,'call_llm',return_value=wrong),patch.object(sql_regenerator,'call_llm',return_value=wrong),patch.object(ask,'execute_sql') as execute:
            result=ask.ask_question(ask.AskRequest(question='Give me the product name bought by Alice.'),O,'usr_8')
        self.assertFalse(result['success']);execute.assert_not_called()
        self.assertIn(self.display,result['error'])

    def test_generic_id_join_is_blocked_despite_both_columns_existing(self):
        result,_,_,execute=self.query('Give me the product name bought by Alice.','Alice',initial=self.sql('Alice',wrong_join=True))
        self.assertFalse(result['success']);execute.assert_not_called()
        self.assertIn('approved relationship',result['error'])

    def test_renamed_display_product_and_join_columns(self):
        with self.engine.begin() as c:
            c.execute(text(f'ALTER TABLE {O} RENAME COLUMN ProductName TO PurchasedArticle'))
            c.execute(text(f'ALTER TABLE {C} RENAME COLUMN CustomerName TO PreferredLabel'))
            c.execute(text(f'ALTER TABLE {O} RENAME COLUMN CustomerID TO PartyRef'))
            c.execute(text(f'ALTER TABLE {C} RENAME COLUMN CustomerID TO PartyRef'))
        self.product='PurchasedArticle';self.display='PreferredLabel';self.join='PartyRef';self.approve()
        for name,products in [('Alice',['Kettle','Book']),('Bob',['Shoes'])]:
            for q in [f'Give me purchased article bought by {name}.',f'Give me purchased article bought by preferred label {name}.',f'Which PurchasedArticle did {name} purchase?']:
                with self.subTest(question=q):
                    r,_,_,_=self.query(q,name)
                    self.assertTrue(r['success'],r)
                    self.assertEqual([x[self.product] for x in r['result']],products)
                    self.assertEqual(r['value_bindings'][0]['column'],self.display)
                    self.assertEqual(r['join_explanation']['relationships'][0]['keys'],[{'left':'PartyRef','right':'PartyRef'}])

    def test_name_and_identifier_collision_requests_clarification(self):
        with self.engine.begin() as c:
            c.execute(text(f"INSERT INTO {C} VALUES (55,'Alice','Different')"))
            c.execute(text(f"INSERT INTO {O} VALUES (55,'O5','Alice','Bag')"))
        self.approve()
        result,generator,_,execute=self.query('Give me the product name bought by Alice.','Alice')
        self.assertTrue(result.get('needs_clarification'),result)
        self.assertTrue(result['clarification_id'].startswith('val_'))
        generator.assert_not_called();execute.assert_not_called()
        selected=next(o for o in result['options'] if self.display in o['label'])
        with patch.object(sql_generator,'call_llm',return_value=self.sql('Alice')),patch.object(ask,'execute_sql',side_effect=self.execute),patch.object(ask,'generate_summary',return_value='Products.'):
            r=metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=result['clarification_id'],selected_option_id=selected['id']),'usr_8')
        self.assertTrue(r['success'],r);self.assertEqual(len(r['result']),2)
        explicit,_,_,_=self.query('Give me the product name bought by customer name Alice.','Alice')
        self.assertTrue(explicit['success'],explicit);self.assertEqual(len(explicit['result']),2)

    def test_duplicate_names_request_identity_or_all_matching_records(self):
        with self.engine.begin() as c: c.execute(text(f"INSERT INTO {C} VALUES (66,'C-04','Alice')"))
        self.approve()
        r,_,_,_=self.query('Give me the product name bought by Alice.','Alice')
        self.assertTrue(r.get('needs_clarification'),r)
        self.assertTrue(any('all matching records' in o['label'] for o in r['options']))
        self.assertTrue(any('C-01' in o['label'] for o in r['options']))

    def test_malformed_value_choice_and_cross_owner_clarification_rejected(self):
        with self.assertRaises(GroundingError):
            from app.services.value_grounding import key
            resolve_values('usr_8','ProductName by Alice',O,{key('alice'):'not-a-candidate'})
        with self.engine.begin() as c: c.execute(text(f"INSERT INTO {C} VALUES (66,'C-04','Alice')"))
        self.approve()
        r,_,_,_=self.query('Give me the product name bought by Alice.','Alice')
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            metrics.resolve_clarification(metrics.ClarificationResolveRequest(clarification_id=r['clarification_id'],selected_option_id=r['options'][0]['id']),'usr_9')

    def test_filter_cannot_be_omitted_or_bypassed(self):
        b=resolve_values('usr_8','ProductName bought by Alice',O)
        sql=self.sql('Alice')
        for bad in [sql.replace("WHERE c.`CustomerName`='Alice'",''),sql.replace("='Alice'","='Alice' OR 1=1")]:
            with self.assertRaises(GroundingError):validate_bindings(bad,b)

    def test_numeric_identifier_does_not_coerce_a_name_to_zero(self):
        with self.engine.begin() as c:
            c.execute(text(f'DROP TABLE {O}'));c.execute(text(f'DROP TABLE {C}'))
            c.execute(text(f'CREATE TABLE {O} (id INTEGER PRIMARY KEY,OrderID TEXT,CustomerID INTEGER,ProductName TEXT)'))
            c.execute(text(f"INSERT INTO {O} VALUES (1,'N1',0,'Wrong'),(2,'N2',4,'Correct')"))
            c.execute(text(f'CREATE TABLE {C} (id INTEGER PRIMARY KEY,CustomerID INTEGER,CustomerName TEXT)'))
            c.execute(text(f"INSERT INTO {C} VALUES (1,0,'Bob'),(2,4,'Alice')"))
        self.approve()
        r,_,repair,execute=self.query('Give me the product name bought by Alice.','Alice',initial=self.sql('Alice',column=self.join))
        self.assertTrue(r['success'],r);repair.assert_called_once();execute.assert_called_once()
        self.assertEqual(r['result'],[{'ProductName':'Correct'}])

if __name__=='__main__':unittest.main()
