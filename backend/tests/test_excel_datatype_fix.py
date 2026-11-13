"""
PromptSQL — Excel Data Type Conversion Bug: Regression Test Suite

Verifies:
1. is_date_series() does NOT classify alphanumeric identifier codes as dates.
2. is_identifier_column_name() recognises _NO, _REF, _CODE, number, etc.
3. detect_column_types() classifies STAFF_NO and ENROLLMENT_REF columns as text.
4. Full upload pipeline stores ST-201 as a string, not 0201-01-01.
5. Legitimate date and numeric columns are unaffected.
6. JOIN across staff_directory and training_enrollments using STAFF_NO returns correct records.
7. Additional identifier formats that must NOT be parsed as dates.
"""

import unittest
import os
import sys
import io
import pandas as pd
import openpyxl
from sqlalchemy import text

# --- Path setup ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

from app.database.connection import engine
from app.services.datatype_detector import (
    is_date_series,
    is_identifier_column_name,
    detect_column_types,
)
from app.services.upload_service import upload_dataset, load_dataset
from app.services.data_cleaner import clean_dataframe


SCRATCH_DIR = os.path.dirname(os.path.abspath(__file__))
STAFF_XLSX = os.path.join(SCRATCH_DIR, "Staff_Directory.xlsx")
ENROLL_XLSX = os.path.join(SCRATCH_DIR, "Training_Enrollments.xlsx")
TEST_USER_ID = "usr_bugtest"
STAFF_TABLE = f"staff_directory_{TEST_USER_ID}"
ENROLL_TABLE = f"training_enrollments_{TEST_USER_ID}"


def _make_excel_bytes(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestIsDateSeriesGuards(unittest.TestCase):
    """Unit tests for the is_date_series() guard rails."""

    def _series(self, values):
        return pd.Series(values)

    # -- Values that must NOT be classified as dates --
    def test_reject_staff_codes_hyphen(self):
        """ST-201, ST-202 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["ST-201", "ST-202", "ST-203"])))

    def test_reject_enrollment_refs(self):
        """EN-9001, EN-9002 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["EN-9001", "EN-9002", "EN-9003"])))

    def test_reject_order_ids(self):
        """ORD-10001 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["ORD-10001", "ORD-10002"])))

    def test_reject_sku_codes(self):
        """SKU-001 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["SKU-001", "SKU-002", "SKU-003"])))

    def test_reject_emp_codes(self):
        """EMP001 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["EMP001", "EMP002", "EMP003"])))

    def test_reject_module_codes(self):
        """PY-101, FN-210 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["PY-101", "FN-210", "UX-115"])))

    def test_reject_quarter_codes(self):
        """2024-Q1 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["2024-Q1", "2024-Q2", "2024-Q3"])))

    def test_reject_client_codes(self):
        """CL-305 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["CL-305", "CL-306"])))

    def test_reject_alpha_prefix_numeric(self):
        """AB-123 must NOT be dates."""
        self.assertFalse(is_date_series(self._series(["AB-123", "AB-124", "AB-125"])))

    # -- Values that MUST be classified as dates --
    def test_accept_iso_dates(self):
        """2024-01-15 format must be recognised as date."""
        self.assertTrue(is_date_series(self._series(["2024-01-15", "2024-02-20", "2024-03-10"])))

    def test_accept_dmy_dates(self):
        """15/01/2024 format must be recognised as date."""
        self.assertTrue(is_date_series(self._series(["15/01/2024", "20/02/2024", "10/03/2024"])))

    def test_accept_long_dates(self):
        """January 15, 2024 must be recognised as date."""
        self.assertTrue(is_date_series(self._series(["January 15, 2024", "February 20, 2024"])))

    def test_accept_dmy_dash(self):
        """15-01-2024 must be recognised as date."""
        self.assertTrue(is_date_series(self._series(["15-01-2024", "20-02-2024", "10-03-2024"])))


class TestIsIdentifierColumnName(unittest.TestCase):
    """Unit tests for the is_identifier_column_name() column-name heuristic."""

    def test_staff_no(self):
        self.assertTrue(is_identifier_column_name("STAFF_NO"))

    def test_staff_no_space(self):
        self.assertTrue(is_identifier_column_name("STAFF NO"))

    def test_enrollment_ref(self):
        self.assertTrue(is_identifier_column_name("ENROLLMENT_REF"))

    def test_module_code(self):
        self.assertTrue(is_identifier_column_name("MODULE_CODE"))

    def test_employee_id(self):
        self.assertTrue(is_identifier_column_name("EMPLOYEE_ID"))

    def test_customer_id(self):
        self.assertTrue(is_identifier_column_name("CustomerID"))

    def test_order_number(self):
        self.assertTrue(is_identifier_column_name("Order Number"))

    def test_ref_no(self):
        self.assertTrue(is_identifier_column_name("REF_NO"))

    def test_product_code(self):
        self.assertTrue(is_identifier_column_name("product_code"))

    def test_non_identifier_salary(self):
        self.assertFalse(is_identifier_column_name("SALARY"))

    def test_non_identifier_hire_date(self):
        self.assertFalse(is_identifier_column_name("HIRE_DATE"))

    def test_non_identifier_department(self):
        self.assertFalse(is_identifier_column_name("DEPARTMENT"))

    def test_non_identifier_score(self):
        self.assertFalse(is_identifier_column_name("SCORE"))


class TestDetectColumnTypes(unittest.TestCase):
    """Integration tests for detect_column_types() on the staff dataset."""

    def _make_df(self):
        return pd.DataFrame({
            "STAFF_NO":           ["ST-201", "ST-202", "ST-203"],
            "FULL_NAME":          ["Maya Iyer", "Arjun Mehta", "Nisha Rao"],
            "DEPARTMENT":         ["Engineering", "Finance", "Design"],
            "HIRE_DATE":          ["2022-03-15", "2021-07-01", "2023-01-10"],
            "SALARY":             [85000, 92000, 78000],
            "ENROLLMENT_REF":     ["EN-9001", "EN-9002", "EN-9003"],
            "MODULE_CODE":        ["PY-101", "FN-210", "UX-115"],
            "COMPLETION_STATUS":  ["Completed", "In Progress", "Completed"],
            "SCORE":              [92.0, 68.0, 88.0],
        })

    def setUp(self):
        self.types = detect_column_types(self._make_df())

    def test_staff_no_is_text(self):
        self.assertEqual(self.types["STAFF_NO"], "text", "STAFF_NO must be text, not date")

    def test_enrollment_ref_is_text(self):
        self.assertEqual(self.types["ENROLLMENT_REF"], "text")

    def test_module_code_is_text(self):
        self.assertEqual(self.types["MODULE_CODE"], "text")

    def test_hire_date_is_date(self):
        self.assertEqual(self.types["HIRE_DATE"], "date", "HIRE_DATE must be detected as date")

    def test_salary_is_numeric(self):
        self.assertEqual(self.types["SALARY"], "numeric")

    def test_score_is_numeric(self):
        self.assertEqual(self.types["SCORE"], "numeric")

    def test_department_is_text(self):
        self.assertEqual(self.types["DEPARTMENT"], "text")

    def test_completion_status_is_text(self):
        self.assertEqual(self.types["COMPLETION_STATUS"], "text")


class TestUploadPipelinePreservesIdentifiers(unittest.TestCase):
    """
    Uploads the synthetic Staff Directory and Training Enrollments Excel files
    through the full upload_dataset pipeline and checks the MySQL tables.
    """

    @classmethod
    def setUpClass(cls):
        # Drop any pre-existing test tables
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{STAFF_TABLE}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{ENROLL_TABLE}`"))

        # Upload via the full pipeline (creates temp file, calls upload_dataset)
        import shutil, tempfile

        for src, fname in [(STAFF_XLSX, "Staff_Directory.xlsx"), (ENROLL_XLSX, "Training_Enrollments.xlsx")]:
            tmp_path = tempfile.mktemp(suffix=".xlsx")
            shutil.copy(src, tmp_path)
            try:
                upload_dataset(filepath=tmp_path, filename=fname, user_id=TEST_USER_ID)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{STAFF_TABLE}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{ENROLL_TABLE}`"))

    def test_staff_no_values_preserved_in_staff_table(self):
        """STAFF_NO column in staff_directory must contain 'ST-201', not '0201-01-01'."""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT staff_no FROM `{STAFF_TABLE}` ORDER BY id")).fetchall()
        values = [r[0] for r in rows]
        print("staff_directory.STAFF_NO values:", values)
        expected = ["ST-201", "ST-202", "ST-203", "ST-204", "ST-205", "ST-206"]
        self.assertEqual(values, expected,
                         f"STAFF_NO values corrupted! Got: {values}, expected: {expected}")

    def test_staff_no_values_preserved_in_enroll_table(self):
        """STAFF_NO column in training_enrollments must contain 'ST-201', not '0201-01-01...'."""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT staff_no FROM `{ENROLL_TABLE}` ORDER BY id")).fetchall()
        values = [r[0] for r in rows]
        print("training_enrollments.STAFF_NO values:", values)
        self.assertIn("ST-201", values)
        self.assertNotIn("0201-01-01 00:00:00", values)
        self.assertNotIn("0201-01-01", values)

    def test_hire_date_stored_as_datetime(self):
        """HIRE_DATE column must be stored as a valid date, not garbled."""
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT hire_date FROM `{STAFF_TABLE}` LIMIT 1")).fetchone()
        hire_date = row[0]
        print("HIRE_DATE first value:", hire_date)
        self.assertIsNotNone(hire_date)
        # Should be a date object, not a string containing 'ST-'
        self.assertNotIn("ST-", str(hire_date))

    def test_salary_stored_as_number(self):
        """SALARY must be stored as a number."""
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT salary FROM `{STAFF_TABLE}` LIMIT 1")).fetchone()
        salary = row[0]
        print("SALARY first value:", salary, type(salary))
        self.assertIsNotNone(salary)
        self.assertGreater(float(salary), 0)

    def test_join_on_staff_no_returns_correct_records(self):
        """
        JOIN training_enrollments to staff_directory on STAFF_NO.
        Must return matching rows — requires STAFF_NO to be preserved as a string in both tables.
        """
        sql = f"""
            SELECT s.full_name, s.department, e.module_code, e.completion_status
            FROM `{STAFF_TABLE}` s
            JOIN `{ENROLL_TABLE}` e ON s.staff_no = e.staff_no
            ORDER BY s.full_name, e.module_code
        """
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
        print(f"JOIN returned {len(rows)} rows")
        for r in rows:
            print(" ", r)

        self.assertGreater(len(rows), 0,
                           "JOIN returned 0 rows — STAFF_NO values are mismatched (corruption still present)")

        # Verify specific expected joins
        full_names = [r[0] for r in rows]
        self.assertIn("Maya Iyer", full_names)   # ST-201 appears in both tables
        self.assertIn("Arjun Mehta", full_names) # ST-202 appears in both tables

    def test_enrollment_ref_preserved(self):
        """ENROLLMENT_REF must be preserved as EN-9001, not garbled."""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT enrollment_ref FROM `{ENROLL_TABLE}` LIMIT 3")).fetchall()
        values = [r[0] for r in rows]
        print("ENROLLMENT_REF values:", values)
        self.assertIn("EN-9001", values)
        self.assertNotIn("9001-01-01", values)

    def test_module_code_preserved(self):
        """MODULE_CODE like PY-101 must not be corrupted."""
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT module_code FROM `{ENROLL_TABLE}` LIMIT 3")).fetchall()
        values = [r[0] for r in rows]
        print("MODULE_CODE values:", values)
        self.assertIn("PY-101", values)


class TestExtraIdentifierFormats(unittest.TestCase):
    """
    Verify that additional identifier formats across different domains are
    never corrupted by is_date_series(). Zero hardcoding — these test column
    *values* only; column names vary.
    """

    def _assert_not_date(self, label, values):
        s = pd.Series(values)
        result = is_date_series(s)
        self.assertFalse(result, f"{label} should NOT be classified as date, but was: {values}")

    def _assert_is_date(self, label, values):
        s = pd.Series(values)
        result = is_date_series(s)
        self.assertTrue(result, f"{label} SHOULD be classified as date, but was not: {values}")

    def test_hyphen_alpha_prefix(self):
        self._assert_not_date("Alpha-hyphen-number codes", ["AB-100", "AB-101", "AB-102"])

    def test_mixed_case_codes(self):
        self._assert_not_date("Mixed-case codes", ["Ref-2024", "Ref-2025", "Ref-2026"])

    def test_all_alpha_no_digits(self):
        # Pure alpha text — should be text, not date
        self._assert_not_date("Pure alpha", ["Completed", "In Progress", "Not Started"])

    def test_numeric_only_no_separator(self):
        # Bare integers — not dates without separator
        self._assert_not_date("Bare integers", ["201", "202", "203"])

    def test_iso_dates_still_work(self):
        self._assert_is_date("ISO dates", ["2022-03-15", "2021-07-01", "2023-01-10"])

    def test_slash_dates_still_work(self):
        self._assert_is_date("Slash dates", ["15/01/2022", "01/07/2021", "10/01/2023"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
