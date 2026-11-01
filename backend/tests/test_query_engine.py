"""Query-engine regressions: real SQL execution with isolated SQLite fixtures."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sqlalchemy import create_engine, text
from fastapi import HTTPException
from app.services import sql_validator as validator
from app.services.metric_parser import validate_and_compile_expression
from app.services.aggregate_summary import format_value
from app.services import query_planner as planner
from app.routes import ask


class QueryEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.table = 'sales_usr_1'
        self.columns = ['id', 'Sales Region', 'Quantity Ordered', 'Total Sales Amount', 'Unit Price']
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE sales_usr_1 (id INTEGER, `Sales Region` TEXT, `Quantity Ordered` REAL, `Total Sales Amount` REAL, `Unit Price` REAL)'))
            conn.execute(text("INSERT INTO sales_usr_1 VALUES (1, 'North', 2, 100, 50), (2, 'South', 5, 200, 40), (3, 'North', 3, 150, 50)"))
        self.patch = patch.object(validator, 'engine', self.engine)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()

    def prepare(self, sql):
        return validator.prepare_sql(sql, [self.table])

    def test_total_revenue_alias_executes(self):
        sql = self.prepare('SELECT SUM(`Total Sales Amount`) AS `Total Revenue` FROM sales ORDER BY `Total Revenue`')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(sql)).scalar(), 450)

    def test_mysql_column_case_insensitivity(self):
        self.prepare('SELECT SUM(`total sales amount`) AS `Total Revenue` FROM sales ORDER BY `total revenue`')

    def test_cte_aliases_and_join(self):
        sql = self.prepare('WITH totals AS (SELECT `Sales Region`, SUM(`Total Sales Amount`) AS revenue FROM sales GROUP BY `Sales Region`) SELECT t.revenue FROM totals t ORDER BY t.revenue DESC')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(sql)).scalar(), 250)
        self.prepare('SELECT a.id FROM sales a JOIN sales b ON a.id = b.id')

    def test_literals_are_not_columns_or_table_references(self):
        sql = self.prepare("SELECT 'sales', 'DROP TABLE users', 'users' FROM sales")
        self.assertIn("'sales'", sql)
        self.assertIn("'DROP TABLE users'", sql)

    def test_unknown_columns_including_unquoted_are_rejected(self):
        for sql in ['SELECT missing FROM sales', 'SELECT SUM(`No Revenue`) AS revenue FROM sales', 'SELECT a.missing FROM sales a']:
            with self.subTest(sql=sql), self.assertRaises(Exception):
                self.prepare(sql)

    def test_unauthorized_tables_and_side_effects_rejected(self):
        for sql in ['SELECT * FROM users', 'SELECT * FROM other_usr_2', 'SELECT * FROM mysql.user', 'SELECT * FROM sales; SELECT 1', 'DELETE FROM sales', 'SELECT SLEEP(5)', 'SELECT @x := 1', "SELECT * INTO OUTFILE '/tmp/leak' FROM sales", 'SELECT * FROM sales FOR UPDATE', 'SELECT * FROM sales UNION SELECT * FROM users']:
            with self.subTest(sql=sql), self.assertRaises(Exception):
                self.prepare(sql)

    def test_quantity_is_not_its_own_group(self):
        with patch.object(planner, 'get_authorized_dataset_columns', return_value=self.columns), patch.object(planner, 'list_metrics', return_value=[]), patch.object(planner, 'get_default_metric', return_value=None):
            plan = planner.resolve_or_create_plan('What is total quantity ordered?', self.table, 'usr_1')['plan']
        self.assertEqual(plan['grouping_dimensions'], [])
        sql, params = planner.compile_plan_to_sql(plan, self.table, self.columns)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text(sql), params).scalar(), 10)

    def test_spaced_revenue_and_explicit_average(self):
        with patch.object(planner, 'get_authorized_dataset_columns', return_value=self.columns), patch.object(planner, 'list_metrics', return_value=[]), patch.object(planner, 'get_default_metric', return_value=None):
            plan = planner.resolve_or_create_plan('What is average revenue?', self.table, 'usr_1')['plan']
        self.assertEqual(plan['metric_aggregation'], 'AVG')
        self.assertEqual(plan['metric_expression'], 'Total Sales Amount')

    def test_filter_column_does_not_become_dimension(self):
        dims = planner.extract_dimensions_and_grouping('Total revenue where Sales Region is North', self.columns, ['Total Sales Amount'])
        self.assertEqual(dims, [])
        self.assertEqual(planner.extract_dimensions_and_grouping('Total revenue by region?', self.columns, ['Total Sales Amount']), ['Sales Region'])

    def test_complex_questions_defer_instead_of_losing_conditions(self):
        with patch.object(planner, 'get_authorized_dataset_columns', return_value=self.columns):
            for question in ['Show all quantity ordered', 'Total revenue monthly', 'Total revenue where quantity > 3', 'Compare revenue between regions']:
                with self.subTest(question=question), self.assertRaises(planner.PlanCompilationError):
                    planner.resolve_or_create_plan(question, self.table, 'usr_1')

    def test_compiler_rejects_client_sql_fragments(self):
        plan = dict(metric_expression='Total Sales Amount', metric_name='Revenue', filters=[], ordering={'target': 'metric'})
        for change in [dict(filters=[dict(column='id', operator='= 1 OR 1 =', value=1)]), dict(ordering={'target': 'id` DESC; SELECT 1 --'}), dict(limit=-1), dict(limit=True)]:
            with self.subTest(change=change), self.assertRaises(planner.PlanCompilationError):
                planner.compile_plan_to_sql(dict(plan, **change), self.table, self.columns)

    def test_missing_aggregate_is_not_reported_as_zero(self):
        self.assertEqual(format_value(None), 'not available')

    def test_multiple_explicit_dimensions(self):
        self.assertEqual(planner.extract_dimensions_and_grouping(
            'Total revenue by region and category',
            ['Sales Region', 'Product Category', 'Total Sales Amount'],
            ['Total Sales Amount']), ['Sales Region', 'Product Category'])

    def test_constant_expression_produces_valid_sql(self):
        sql, _ = validate_and_compile_expression('1', self.columns, 'SUM')
        self.assertEqual(sql, 'SUM(1)')

    def test_execution_error_is_repaired_and_revalidated(self):
        with patch.object(ask, 'engine', self.engine), patch.object(ask, 'resolve_or_create_plan', side_effect=planner.PlanCompilationError('fallback')), patch.object(ask, 'generate_sql', return_value='SELECT id FROM sales'), patch.object(ask, 'regenerate_sql', return_value='SELECT id FROM sales ORDER BY id'), patch.object(ask, 'execute_sql', side_effect=[Exception('temporary SQL execution error'), [{'id': 1}]]), patch.object(ask, 'generate_summary', side_effect=Exception('summary unavailable')), patch.object(ask, 'SessionLocal', return_value=MagicMock()):
            result = ask.ask_question(ask.AskRequest(question='Show records'), self.table, 'usr_1')
        self.assertTrue(result['success'])
        self.assertEqual(result['result'], [{'id': 1}])
        self.assertIn('1 matching records', result['summary'])

    def test_invalid_repair_never_executes(self):
        with patch.object(ask, 'engine', self.engine), patch.object(ask, 'resolve_or_create_plan', side_effect=planner.PlanCompilationError('fallback')), patch.object(ask, 'generate_sql', return_value='SELECT missing FROM sales'), patch.object(ask, 'regenerate_sql', return_value='DELETE FROM sales'), patch.object(ask, 'execute_sql') as execute:
            result = ask.ask_question(ask.AskRequest(question='Show records'), self.table, 'usr_1')
        self.assertFalse(result['success'])
        execute.assert_not_called()

    def test_system_table_request_is_forbidden(self):
        with self.assertRaises(HTTPException) as context:
            ask.ask_question(ask.AskRequest(question='Show records'), 'users', 'usr_1')
        self.assertEqual(context.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
