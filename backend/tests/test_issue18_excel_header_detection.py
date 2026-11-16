"""
PromptSQL — Issue 18: Robust Excel Header Detection and Import Preview Test Suite

Tests all 10 scenarios + Privacy Guardian regression + UI preview endpoint:
1. Scenario 1: Headers in row 1.
2. Scenario 2: Title in row 1, headers in row 2.
3. Scenario 3: Title and description in rows 1-2, headers in row 3.
4. Scenario 4: Several introductory rows with headers in row 5.
5. Scenario 5: Merged title cells above the headings.
6. Scenario 6: Blank rows before the headings.
7. Scenario 7: Duplicate and empty column headings.
8. Scenario 8: Multiple worksheets with different header positions.
9. Scenario 9: Workbook with ambiguous header candidates.
10. Scenario 10: Numeric identifiers, dates, missing values and leading-zero text identifiers.
11. Regression: Privacy Guardian test workbook with introductory content.
12. CSV compatibility: CSV uploads work untouched.
13. User manual override: User-selected header row accurately overrides auto-detection.
"""

import unittest
import os
import shutil
import tempfile
import time
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
    normalize_column_names,
    load_excel_with_detected_header,
    detect_and_preview_excel,
)
from app.services.upload_service import upload_dataset
from app.services.privacy_service import scan_and_save_dataset_privacy, get_dataset_column_policies


class TestIssue18ExcelHeaderDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        cls.temp_dir = tempfile.mkdtemp(prefix="promptsql_i18_test_")

        # Test user
        cls.test_username = f"i18_user_{uuid.uuid4().hex[:8]}"
        cls.user = User(
            username=cls.test_username,
            password_hash=hash_password("TestPassword123!")
        )
        cls.db.add(cls.user)
        cls.db.commit()
        cls.db.refresh(cls.user)
        cls.user_id_str = f"usr_{cls.user.id}"
        cls.token = create_access_token(cls.user.id)
        cls.headers = {"Authorization": f"Bearer {cls.token}"}
        cls.created_tables = []

    @classmethod
    def tearDownClass(cls):
        # Drop test tables created in database
        try:
            with engine.begin() as conn:
                for tbl in cls.created_tables:
                    conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
        except Exception:
            pass

        try:
            cls.db.query(User).filter(User.id == cls.user.id).delete()
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        finally:
            cls.db.close()

        # Clean temp directory
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Scenario 1: Headers in Row 1
    # -------------------------------------------------------------------------
    def test_01_headers_in_row_1(self):
        """Standard Excel workbook where column headings reside in row 1."""
        wb_path = os.path.join(self.temp_dir, "scenario1_headers_row1.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sales"
        ws.append(["order_id", "customer_name", "amount", "order_date"])
        ws.append(["ORD101", "Alice Smith", 120.50, "2024-01-10"])
        ws.append(["ORD102", "Bob Jones", 450.00, "2024-01-11"])
        ws.append(["ORD103", "Charlie Day", 75.25, "2024-01-12"])
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="Sales")
        self.assertEqual(detection["header_row_1_based"], 1)
        self.assertFalse(detection["is_ambiguous"])
        self.assertGreaterEqual(detection["confidence"], 0.70)

        df, meta = load_excel_with_detected_header(wb_path, sheet_name="Sales")
        self.assertEqual(len(df), 3)
        self.assertEqual(df.columns.tolist(), ["order_id", "customer_name", "amount", "order_date"])

        # End-to-end upload
        res = upload_dataset(wb_path, "scenario1.xlsx", user_id=self.user_id_str)
        self.created_tables.append(res["table_name"])
        self.assertEqual(res["rows"], 3)
        self.assertEqual(res["header_row"], 1)

    # -------------------------------------------------------------------------
    # Scenario 2: Title in Row 1, Headers in Row 2
    # -------------------------------------------------------------------------
    def test_02_title_in_row_1_headers_in_row_2(self):
        """Title on row 1, followed immediately by column headings on row 2."""
        wb_path = os.path.join(self.temp_dir, "scenario2_title_row1_headers_row2.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Employees"
        ws.append(["Quarterly Department Roster FY2024"])  # Row 1: Title
        ws.append(["employee_id", "full_name", "department", "annual_salary"])  # Row 2: Headers
        ws.append(["E001", "David Clark", "Engineering", 95000])  # Row 3: Data
        ws.append(["E002", "Emma Watson", "Marketing", 72000])    # Row 4: Data
        ws.append(["E003", "Frank Miller", "Finance", 88000])     # Row 5: Data
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="Employees")
        self.assertEqual(detection["header_row_1_based"], 2, "Row 2 must be detected as header row")
        self.assertFalse(detection["is_ambiguous"])

        df, meta = load_excel_with_detected_header(wb_path, sheet_name="Employees")
        self.assertEqual(len(df), 3)
        self.assertEqual(df.columns.tolist(), ["employee_id", "full_name", "department", "annual_salary"])
        self.assertEqual(df.iloc[0]["employee_id"], "E001")

        # End-to-end upload
        res = upload_dataset(wb_path, "scenario2.xlsx", user_id=self.user_id_str)
        self.created_tables.append(res["table_name"])
        self.assertEqual(res["rows"], 3)
        self.assertEqual(res["header_row"], 2)

    # -------------------------------------------------------------------------
    # Scenario 3: Title and Description in Rows 1-2, Headers in Row 3
    # -------------------------------------------------------------------------
    def test_03_title_and_description_in_rows_1_2_headers_in_row_3(self):
        """Title in row 1, narrative description in row 2, headers in row 3."""
        wb_path = os.path.join(self.temp_dir, "scenario3_headers_row3.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inventory"
        ws.append(["Enterprise Inventory & Warehouse Stock Report"])  # Row 1: Title
        ws.append(["Confidential: Contains real-time physical stock counts as of October 2024."])  # Row 2: Note
        ws.append(["product_sku", "product_name", "warehouse", "stock_qty", "unit_cost"])  # Row 3: Headers
        ws.append(["SKU-100", "Widget Pro", "North", 450, 19.99])  # Row 4: Data
        ws.append(["SKU-200", "Gadget Plus", "South", 120, 49.50]) # Row 5: Data
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="Inventory")
        self.assertEqual(detection["header_row_1_based"], 3)

        df, _ = load_excel_with_detected_header(wb_path, sheet_name="Inventory")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.columns.tolist(), ["product_sku", "product_name", "warehouse", "stock_qty", "unit_cost"])

    # -------------------------------------------------------------------------
    # Scenario 4: Several Introductory Rows with Headers in Row 5
    # -------------------------------------------------------------------------
    def test_04_several_introductory_rows_headers_in_row_5(self):
        """Multiple metadata notes, instructions, and blank lines before headers at row 5."""
        wb_path = os.path.join(self.temp_dir, "scenario4_headers_row5.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Patients"
        ws.append(["Hospital Administration System"])  # Row 1
        ws.append(["Department: Cardiology Division"])  # Row 2
        ws.append(["Prepared by: Dr. Robert Langdon"])  # Row 3
        ws.append([])                                  # Row 4: Blank
        ws.append(["patient_id", "patient_name", "age", "diagnosis", "admission_date"])  # Row 5: Headers
        ws.append(["P1001", "Grace Hopper", 72, "Arrhythmia", "2024-03-01"])            # Row 6: Data
        ws.append(["P1002", "Alan Turing", 41, "Hypertension", "2024-03-04"])            # Row 7: Data
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="Patients")
        self.assertEqual(detection["header_row_1_based"], 5)

        df, _ = load_excel_with_detected_header(wb_path, sheet_name="Patients")
        self.assertEqual(len(df), 2)
        self.assertIn("patient_id", df.columns)

    # -------------------------------------------------------------------------
    # Scenario 5: Merged Title Cells Above Headings
    # -------------------------------------------------------------------------
    def test_05_merged_title_cells_above_headings(self):
        """Merged cell banner across columns A1:E1 with headers in row 2."""
        wb_path = os.path.join(self.temp_dir, "scenario5_merged_banner.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Financials"
        ws["A1"] = "Consolidated Financial Performance Q3"
        ws.merge_cells("A1:E1")  # Merge A1 through E1
        ws.append(["fiscal_quarter", "revenue", "cogs", "operating_expenses", "net_income"])  # Row 2
        ws.append(["2024-Q1", 500000.0, 200000.0, 150000.0, 150000.0])                        # Row 3
        ws.append(["2024-Q2", 620000.0, 240000.0, 160000.0, 220000.0])                        # Row 4
        wb.save(wb_path)

        merged = detect_merged_title_rows(wb_path, "Financials")
        self.assertIn(0, merged, "Row 0 (Excel row 1) must be identified as merged banner")

        detection = detect_header_row(wb_path, sheet_name="Financials")
        self.assertEqual(detection["header_row_1_based"], 2)

        df, _ = load_excel_with_detected_header(wb_path, sheet_name="Financials")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.columns.tolist(), ["fiscal_quarter", "revenue", "cogs", "operating_expenses", "net_income"])

    # -------------------------------------------------------------------------
    # Scenario 6: Blank Rows Before Headings
    # -------------------------------------------------------------------------
    def test_06_blank_rows_before_headings(self):
        """Top 3 rows are completely blank, headers begin on row 4."""
        wb_path = os.path.join(self.temp_dir, "scenario6_blank_rows_top.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Projects"
        ws.append([])  # Row 1
        ws.append([])  # Row 2
        ws.append([])  # Row 3
        ws.append(["project_code", "project_title", "lead", "budget", "status"])  # Row 4
        ws.append(["PRJ-01", "Apollo Rebuild", "Sarah", 150000, "Active"])       # Row 5
        ws.append(["PRJ-02", "Gemini Sync", "Kevin", 85000, "Planning"])         # Row 6
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="Projects")
        self.assertEqual(detection["header_row_1_based"], 4)

        df, _ = load_excel_with_detected_header(wb_path, sheet_name="Projects")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["project_code"], "PRJ-01")

    # -------------------------------------------------------------------------
    # Scenario 7: Duplicate and Empty Column Headings
    # -------------------------------------------------------------------------
    def test_07_duplicate_and_empty_column_headings(self):
        """Headers contain duplicate names ('Amount', 'Amount') and empty cell ('')."""
        wb_path = os.path.join(self.temp_dir, "scenario7_duplicates_and_empty.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Transactions"
        # Duplicate 'amount' and empty cell in 3rd column
        ws.append(["tx_id", "amount", None, "amount"])  # Row 1
        ws.append(["TX1", 100.0, "Verified", 105.0])    # Row 2
        ws.append(["TX2", 200.0, "Pending", 210.0])     # Row 3
        wb.save(wb_path)

        df, meta = load_excel_with_detected_header(wb_path, sheet_name="Transactions")
        self.assertEqual(len(df.columns), 4)
        cols = df.columns.tolist()
        self.assertEqual(cols[0], "tx_id")
        self.assertEqual(cols[1], "amount")
        self.assertEqual(cols[2], "Column_3", "Empty column must be cleanly assigned Column_3")
        self.assertEqual(cols[3], "amount_1", "Duplicate amount must be disambiguated to amount_1")

        # Warnings generated
        self.assertTrue(any("empty heading" in w.lower() for w in meta["warnings"]))
        self.assertTrue(any("duplicate column" in w.lower() for w in meta["warnings"]))

    # -------------------------------------------------------------------------
    # Scenario 8: Multiple Worksheets with Different Header Positions
    # -------------------------------------------------------------------------
    def test_08_multiple_worksheets_with_different_header_positions(self):
        """Workbook with 2 sheets: Sheet A has headers in row 1, Sheet B has headers in row 3."""
        wb_path = os.path.join(self.temp_dir, "scenario8_multi_sheets.xlsx")
        wb = openpyxl.Workbook()

        # Sheet 1: Summary (headers in row 1)
        ws1 = wb.active
        ws1.title = "Summary"
        ws1.append(["dept", "headcount", "budget"])
        ws1.append(["IT", 45, 1200000])
        ws1.append(["Sales", 60, 1800000])

        # Sheet 2: Raw_Log (title in row 1, note in row 2, headers in row 3)
        ws2 = wb.create_sheet(title="Raw_Log")
        ws2.append(["System Access Audit Logs"])
        ws2.append(["Exported by Admin on 2024-04-10"])
        ws2.append(["log_id", "user_email", "ip_address", "action", "status"])
        ws2.append(["L001", "dev@org.com", "10.0.0.1", "LOGIN", "SUCCESS"])
        ws2.append(["L002", "qa@org.com", "10.0.0.2", "LOGOUT", "SUCCESS"])
        wb.save(wb_path)

        sheets = get_excel_sheet_names(wb_path)
        self.assertEqual(sheets, ["Summary", "Raw_Log"])

        # Detect Sheet 1
        det1 = detect_header_row(wb_path, sheet_name="Summary")
        self.assertEqual(det1["header_row_1_based"], 1)

        # Detect Sheet 2
        det2 = detect_header_row(wb_path, sheet_name="Raw_Log")
        self.assertEqual(det2["header_row_1_based"], 3)

        # Upload Sheet 2 specifically
        res2 = upload_dataset(wb_path, "logs.xlsx", user_id=self.user_id_str, sheet_name="Raw_Log")
        self.created_tables.append(res2["table_name"])
        self.assertEqual(res2["sheet_name"], "Raw_Log")
        self.assertEqual(res2["header_row"], 3)
        self.assertEqual(res2["rows"], 2)

    # -------------------------------------------------------------------------
    # Scenario 9: Workbook with Ambiguous Header Candidates
    # -------------------------------------------------------------------------
    def test_09_ambiguous_header_candidates_flagged(self):
        """Two text-heavy rows with similar scores are flagged as ambiguous."""
        wb_path = os.path.join(self.temp_dir, "scenario9_ambiguous.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Schedule"
        # Row 1: Section Headings
        ws.append(["Division North", "Division South", "Division East"])
        # Row 2: Sub-Headings
        ws.append(["Team Alpha", "Team Beta", "Team Gamma"])
        # Row 3: Data
        ws.append([100, 200, 300])
        ws.append([150, 250, 350])
        wb.save(wb_path)

        preview = detect_and_preview_excel(wb_path, sheet_name="Schedule")
        self.assertTrue(preview["is_ambiguous"], "Ambiguous row candidates must be flagged")
        self.assertTrue(any("ambiguous" in w.lower() for w in preview["warnings"]))

    # -------------------------------------------------------------------------
    # Scenario 10: Numeric Identifiers, Dates, Missing Values & Leading-Zero Text
    # -------------------------------------------------------------------------
    def test_10_leading_zero_text_dates_and_missing_values(self):
        """Preserves leading-zero strings ('00123'), true nulls, dates, and valid zeros."""
        wb_path = os.path.join(self.temp_dir, "scenario10_data_integrity.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Roster"
        ws.append(["Staff Directory 2024"])  # Row 1: Title
        ws.append(["emp_code", "hire_date", "score", "balance", "notes"])  # Row 2: Headers
        ws.append(["00123", "2023-05-15", 95.5, 0.0, None])                 # Row 3: Data (valid 0.0, null)
        ws.append(["00456", "2023-08-20", 82.0, 150.0, "New hire"])        # Row 4: Data
        ws.append(["09876", "2024-01-10", None, 0, "Zero balance"])        # Row 5: Data (null score, 0 balance)
        wb.save(wb_path)

        df, _ = load_excel_with_detected_header(wb_path, sheet_name="Roster")
        self.assertEqual(len(df), 3)

        # 1. Leading zero preserved
        self.assertEqual(df.iloc[0]["emp_code"], "00123")
        self.assertEqual(df.iloc[1]["emp_code"], "00456")
        self.assertEqual(df.iloc[2]["emp_code"], "09876")

        # 2. End-to-end upload and database verification
        res = upload_dataset(wb_path, "roster.xlsx", user_id=self.user_id_str)
        self.created_tables.append(res["table_name"])
        safe_tbl = f"`{res['table_name']}`"

        with engine.connect() as conn:
            codes = [r[0] for r in conn.execute(text(f"SELECT emp_code FROM {safe_tbl} ORDER BY id ASC")).fetchall()]
            balances = [r[0] for r in conn.execute(text(f"SELECT balance FROM {safe_tbl} ORDER BY id ASC")).fetchall()]
            notes = [r[0] for r in conn.execute(text(f"SELECT notes FROM {safe_tbl} ORDER BY id ASC")).fetchall()]

        # Verify leading zeros remained intact in database column
        self.assertEqual(codes, ["00123", "00456", "09876"])
        # Verify valid zero values preserved
        self.assertEqual(balances[0], 0.0)
        self.assertEqual(balances[2], 0.0)
        # Verify missing note is database NULL (None)
        self.assertIsNone(notes[0])

    # -------------------------------------------------------------------------
    # Scenario 11: Privacy Guardian Test Workbook Regression
    # -------------------------------------------------------------------------
    def test_11_privacy_guardian_workbook_structure_regression(self):
        """Introductory content above headers in workbook containing sensitive personal data."""
        wb_path = os.path.join(self.temp_dir, "scenario11_privacy_workbook.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "HR_Confidential"
        ws.append(["Acme Global HR Master Records - Strictly Confidential"])  # Row 1
        ws.append(["Generated for Audit Compliance: 2024-05-01"])            # Row 2
        ws.append(["emp_name", "email", "phone_number", "ssn", "base_salary"])  # Row 3: Headers
        ws.append(["Rahul Sharma", "rahul@enterprise.com", "+1-202-555-0199", "123-45-6789", 85000])
        ws.append(["Priya Patel", "priya@enterprise.com", "+1-202-555-0188", "987-65-4321", 92000])
        wb.save(wb_path)

        detection = detect_header_row(wb_path, sheet_name="HR_Confidential")
        self.assertEqual(detection["header_row_1_based"], 3)

        # Upload and trigger Privacy Guardian scan
        res = upload_dataset(wb_path, "hr_confidential.xlsx", user_id=self.user_id_str)
        self.created_tables.append(res["table_name"])

        scan_and_save_dataset_privacy(self.user_id_str, res["table_name"])
        policies = get_dataset_column_policies(self.user_id_str, res["table_name"])

        # Sensitive columns should be recognized despite title rows in raw Excel
        self.assertEqual(policies.get("email", {}).get("policy"), "sensitive")
        self.assertEqual(policies.get("phone_number", {}).get("policy"), "sensitive")
        self.assertEqual(policies.get("ssn", {}).get("policy"), "restricted")

    # -------------------------------------------------------------------------
    # Scenario 12: CSV Compatibility Untouched
    # -------------------------------------------------------------------------
    def test_12_csv_compatibility_untouched(self):
        """CSV files continue to be processed with 100% reliability."""
        csv_path = os.path.join(self.temp_dir, "scenario12_standard.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("user_id,username,credits\n")
            f.write("U1,Alpha,100\n")
            f.write("U2,Beta,250\n")

        res = upload_dataset(csv_path, "scenario12.csv", user_id=self.user_id_str)
        self.created_tables.append(res["table_name"])
        self.assertEqual(res["rows"], 2)
        self.assertEqual(res["columns"], 3)

    # -------------------------------------------------------------------------
    # Scenario 13: UI Preview API & Manual Header Row Override
    # -------------------------------------------------------------------------
    def test_13_preview_api_and_manual_header_override(self):
        """User can request preview, manually override header row, and upload with confirmed row."""
        wb_path = os.path.join(self.temp_dir, "scenario13_override.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Overrides"
        ws.append(["Summary Dashboard"])                                # Row 1
        ws.append(["Note: Preliminary Data"])                           # Row 2
        ws.append(["col_a", "col_b", "col_c"])                          # Row 3
        ws.append(["data1", "data2", "data3"])                          # Row 4
        wb.save(wb_path)

        # 1. Test POST /upload/preview-excel endpoint
        with open(wb_path, "rb") as f:
            res_preview = self.client.post(
                "/upload/preview-excel",
                headers=self.headers,
                files={"file": ("override.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(res_preview.status_code, 200)
        data = res_preview.json()
        self.assertEqual(data["detected_header_row"], 3)
        self.assertEqual(data["selected_header_row"], 3)
        self.assertEqual(data["columns"], ["col_a", "col_b", "col_c"])

        # 2. Test manual override to Row 4 (user explicitly chooses row 4 as header)
        with open(wb_path, "rb") as f:
            res_override = self.client.post(
                "/upload/preview-excel",
                headers=self.headers,
                files={"file": ("override.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"header_row": "4"}
            )
        self.assertEqual(res_override.status_code, 200)
        data_ov = res_override.json()
        self.assertEqual(data_ov["selected_header_row"], 4)
        self.assertEqual(data_ov["columns"], ["data1", "data2", "data3"])

        # 3. Test confirmed upload with explicit header_row=3
        with open(wb_path, "rb") as f:
            res_upload = self.client.post(
                "/upload",
                headers=self.headers,
                files={"file": ("override.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"header_row": "3", "sheet_name": "Overrides"}
            )
        self.assertEqual(res_upload.status_code, 200)
        upload_json = res_upload.json()
        self.created_tables.append(upload_json["table_name"])
        self.assertEqual(upload_json["header_row"], 3)
        self.assertEqual(upload_json["rows"], 1)


if __name__ == "__main__":
    unittest.main()
