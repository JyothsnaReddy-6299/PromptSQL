"""Dataset selection regressions: schemas are context, not selected sources."""
import sys
import os
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services import relationship_service as service

DATASETS = [
    dict(id='header-id', name='qa_header_nov01', table_name='qa_header_nov01_usr_8', columns=[{'name':'order_key'},{'name':'amount'}]),
    dict(id='items-id', name='qa_items_nov01', table_name='qa_items_nov01_usr_8', columns=[{'name':'order_key'},{'name':'quantity'}]),
    dict(id='ecommerce-id', name='ecommerce_sales_dataset', table_name='ecommerce_sales_dataset_usr_8', columns=[{'name':'Total_Sales'},{'name':'Sales_Region'},{'name':'Quantity_Ordered'}]),
    dict(id='unrelated-id', name='orders_archive', table_name='orders_archive_usr_8', columns=[{'name':'Amount'},{'name':'revenue'},{'name':'order_key_old'}]),
]

def approved_order_customer_path(owner,tables,selected=None):
    if set(tables)!={'orders_usr_8','customers_usr_8'}:
        raise service.RelationshipError('No approved connection')
    return []


class DatasetResolutionTests(unittest.TestCase):
    def resolve(self, question, active='qa_header_nov01_usr_8'):
        with patch.object(service, 'catalog', return_value=DATASETS), patch.object(service, 'resolve_paths', return_value=[]) as paths:
            required,_=service.query_context('usr_8',question,active)
        return required,paths

    def test_single_table_does_not_select_case_variant_columns_elsewhere(self):
        required,paths=self.resolve('Show order_key, amount from this table')
        self.assertEqual(required,['qa_header_nov01_usr_8'])
        paths.assert_not_called()

    def test_generic_revenue_prefers_active_ecommerce(self):
        required,paths=self.resolve('Total revenue across all orders','ecommerce_sales_dataset_usr_8')
        self.assertEqual(required,['ecommerce_sales_dataset_usr_8'])
        paths.assert_not_called()

    def test_logical_catalog_id_and_physical_active_resolve_identically(self):
        for active in ['header-id','qa_header_nov01','qa_header_nov01_usr_8']:
            with self.subTest(active=active):
                self.assertEqual(self.resolve('Show order_key, amount from this table',active)[0],['qa_header_nov01_usr_8'])

    def test_explicit_single_dataset_does_not_force_active_into_join(self):
        self.assertEqual(self.resolve('Show order_key from qa_items_nov01')[0],['qa_items_nov01_usr_8'])

    def test_dataset_names_are_not_substrings(self):
        self.assertEqual(self.resolve('Show amount from qa_header_nov01_archive')[0],['qa_header_nov01_usr_8'])

    def test_common_business_nouns_do_not_select_tables(self):
        datasets=DATASETS+[dict(id='orders-id',name='orders',table_name='orders_usr_8',columns=[{'name':'order_key'}])]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths',return_value=[]) as paths:
            for q in ['Total revenue across all orders','Total revenue and orders']:
                self.assertEqual(service.query_context('usr_8',q,'ecommerce_sales_dataset_usr_8')[0],['ecommerce_sales_dataset_usr_8'])
        paths.assert_not_called()

    def test_column_name_substrings_are_not_references(self):
        self.assertEqual(self.resolve('Show amount_due from this table')[0],['qa_header_nov01_usr_8'])

    def test_explicit_both_names_require_only_the_pair(self):
        required,paths=self.resolve('Totals from qa_header_nov01 and qa_items_nov01')
        self.assertEqual(set(required),{'qa_header_nov01_usr_8','qa_items_nov01_usr_8'})
        paths.assert_called_once()

    def test_ambiguous_missing_column_asks_instead_of_joining_every_candidate(self):
        datasets=DATASETS+[dict(id='other-items',name='other_items',table_name='other_items_usr_8',columns=[{'name':'quantity'}])]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths') as paths:
            with self.assertRaises(service.DatasetChoice) as choice:
                service.query_context('usr_8','Show quantity','qa_header_nov01_usr_8')
        self.assertEqual(len(choice.exception.options),3)
        paths.assert_not_called()

    def test_active_semantic_fields_win_over_literal_columns_elsewhere(self):
        datasets=DATASETS+[dict(id='extra',name='extra',table_name='extra_usr_8',columns=[{'name':'region'},{'name':'quantity'},{'name':'amount'}])]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths') as paths:
            for q in ['Revenue by region','Total revenue and quantity','Show amount']:
                self.assertEqual(service.query_context('usr_8',q,'ecommerce_sales_dataset_usr_8')[0],['ecommerce_sales_dataset_usr_8'])
        paths.assert_not_called()

    def test_active_without_requested_metric_asks_for_source(self):
        with patch.object(service,'catalog',return_value=DATASETS),patch.object(service,'resolve_paths') as paths:
            with self.assertRaises(service.DatasetChoice):
                service.query_context('usr_8','Total revenue','qa_items_nov01_usr_8')
        paths.assert_not_called()

    def test_longer_explicit_dataset_name_does_not_select_its_prefix(self):
        datasets=DATASETS+[dict(id='short',name='qa_header',table_name='qa_header_usr_8',columns=[{'name':'amount'}])]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths') as paths:
            self.assertEqual(service.query_context('usr_8','Total amount from qa_header_nov01','qa_items_nov01_usr_8')[0],['qa_header_nov01_usr_8'])
        paths.assert_not_called()

    def test_order_output_and_customer_filter_do_not_require_active_ecommerce(self):
        datasets = [
            dict(id='orders',name='orders',table_name='orders_usr_8',columns=[{'name':'Order IDs'},{'name':'Customer ID'}]),
            dict(id='customers',name='customers',table_name='customers_usr_8',columns=[{'name':'Customer ID'},{'name':'Membership'}]),
            dict(id='commerce',name='ecommerce_sales_dataset',table_name='ecommerce_sales_dataset_usr_8',columns=[{'name':'Order_IDs'},{'name':'Total_Sales'}]),
        ]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths',side_effect=approved_order_customer_path) as paths:
            tables,_=service.query_context('usr_8','Give me order IDs whose membership is Gold.','ecommerce_sales_dataset_usr_8')
        self.assertEqual(set(tables),{'orders_usr_8','customers_usr_8'})
        self.assertTrue(any(set(call.args[1])=={'orders_usr_8','customers_usr_8'} for call in paths.call_args_list))

    def test_compact_orderid_does_not_omit_orders(self):
        datasets=[
            dict(id='orders',name='orders',table_name='orders_usr_8',columns=[{'name':'OrderID'},{'name':'CustomerID'}]),
            dict(id='customers',name='customers',table_name='customers_usr_8',columns=[{'name':'CustomerID'},{'name':'Membership'}]),
            dict(id='commerce',name='ecommerce_sales_dataset',table_name='ecommerce_sales_dataset_usr_8',columns=[{'name':'Order_ID'}]),
        ]
        with patch.object(service,'catalog',return_value=datasets),patch.object(service,'resolve_paths',side_effect=approved_order_customer_path) as paths:
            tables,_=service.query_context('usr_8','Give me order ID whose membership is gold.','ecommerce_sales_dataset_usr_8')
        self.assertEqual(set(tables),{'orders_usr_8','customers_usr_8'})

if __name__ == '__main__': unittest.main()
