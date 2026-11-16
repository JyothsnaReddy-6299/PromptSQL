"""
PromptSQL — Issue 18.1: Automatic Excel Header Detection and Ingestion Test Suite

Tests the 10 core scenarios for fully automatic Excel header detection without manual preview:
1. Single-sheet workbook with headers in row 1.
2. Single-sheet workbook with headers in row 3.
3. Single-sheet workbook with headers in row 5.
4. Workbook with merged title cells.
5. Workbook with multiple worksheets, one containing the actual dataset (Instructions + Data).
6. Workbook with multiple equally plausible data worksheets (returns clear upload error).
7. Ambiguous header candidates (stops import and returns clear upload error).
8. CSV upload regression (CSV uploads remain 100% functional).
9. Privacy Guardian integration (sensitive data protected for AI while original in DB).
10. Tenant isolation and atomic staging table swap.
"""

import unittest
import os
import shutil
import tempfile
import uuid
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import pandas as pd
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password, create_access_token
from app.services.excel_header_service import (
    get_excel_sheet_names,
    detect_merged_title_rows,
    detect_header_row,
    auto_select_excel_worksheet,
    normalize_column_names,
    load_excel_with_detected_header,
)
from app.services.upload_service import upload_dataset
from app.services.privacy_service import scan_and_save_dataset_privacy, get_dataset_column_policies


class TestIssue181AutoExcelDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        cls.temp_dir = tempfile.mkdtemp(prefix="promptsql_i18_1_test_")

        # Test user A
        cls.test_username_a = f"i18_1_user_a_{uuid.uuid4().hex[:8]}"
        cls.user_a = User(
            username=cls.test_username_a,
            password_hash=hash_password("TestPassword123!")
        )
        cls.db.add(cls.user_a)

        # Test user B
        cls.test_username_b = f"i18_1_user_b_{uuid.uuid4().hex[:8]}"
        cls.user_b = User(
            username=cls.test_username_b,
            password_hash=hash_password("TestPassword123!")
        )
        cls.db.add(cls.user_b)

        cls.db.commit()
        cls.db.refresh(cls.user_a)
        cls.db.refresh(cls.user_b)

        cls.user_id_a = f"usr_{cls.user_a.id}"
        cls.user_id_b = f"usr_{cls.user_b.id}"

        cls.token_a = create_access_token(cls.user_a.id)
        cls.headers_a = {"Authorization": f"Bearer {cls.token_a}"}

        cls.token_b = create_access_token(cls.user_b.id)
        cls.headers_b = {"Authorization": f"Bearer {cls.token_b}"}

        cls.created_tables = []

    @classmethod
    def tearDownClass(cls):
        try:
            with engine.begin() as conn:
                for tbl in cls.created_tables:
                    conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
        except Exception:
            pass

        try:
            cls.db.query(User).filter(User.id.in_([cls.user_a.id, cls.user_b.id])).delete(synchronize_session=False)
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        finally:
            cls.db.close()

        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Single-sheet workbook with headers in row 1
    # -------------------------------------------------------------------------
    def test_01_single_sheet_headers_row_1(self):
        """Headers in row 1 are detected and ingested automatically without manual configuration."""
        wb_path = os.path.join(self.temp_dir, "scenario1_row1.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sales"
        ws.append(["order_id", "customer_name", "amount", "order_date"])
        ws.append(["ORD101", "Alice Smith", 120.50, "2024-01-10"])
        ws.append(["ORD102", "Bob Jones", 450.00, "2024-01-11"])
        ws.append(["ORD103", "Charlie Day", 75.25, "2024-01-12"])
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("sales_row1.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["header_row"], 1)
        self.assertEqual(data["rows"], 3)
        self.assertEqual(data["columns"], 4)
        self.assertEqual(list(data["detected_types"].keys()), ["order_id", "customer_name", "amount", "order_date"])

    # -------------------------------------------------------------------------
    # 2. Single-sheet workbook with headers in row 3
    # -------------------------------------------------------------------------
    def test_02_single_sheet_headers_row_3(self):
        """Title on row 1, description on row 2, headers on row 3 ingested automatically."""
        wb_path = os.path.join(self.temp_dir, "scenario2_row3.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventory"
        ws.append(["Enterprise Inventory & Warehouse Stock Report"])                     # Row 1: Title
        ws.append(["All stock quantities verified as of FY2024 Q1 close."])              # Row 2: Description
        ws.append(["sku", "product_name", "category", "unit_cost", "stock_qty"])        # Row 3: Headers
        ws.append(["SKU-100", "Wireless Mouse", "Electronics", 15.50, 250])              # Row 4: Data
        ws.append(["SKU-200", "Mechanical Keyboard", "Electronics", 65.00, 120])         # Row 5: Data
        ws.append(["SKU-300", "USB-C Hub", "Accessories", 22.00, 85])                   # Row 6: Data
        ws.append(["SKU-400", "Desk Pad", "Office Supplies", 12.00, 310])                # Row 7: Data
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("inventory_row3.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["header_row"], 3)
        self.assertEqual(data["rows"], 4)
        self.assertEqual(data["columns"], 5)
        self.assertEqual(list(data["detected_types"].keys()), ["sku", "product_name", "category", "unit_cost", "stock_qty"])

    # -------------------------------------------------------------------------
    # 3. Single-sheet workbook with headers in row 5
    # -------------------------------------------------------------------------
    def test_03_single_sheet_headers_row_5(self):
        """Introductory metadata, report notes, and empty rows preceding headers in row 5."""
        wb_path = os.path.join(self.temp_dir, "scenario3_row5.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Financials"
        ws.append(["ACME Corporation - Internal Ledger Report"])                        # Row 1
        ws.append(["Fiscal Period: Q1 2024 | Generated: 2024-03-31"])                   # Row 2
        ws.append(["Strictly Confidential: For authorized financial personnel only."])  # Row 3
        ws.append([])                                                                    # Row 4: Blank
        ws.append(["transaction_id", "account_id", "txn_type", "amount", "balance_after"]) # Row 5: Headers
        ws.append(["TX1001", "ACC-901", "CREDIT", 5000.00, 15000.00])                   # Row 6: Data
        ws.append(["TX1002", "ACC-902", "DEBIT", 1200.50, 3400.00])                     # Row 7: Data
        ws.append(["TX1003", "ACC-901", "DEBIT", 850.00, 14150.00])                     # Row 8: Data
        ws.append(["TX1004", "ACC-903", "CREDIT", 2300.00, 8900.00])                    # Row 9: Data
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("financials_row5.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["header_row"], 5)
        self.assertEqual(data["rows"], 4)

    # -------------------------------------------------------------------------
    # 4. Workbook with merged title cells
    # -------------------------------------------------------------------------
    def test_04_merged_title_cells(self):
        """Merged title banner cell across A1:D1 is ignored and headers in row 2 are selected."""
        wb_path = os.path.join(self.temp_dir, "scenario4_merged.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Equipment"
        ws.merge_cells("A1:D1")
        ws["A1"] = "REGIONAL EQUIPMENT & ASSET REGISTER"
        ws["A1"].font = Font(size=14, bold=True)
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.append(["asset_id", "asset_name", "branch", "acquisition_value"])  # Row 2: Headers
        ws.append(["AST-01", "Forklift Model X", "Chicago", 45000])           # Row 3: Data
        ws.append(["AST-02", "Pallet Jack", "Chicago", 1200])                 # Row 4: Data
        ws.append(["AST-03", "Conveyor Belt", "Dallas", 78000])               # Row 5: Data
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("equipment_merged.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["header_row"], 2)
        self.assertEqual(data["rows"], 3)

    # -------------------------------------------------------------------------
    # 5. Workbook with multiple worksheets, one containing the actual dataset
    # -------------------------------------------------------------------------
    def test_05_multi_sheets_one_actual_dataset(self):
        """Automatically ignores Instruction / ReadMe sheets and selects the tabular data sheet."""
        wb_path = os.path.join(self.temp_dir, "scenario5_readme_and_data.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: Instructions (non-tabular text)
        ws1 = wb.active
        ws1.title = "Instructions"
        ws1.append(["README & USER GUIDE"])
        ws1.append(["Please do not edit the data sheet directly without checking constraints."])
        ws1.append(["Contact the data engineering team for questions or bug reports."])

        # Sheet 2: Customers (actual tabular data)
        ws2 = wb.create_sheet(title="Customers")
        ws2.append(["Enterprise Customers List 2024"])  # Row 1: Title
        ws2.append(["cust_id", "company_name", "tier", "annual_spend"])  # Row 2: Headers
        ws2.append(["C101", "Acme Corp", "Enterprise", 125000])
        ws2.append(["C102", "Stark Ind", "Enterprise", 340000])
        ws2.append(["C103", "Wayne Ent", "Standard", 85000])
        wb.save(wb_path)

        # Automatic worksheet selector must choose "Customers"
        selected = auto_select_excel_worksheet(wb_path)
        self.assertEqual(selected, "Customers")

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("readme_and_data.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["sheet_name"], "Customers")
        self.assertEqual(data["header_row"], 2)
        self.assertEqual(data["rows"], 3)

    # -------------------------------------------------------------------------
    # 6. Workbook with multiple equally plausible data worksheets
    # -------------------------------------------------------------------------
    def test_06_multi_sheets_equally_plausible_rejected(self):
        """When multiple worksheets contain equally plausible data tables, import stops with a clear error."""
        wb_path = os.path.join(self.temp_dir, "scenario6_equally_plausible.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: Q1 Sales
        ws1 = wb.active
        ws1.title = "Q1_Sales"
        ws1.append(["order_id", "product", "revenue", "qty"])
        ws1.append(["O1", "Laptop", 50000, 2])
        ws1.append(["O2", "Monitor", 12000, 4])
        ws1.append(["O3", "Keyboard", 3000, 5])

        # Sheet 2: Q2 Sales (equally plausible structure)
        ws2 = wb.create_sheet(title="Q2_Sales")
        ws2.append(["order_id", "product", "revenue", "qty"])
        ws2.append(["O4", "Mouse", 1500, 6])
        ws2.append(["O5", "Desk", 25000, 1])
        ws2.append(["O6", "Chair", 18000, 3])
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("equally_plausible.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 400)
        err = res.json().get("detail", "")
        self.assertIn("multiple plausible data worksheets", err.lower())
        self.assertIn("simplify the workbook", err.lower())

    # -------------------------------------------------------------------------
    # 7. Ambiguous header candidates
    # -------------------------------------------------------------------------
    def test_07_ambiguous_header_candidates_rejected(self):
        """Ambiguous candidate rows stop import and return a clear user error without technical numbers."""
        wb_path = os.path.join(self.temp_dir, "scenario7_ambiguous.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Schedule"
        # Two text-heavy rows with competing header structures
        ws.append(["Division North", "Division South", "Division East"])
        ws.append(["Team Alpha", "Team Beta", "Team Gamma"])
        ws.append([100, 200, 300])
        ws.append([150, 250, 350])
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("ambiguous.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 400)
        err = res.json().get("detail", "")
        self.assertIn("multiple plausible heading rows", err.lower())
        self.assertIn("simplify", err.lower())
        # Verify no technical scoring leaked to user
        self.assertNotIn("score", err.lower())
        self.assertNotIn("diff_ratio", err.lower())

    # -------------------------------------------------------------------------
    # 8. CSV upload regression
    # -------------------------------------------------------------------------
    def test_08_csv_upload_regression(self):
        """CSV files continue to be processed with 100% reliability."""
        csv_path = os.path.join(self.temp_dir, "scenario8_standard.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("user_id,username,credits\n")
            f.write("U1,Alpha,100\n")
            f.write("U2,Beta,250\n")

        with open(csv_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("standard.csv", f, "text/csv")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["rows"], 2)
        self.assertEqual(data["columns"], 3)

    # -------------------------------------------------------------------------
    # 9. Privacy Guardian integration
    # -------------------------------------------------------------------------
    def test_09_privacy_guardian_integration(self):
        """Introductory content above headers in workbook containing sensitive personal data."""
        wb_path = os.path.join(self.temp_dir, "scenario9_privacy.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "HR_Staff"
        ws.append(["Staff Directory Confidential FY2024"])                        # Row 1: Title
        ws.append(["Internal Use Only"])                                           # Row 2: Note
        ws.append(["emp_name", "email", "phone_number", "ssn", "base_salary"])     # Row 3: Headers
        ws.append(["Rahul Sharma", "rahul@enterprise.com", "+1-202-555-0199", "123-45-6789", 85000])
        ws.append(["Priya Patel", "priya@enterprise.com", "+1-202-555-0188", "987-65-4321", 92000])
        wb.save(wb_path)

        with open(wb_path, "rb") as f:
            res = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("hr_staff.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.created_tables.append(data["table_name"])
        self.assertEqual(data["header_row"], 3)

        # Verify privacy policies detected automatically
        policies = get_dataset_column_policies(self.user_id_a, data["table_name"])
        self.assertEqual(policies.get("email", {}).get("policy"), "sensitive")
        self.assertEqual(policies.get("phone_number", {}).get("policy"), "sensitive")
        self.assertEqual(policies.get("ssn", {}).get("policy"), "restricted")

        # Verify database retains full unmasked values
        safe_tbl = f"`{data['table_name']}`"
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT email, phone_number, ssn FROM {safe_tbl} ORDER BY id ASC")).fetchall()
        self.assertEqual(rows[0][0], "rahul@enterprise.com")
        self.assertEqual(rows[0][1], "+1-202-555-0199")
        self.assertEqual(rows[0][2], "123-45-6789")

    # -------------------------------------------------------------------------
    # 10. Tenant isolation and atomic swap
    # -------------------------------------------------------------------------
    def test_10_tenant_isolation_and_atomic_swap(self):
        """Two different users uploading datasets remain strictly isolated with user-specific tables."""
        wb_path = os.path.join(self.temp_dir, "scenario10_tenant.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Metrics"
        ws.append(["Department Performance"])
        ws.append(["dept_code", "kpi_score", "active_projects"])
        ws.append(["ENG", 98.2, 14])
        ws.append(["MKT", 87.5, 9])
        wb.save(wb_path)

        # Upload as User A
        with open(wb_path, "rb") as f:
            res_a = self.client.post(
                "/upload",
                headers=self.headers_a,
                files={"file": ("metrics.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res_a.status_code, 200)
        table_a = res_a.json()["table_name"]
        self.created_tables.append(table_a)

        # Upload as User B
        with open(wb_path, "rb") as f:
            res_b = self.client.post(
                "/upload",
                headers=self.headers_b,
                files={"file": ("metrics.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res_b.status_code, 200)
        table_b = res_b.json()["table_name"]
        self.created_tables.append(table_b)

        # Tables must have distinct tenant suffixes
        self.assertIn(self.user_id_a, table_a)
        self.assertIn(self.user_id_b, table_b)
        self.assertNotEqual(table_a, table_b)


if __name__ == "__main__":
    unittest.main()
