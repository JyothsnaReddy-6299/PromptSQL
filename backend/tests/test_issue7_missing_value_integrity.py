import unittest
import io
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database.connection import engine
from app.services.upload_service import upload_dataset
from app.services.auth_service import create_access_token


class TestIssue7MissingValueIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.user_num = 99820
        cls.user_id = f"usr_{cls.user_num}"
        cls.token = create_access_token(cls.user_num)
        cls.headers = {
            "Authorization": f"Bearer {cls.token}",
            "X-User-ID": cls.user_id
        }

        # Create test CSV & Excel data
        cls.csv_content = (
            "id,product_code,product_name,category,price,launch_date\n"
            "1,P-101,Keyboard,Electronics,120.00,2026-01-15\n"
            "2,P-102,,,null,\n"
            "3,P-103,nan,None,NaN,None\n"
            "4,P-104,None,Hardware,None,null\n"
            "5,P-105,null,NaN,85.50,2026-02-20\n"
            "6,P-106,Mouse,\"nan\",45.00,2026-03-01\n"
            "7,P-107,Monitor,\"None\",250.00,2026-03-15\n"
        )

        df_raw = pd.read_csv(io.StringIO(cls.csv_content), keep_default_na=False)
        cls.csv_path = "backend/tests/test_missing_dataset_temp.csv"
        cls.excel_path = "backend/tests/test_missing_dataset_temp.xlsx"
        
        with open(cls.csv_path, "w", encoding="utf-8") as f:
            f.write(cls.csv_content)
        df_raw.to_excel(cls.excel_path, index=False)

    @classmethod
    def tearDownClass(cls):
        import os
        for p in [cls.csv_path, cls.excel_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def setUp(self):
        # Cleanly upload CSV and Excel for the test user
        self.csv_res = upload_dataset(self.csv_path, "issue7_csv.csv", user_id=self.user_id)
        self.csv_table = self.csv_res["table_name"]

        self.excel_res = upload_dataset(self.excel_path, "issue7_excel.xlsx", user_id=self.user_id)
        self.excel_table = self.excel_res["table_name"]

    def test_stage1_file_upload_and_type_detection(self):
        """Stage 1: Verify type detection detects numeric & date despite missing values, and missing values count is accurate."""
        for res, label in [(self.csv_res, "CSV"), (self.excel_res, "Excel")]:
            types = res["detected_types"]
            self.assertEqual(types.get("price"), "numeric", f"{label} price should be numeric")
            self.assertEqual(types.get("launch_date"), "date", f"{label} launch_date should be date")
            self.assertEqual(types.get("product_name"), "text", f"{label} product_name should be text")
            self.assertEqual(types.get("category"), "text", f"{label} category should be text")
            # Total missing values across the 7 rows:
            # Row 1: 0 missing
            # Row 2: product_name, category, price, launch_date (4 missing)
            # Row 3: price, launch_date (2 missing) [nan and None in product_name/category are text!]
            # Row 4: price, launch_date (2 missing) [None in product_name is text!]
            # Row 5: product_name, category (2 missing)
            # Row 6: 0 missing [nan in category is text!]
            # Row 7: 0 missing [None in category is text!]
            # Total missing = 4 + 2 + 2 + 2 = 10
            self.assertEqual(res["missing_values"], 10, f"{label} missing values count should be 10, got {res['missing_values']}")

    def test_stage2_database_storage_fidelity(self):
        """Stage 2: Verify database stores SQL NULL for missing values, and literal strings for 'nan' and 'None'."""
        with engine.connect() as conn:
            for tbl in [self.csv_table, self.excel_table]:
                rows = conn.execute(text(
                    f"SELECT id, product_name, category, price, launch_date, "
                    f"product_name IS NULL as name_is_null, "
                    f"category IS NULL as cat_is_null, "
                    f"price IS NULL as price_is_null "
                    f"FROM `{tbl}` ORDER BY CAST(id AS UNSIGNED) ASC"
                )).fetchall()

                # Row 1: Keyboard, Electronics, 120.0
                r1 = rows[0]
                self.assertEqual(r1.product_name, "Keyboard")
                self.assertEqual(r1.category, "Electronics")
                self.assertEqual(r1.price, 120.0)
                self.assertEqual(r1.name_is_null, 0)
                self.assertEqual(r1.price_is_null, 0)

                # Row 2: Empty cell -> SQL NULL
                r2 = rows[1]
                self.assertIsNone(r2.product_name)
                self.assertIsNone(r2.category)
                self.assertIsNone(r2.price)
                self.assertIsNone(r2.launch_date)
                self.assertEqual(r2.name_is_null, 1)
                self.assertEqual(r2.cat_is_null, 1)
                self.assertEqual(r2.price_is_null, 1)

                # Row 3: 'nan' and 'None' are literal strings; price & launch_date are NULL
                r3 = rows[2]
                self.assertEqual(r3.product_name, "nan")
                self.assertEqual(r3.category, "None")
                self.assertIsNone(r3.price)
                self.assertIsNone(r3.launch_date)
                self.assertEqual(r3.name_is_null, 0)
                self.assertEqual(r3.cat_is_null, 0)
                self.assertEqual(r3.price_is_null, 1)

                # Row 4: 'None' in product_name is literal string
                r4 = rows[3]
                self.assertEqual(r4.product_name, "None")
                self.assertEqual(r4.category, "Hardware")
                self.assertIsNone(r4.price)
                self.assertEqual(r4.name_is_null, 0)
                self.assertEqual(r4.price_is_null, 1)

                # Row 5: 'null' and 'NaN' became SQL NULL
                r5 = rows[4]
                self.assertIsNone(r5.product_name)
                self.assertIsNone(r5.category)
                self.assertEqual(r5.price, 85.5)
                self.assertEqual(r5.name_is_null, 1)
                self.assertEqual(r5.price_is_null, 0)

                # Row 6: Mouse, 'nan' (string), 45.0
                r6 = rows[5]
                self.assertEqual(r6.product_name, "Mouse")
                self.assertEqual(r6.category, "nan")
                self.assertEqual(r6.price, 45.0)
                self.assertEqual(r6.cat_is_null, 0)

                # Row 7: Monitor, 'None' (string), 250.0
                r7 = rows[6]
                self.assertEqual(r7.product_name, "Monitor")
                self.assertEqual(r7.category, "None")
                self.assertEqual(r7.price, 250.0)
                self.assertEqual(r7.cat_is_null, 0)

    def test_stage3_table_preview_api_serialization(self):
        """Stage 3: Verify /preview endpoint returns JSON null for missing values and preserves legitimate strings."""
        headers = dict(self.headers)
        headers["x-table-name"] = self.csv_table

        res = self.client.get("/preview", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        records = data["records"]
        self.assertEqual(len(records), 7)

        # Row 2 should have None (JSON null)
        self.assertIsNone(records[1]["product_name"])
        self.assertIsNone(records[1]["category"])
        self.assertIsNone(records[1]["price"])
        self.assertIsNone(records[1]["launch_date"])

        # Row 3 should have literal string "nan" and "None"
        self.assertEqual(records[2]["product_name"], "nan")
        self.assertEqual(records[2]["category"], "None")
        self.assertIsNone(records[2]["price"])

        # Search for null should return rows with missing values
        res_search = self.client.get("/preview?search=null", headers=headers)
        self.assertEqual(res_search.status_code, 200)
        search_records = res_search.json()["records"]
        # Rows 2, 3, 4, 5 have NULL values in at least one column
        self.assertTrue(len(search_records) >= 4)

    def test_stage4_natural_language_and_sql_aggregations(self):
        """Stage 4: Verify SQL aggregations (COUNT, AVG) and NULL comparisons behave correctly."""
        with engine.connect() as conn:
            # 1. Total count
            total_rows = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}`")).scalar()
            self.assertEqual(total_rows, 7)

            # 2. Non-null count of numeric column
            non_null_price_count = conn.execute(text(f"SELECT COUNT(price) FROM `{self.csv_table}`")).scalar()
            self.assertEqual(non_null_price_count, 4)

            # 3. AVG of numeric column ignores NULLs: (120 + 85.5 + 45 + 250) / 4 = 125.125
            avg_price = conn.execute(text(f"SELECT AVG(price) FROM `{self.csv_table}`")).scalar()
            self.assertAlmostEqual(float(avg_price), 125.125, places=3)

            # 4. IS NULL vs IS NOT NULL
            null_names = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name IS NULL")).scalar()
            self.assertEqual(null_names, 2)

            not_null_names = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name IS NOT NULL")).scalar()
            self.assertEqual(not_null_names, 5)

            # 5. Legitimate text value lookups
            nan_text = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name = 'nan'")).scalar()
            self.assertEqual(nan_text, 1)

            none_text = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name = 'None'")).scalar()
            self.assertEqual(none_text, 1)

    def test_stage5_data_cleaning_locate_and_impute(self):
        """Stage 5: Verify data cleaning locate-missing and impute handle NULLs without corrupting legitimate text."""
        headers = dict(self.headers)
        headers["x-table-name"] = self.csv_table

        # 1. Locate missing in product_name: only 2 missing
        loc_name = self.client.get("/api/clean/locate-missing?column_name=product_name", headers=headers)
        self.assertEqual(loc_name.status_code, 200)
        self.assertEqual(loc_name.json()["total_missing"], 2)

        # 2. Locate missing in price: 3 missing
        loc_price = self.client.get("/api/clean/locate-missing?column_name=price", headers=headers)
        self.assertEqual(loc_price.status_code, 200)
        self.assertEqual(loc_price.json()["total_missing"], 3)

        # 3. Impute price with mean
        imp_res = self.client.post("/api/clean/impute", json={
            "column_name": "price",
            "strategy": "mean"
        }, headers=headers)
        self.assertEqual(imp_res.status_code, 200)
        self.assertEqual(imp_res.json()["rows_affected"], 3)

        # Verify price now has 0 missing
        loc_price_after = self.client.get("/api/clean/locate-missing?column_name=price", headers=headers)
        self.assertEqual(loc_price_after.json()["total_missing"], 0)

        # Verify legitimate text was NOT affected
        with engine.connect() as conn:
            cnt_nan = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name = 'nan'")).scalar()
            cnt_none = conn.execute(text(f"SELECT COUNT(*) FROM `{self.csv_table}` WHERE product_name = 'None'")).scalar()
            self.assertEqual(cnt_nan, 1)
            self.assertEqual(cnt_none, 1)

    def test_stage6_export_raw_csv_and_excel(self):
        """Stage 6: Verify raw exports represent NULLs as empty cells and preserve legitimate strings."""
        headers = dict(self.headers)
        headers["x-table-name"] = self.csv_table

        # Export CSV
        res_csv = self.client.get("/api/export/raw/csv", headers=headers)
        self.assertEqual(res_csv.status_code, 200)
        csv_text = res_csv.content.decode("utf-8")
        
        # Read back exported CSV with keep_default_na=False
        df_exp_csv = pd.read_csv(io.StringIO(csv_text), keep_default_na=False)
        # Row 2 (index 1) product_name should be empty string
        self.assertEqual(df_exp_csv.loc[1, "product_name"], "")
        # Row 3 (index 2) product_name should be "nan"
        self.assertEqual(df_exp_csv.loc[2, "product_name"], "nan")
        # Row 4 (index 3) product_name should be "None"
        self.assertEqual(df_exp_csv.loc[3, "product_name"], "None")

        # Export Excel
        res_xl = self.client.get("/api/export/raw/excel", headers=headers)
        self.assertEqual(res_xl.status_code, 200)
        excel_bytes = res_xl.content

        # Read back exported Excel with keep_default_na=False
        df_exp_xl = pd.read_excel(io.BytesIO(excel_bytes), keep_default_na=False)
        self.assertEqual(df_exp_xl.loc[1, "product_name"], "")
        self.assertEqual(df_exp_xl.loc[2, "product_name"], "nan")
        self.assertEqual(df_exp_xl.loc[3, "product_name"], "None")

    def test_stage7_focused_none_conversion_and_matrix_verification(self):
        """Stage 7 (Issue 7.1): Verify 'None', 'nan', 'null', and empty cells across numeric, date, and text columns."""
        matrix_csv = (
            "id,amount,launch_date,category\n"
            "1,100,2026-01-01,ValidText\n"
            "2,None,None,None\n"
            "3,nan,nan,nan\n"
            "4,null,null,null\n"
            "5,,,\n"
        )
        csv_tmp = "backend/tests/matrix_test.csv"
        xl_tmp = "backend/tests/matrix_test.xlsx"
        try:
            with open(csv_tmp, "w", encoding="utf-8") as f:
                f.write(matrix_csv)
            pd.read_csv(io.StringIO(matrix_csv), keep_default_na=False).to_excel(xl_tmp, index=False)

            res_c = upload_dataset(csv_tmp, "matrix_csv.csv", user_id=self.user_id)
            res_x = upload_dataset(xl_tmp, "matrix_xl.xlsx", user_id=self.user_id)

            for res, label in [(res_c, "CSV"), (res_x, "Excel")]:
                tbl = res["table_name"]
                types = res["detected_types"]
                self.assertEqual(types.get("amount"), "numeric", f"{label} amount must be numeric")
                self.assertEqual(types.get("launch_date"), "date", f"{label} launch_date must be date")
                self.assertEqual(types.get("category"), "text", f"{label} category must be text")

                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT id, amount, launch_date, category,
                               amount IS NULL AS amount_is_null,
                               launch_date IS NULL AS date_is_null,
                               category IS NULL AS category_is_null
                        FROM `{tbl}` ORDER BY CAST(id AS UNSIGNED) ASC
                    """)).fetchall()

                    # Row 1: Valid values
                    self.assertEqual(rows[0].amount, 100.0)
                    self.assertIsNotNone(rows[0].launch_date)
                    self.assertEqual(rows[0].category, "ValidText")

                    # Row 2: 'None' -> SQL NULL in numeric & date, preserved as string 'None' in text
                    self.assertIsNone(rows[1].amount, f"{label} numeric 'None' must be SQL NULL")
                    self.assertEqual(rows[1].amount_is_null, 1)
                    self.assertIsNone(rows[1].launch_date, f"{label} date 'None' must be SQL NULL")
                    self.assertEqual(rows[1].date_is_null, 1)
                    self.assertEqual(rows[1].category, "None", f"{label} text 'None' must remain string 'None'")
                    self.assertEqual(rows[1].category_is_null, 0)

                    # Row 3: 'nan' -> SQL NULL in numeric & date, preserved as string 'nan' in text
                    self.assertIsNone(rows[2].amount, f"{label} numeric 'nan' must be SQL NULL")
                    self.assertEqual(rows[2].amount_is_null, 1)
                    self.assertIsNone(rows[2].launch_date, f"{label} date 'nan' must be SQL NULL")
                    self.assertEqual(rows[2].date_is_null, 1)
                    self.assertEqual(rows[2].category, "nan", f"{label} text 'nan' must remain string 'nan'")
                    self.assertEqual(rows[2].category_is_null, 0)

                    # Row 4: 'null' -> SQL NULL across all columns
                    self.assertIsNone(rows[3].amount, f"{label} numeric 'null' must be SQL NULL")
                    self.assertEqual(rows[3].amount_is_null, 1)
                    self.assertIsNone(rows[3].launch_date, f"{label} date 'null' must be SQL NULL")
                    self.assertEqual(rows[3].date_is_null, 1)
                    self.assertIsNone(rows[3].category, f"{label} text 'null' must be SQL NULL")
                    self.assertEqual(rows[3].category_is_null, 1)

                    # Row 5: empty cell -> SQL NULL across all columns
                    self.assertIsNone(rows[4].amount, f"{label} numeric empty cell must be SQL NULL")
                    self.assertEqual(rows[4].amount_is_null, 1)
                    self.assertIsNone(rows[4].launch_date, f"{label} date empty cell must be SQL NULL")
                    self.assertEqual(rows[4].date_is_null, 1)
                    self.assertIsNone(rows[4].category, f"{label} text empty cell must be SQL NULL")
                    self.assertEqual(rows[4].category_is_null, 1)
        finally:
            import os
            for p in [csv_tmp, xl_tmp]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass


if __name__ == "__main__":
    unittest.main()
