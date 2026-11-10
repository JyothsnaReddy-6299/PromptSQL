import os
import sys
import uuid
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text, inspect
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, SessionLocal, Base
from app.models.user import User
from app.models.user_active_dataset import UserActiveDataset
from app.models.pending_modification import PendingModification
from app.services.auth_service import hash_password, create_access_token
from app.services.table_manager import (
    get_current_table,
    set_current_table,
    clear_current_table,
    _USER_ACTIVE_TABLES,
    _LOCK
)
from app.services.dataset_guard import resolve_and_authorize_dataset, PROTECTED_SYSTEM_TABLES


class Step4ConcurrentUserIsolationTests(unittest.TestCase):
    """
    Comprehensive tests for Step 4: Per-user Active Dataset State & Concurrent User Isolation.
    Verifies isolation across concurrent users, multi-worker consistency, dataset switching,
    header injection defense, and stale reference cleanup.
    """

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.test_id = uuid.uuid4().hex[:6]
        
        # User A setup
        cls.user_num_a = 9101
        cls.user_id_a = f"usr_{cls.user_num_a}"
        cls.table_a1 = f"ds_a1_{cls.user_id_a}"
        cls.table_a2 = f"ds_a2_{cls.user_id_a}"

        # User B setup
        cls.user_num_b = 9102
        cls.user_id_b = f"usr_{cls.user_num_b}"
        cls.table_b1 = f"ds_b1_{cls.user_id_b}"

        # User C setup (no datasets)
        cls.user_num_c = 9103
        cls.user_id_c = f"usr_{cls.user_num_c}"

        db = SessionLocal()
        try:
            # Clean and create users in database
            db.query(User).filter(User.id.in_([cls.user_num_a, cls.user_num_b, cls.user_num_c])).delete(synchronize_session=False)
            db.query(UserActiveDataset).filter(UserActiveDataset.user_id.in_([cls.user_id_a, cls.user_id_b, cls.user_id_c])).delete(synchronize_session=False)
            
            user_a = User(id=cls.user_num_a, username=f"user_a_{cls.test_id}", password_hash=hash_password("Pass12345678#A"))
            user_b = User(id=cls.user_num_b, username=f"user_b_{cls.test_id}", password_hash=hash_password("Pass12345678#B"))
            user_c = User(id=cls.user_num_c, username=f"user_c_{cls.test_id}", password_hash=hash_password("Pass12345678#C"))
            db.add_all([user_a, user_b, user_c])
            db.commit()
        finally:
            db.close()

        # Generate access tokens
        cls.token_a = create_access_token(user_id=cls.user_num_a)
        cls.token_b = create_access_token(user_id=cls.user_num_b)
        cls.token_c = create_access_token(user_id=cls.user_num_c)

        # Create physical test tables in MySQL
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a1}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a2}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b1}`"))
            conn.execute(text(f"CREATE TABLE `{cls.table_a1}` (id INT PRIMARY KEY, name VARCHAR(50), val INT)"))
            conn.execute(text(f"CREATE TABLE `{cls.table_a2}` (id INT PRIMARY KEY, title VARCHAR(50), score INT)"))
            conn.execute(text(f"CREATE TABLE `{cls.table_b1}` (id INT PRIMARY KEY, item VARCHAR(50), price INT)"))
            
            conn.execute(text(f"INSERT INTO `{cls.table_a1}` VALUES (1, 'Alice_A1', 100), (2, 'Bob_A1', 200)"))
            conn.execute(text(f"INSERT INTO `{cls.table_a2}` VALUES (1, 'Task_A2', 95), (2, 'Report_A2', 88)"))
            conn.execute(text(f"INSERT INTO `{cls.table_b1}` VALUES (1, 'Gadget_B1', 500), (2, 'Widget_B1', 750)"))
            conn.commit()

    @classmethod
    def tearDownClass(cls):
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a1}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_a2}`"))
            conn.execute(text(f"DROP TABLE IF EXISTS `{cls.table_b1}`"))
            conn.commit()

        db = SessionLocal()
        try:
            db.query(User).filter(User.id.in_([cls.user_num_a, cls.user_num_b, cls.user_num_c])).delete(synchronize_session=False)
            db.query(UserActiveDataset).filter(UserActiveDataset.user_id.in_([cls.user_id_a, cls.user_id_b, cls.user_id_c])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def setUp(self):
        self.client = TestClient(app)

    def test_01_two_users_activating_different_datasets(self):
        """Two authenticated users activate distinct datasets; each retains their own active state."""
        # User A activates Table A1
        resp_a = self.client.post(
            "/datasets/active",
            json={"table_name": self.table_a1},
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.json()["table_name"], self.table_a1)

        # User B activates Table B1
        resp_b = self.client.post(
            "/datasets/active",
            json={"table_name": self.table_b1},
            headers={"Authorization": f"Bearer {self.token_b}"}
        )
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_b.json()["table_name"], self.table_b1)

        # Confirm independently in table_manager
        self.assertEqual(get_current_table(self.user_id_a), self.table_a1)
        self.assertEqual(get_current_table(self.user_id_b), self.table_b1)

    def test_02_concurrent_requests_from_two_users(self):
        """Simultaneous concurrent requests from two users resolve only to their respective datasets."""
        set_current_table(self.table_a1, user_id=self.user_id_a)
        set_current_table(self.table_b1, user_id=self.user_id_b)

        results_a = []
        results_b = []

        def call_user_a():
            # Query export raw csv without X-Table-Name (relies on active dataset resolution)
            resp = self.client.get(
                "/api/export/raw/csv",
                headers={"Authorization": f"Bearer {self.token_a}"}
            )
            return resp.status_code, resp.text

        def call_user_b():
            resp = self.client.get(
                "/api/export/raw/csv",
                headers={"Authorization": f"Bearer {self.token_b}"}
            )
            return resp.status_code, resp.text

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures_a = [executor.submit(call_user_a) for _ in range(8)]
            futures_b = [executor.submit(call_user_b) for _ in range(8)]

            results_a = [f.result() for f in futures_a]
            results_b = [f.result() for f in futures_b]

        for status, text_out in results_a:
            self.assertEqual(status, 200)
            self.assertIn("Alice_A1", text_out)
            self.assertNotIn("Gadget_B1", text_out)

        for status, text_out in results_b:
            self.assertEqual(status, 200)
            self.assertIn("Gadget_B1", text_out)
            self.assertNotIn("Alice_A1", text_out)

    def test_03_cross_user_dataset_header_injection(self):
        """User A providing User B's dataset name in X-Table-Name must be strictly rejected (403)."""
        resp = self.client.get(
            "/api/export/raw/csv",
            headers={
                "Authorization": f"Bearer {self.token_a}",
                "X-Table-Name": self.table_b1
            }
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Access denied", resp.json().get("detail", ""))

    def test_04_missing_active_dataset(self):
        """User C with no uploaded datasets attempting to resolve active table receives 400 Bad Request."""
        clear_current_table(self.user_id_c)
        resp = self.client.get(
            "/api/export/raw/csv",
            headers={"Authorization": f"Bearer {self.token_c}"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No dataset uploaded yet", resp.json().get("detail", ""))

    def test_05_invalid_or_unauthenticated_identity_fails_safely(self):
        """Requests without authentication or with invalid tokens fail safely with 401."""
        # 1. Missing Authorization header
        resp_no_auth = self.client.get("/api/export/raw/csv")
        self.assertEqual(resp_no_auth.status_code, 401)

        # 2. Invalid token
        resp_bad_auth = self.client.get(
            "/api/export/raw/csv",
            headers={"Authorization": "Bearer completely-invalid-tampered-token-12345"}
        )
        self.assertEqual(resp_bad_auth.status_code, 401)

        # 3. Direct function invocation with empty user_id
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            resolve_and_authorize_dataset(user_id="", requested_table_name=self.table_a1)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_06_dataset_deletion_and_stale_active_state_cleanup(self):
        """Deleting an active dataset cleans up active references and safely switches or clears state."""
        # Create a temporary table for User A
        temp_table = f"ds_temp_del_{self.user_id_a}"
        with engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE `{temp_table}` (id INT PRIMARY KEY, note VARCHAR(50))"))
            conn.commit()

        # Set as active
        set_current_table(temp_table, user_id=self.user_id_a)
        self.assertEqual(get_current_table(self.user_id_a), temp_table)

        # Delete dataset via API
        del_resp = self.client.delete(
            f"/datasets/{temp_table}",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        self.assertEqual(del_resp.status_code, 200)

        # Active table must not remain pointed to the deleted table
        current = get_current_table(self.user_id_a)
        self.assertNotEqual(current, temp_table)

        # Subsequent resolution without X-Table-Name automatically resolves to another remaining valid table
        resolved = resolve_and_authorize_dataset(user_id=self.user_id_a, requested_table_name=None)
        self.assertIn(resolved, [self.table_a1, self.table_a2])
        self.assertNotEqual(resolved, temp_table)

    def test_07_switching_datasets_during_concurrent_requests(self):
        """User A switching active dataset mid-stream does not disrupt User B or cause state bleeding."""
        set_current_table(self.table_a1, user_id=self.user_id_a)
        set_current_table(self.table_b1, user_id=self.user_id_b)

        def user_b_continuous():
            for _ in range(5):
                resp = self.client.get("/api/export/raw/csv", headers={"Authorization": f"Bearer {self.token_b}"})
                self.assertEqual(resp.status_code, 200)
                self.assertIn("Gadget_B1", resp.text)

        def user_a_switch():
            # Switch to Table A2
            resp = self.client.post(
                "/datasets/active",
                json={"table_name": self.table_a2},
                headers={"Authorization": f"Bearer {self.token_a}"}
            )
            self.assertEqual(resp.status_code, 200)

        t_b = threading.Thread(target=user_b_continuous)
        t_a = threading.Thread(target=user_a_switch)

        t_b.start()
        t_a.start()

        t_b.join()
        t_a.join()

        # User B still has Table B1
        self.assertEqual(get_current_table(self.user_id_b), self.table_b1)
        # User A switched to Table A2
        self.assertEqual(get_current_table(self.user_id_a), self.table_a2)

    def test_08_independent_browser_tab_selections(self):
        """Simulates two browser tabs for User A providing different X-Table-Name headers concurrently."""
        # Tab 1 specifies Table A1
        resp_tab1 = self.client.get(
            "/api/export/raw/csv",
            headers={"Authorization": f"Bearer {self.token_a}", "X-Table-Name": self.table_a1}
        )
        # Tab 2 specifies Table A2
        resp_tab2 = self.client.get(
            "/api/export/raw/csv",
            headers={"Authorization": f"Bearer {self.token_a}", "X-Table-Name": self.table_a2}
        )

        self.assertEqual(resp_tab1.status_code, 200)
        self.assertEqual(resp_tab2.status_code, 200)
        self.assertIn("Alice_A1", resp_tab1.text)
        self.assertIn("Task_A2", resp_tab2.text)

    def test_09_logout_followed_by_another_user_login(self):
        """Clearing session and authenticating as a different user guarantees zero dataset leakage."""
        set_current_table(self.table_a1, user_id=self.user_id_a)
        
        # User A session active
        self.assertEqual(get_current_table(self.user_id_a), self.table_a1)

        # User B authenticates (simulating login)
        resp_login = self.client.post("/auth/login", json={"username": f"user_b_{self.test_id}", "password": "Pass12345678#B"})
        self.assertEqual(resp_login.status_code, 200)
        token_b = resp_login.json()["token"]

        # User B makes request without header
        resp_b = self.client.get("/api/export/raw/csv", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(resp_b.status_code, 200)
        self.assertIn("Gadget_B1", resp_b.text)
        self.assertNotIn("Alice_A1", resp_b.text)

    def test_10_backend_restart_and_active_state_persistence(self):
        """Simulating backend process restart recovers active dataset state from database."""
        set_current_table(self.table_a2, user_id=self.user_id_a)
        
        # Verify in DB
        db = SessionLocal()
        try:
            rec = db.query(UserActiveDataset).filter(UserActiveDataset.user_id == self.user_id_a).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.table_name, self.table_a2)
        finally:
            db.close()

        # Simulate process crash/restart by clearing in-memory dictionary
        with _LOCK:
            _USER_ACTIVE_TABLES.clear()
        self.assertEqual(len(_USER_ACTIVE_TABLES), 0)

        # After restart, get_current_table must retrieve from MySQL
        reloaded = get_current_table(self.user_id_a)
        self.assertEqual(reloaded, self.table_a2)

    def test_11_multiple_worker_consistency(self):
        """Simulates two distinct backend worker processes communicating via the database."""
        worker1_user_id = self.user_id_a
        worker2_user_id = self.user_id_a

        # Worker 1 sets active table
        set_current_table(self.table_a1, user_id=worker1_user_id)

        # Worker 2 simulates a fresh worker instance with empty local memory
        with _LOCK:
            _USER_ACTIVE_TABLES.pop(worker2_user_id, None)

        # Worker 2 reads active table (retrieves from shared DB)
        read_by_worker2 = get_current_table(worker2_user_id)
        self.assertEqual(read_by_worker2, self.table_a1)

        # Worker 2 switches active table to A2
        set_current_table(self.table_a2, user_id=worker2_user_id)

        # Worker 1 reads (simulating another worker thread/process)
        read_by_worker1 = get_current_table(worker1_user_id)
        self.assertEqual(read_by_worker1, self.table_a2)

    def test_12_modification_confirmation_remaining_bound_to_original_dataset(self):
        """Switching active dataset does NOT redirect an existing confirmation token to another table."""
        # 1. Preview modification on Table A1
        preview_resp = self.client.post(
            "/api/modification/ask",
            json={"question": "Update Alice_A1 val to 150"},
            headers={"Authorization": f"Bearer {self.token_a}", "X-Table-Name": self.table_a1}
        )
        self.assertEqual(preview_resp.status_code, 200)
        data = preview_resp.json()
        token = data.get("confirmation_token")
        self.assertIsNotNone(token)
        self.assertEqual(data.get("table_name"), self.table_a1)

        # 2. User A switches active dataset to Table A2
        set_current_table(self.table_a2, user_id=self.user_id_a)
        self.assertEqual(get_current_table(self.user_id_a), self.table_a2)

        # 3. User A executes confirmation token
        exec_resp = self.client.post(
            "/api/modification/execute",
            json={"confirmation_token": token},
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        self.assertEqual(exec_resp.status_code, 200)
        exec_data = exec_resp.json()
        self.assertTrue(exec_data.get("success"))

        # Verify: executed table in database is Table A1, NOT Table A2!
        with engine.connect() as conn:
            # Table A1 values updated (150)
            res_a1 = conn.execute(text(f"SELECT val FROM `{self.table_a1}` WHERE id=1")).scalar()
            self.assertEqual(res_a1, 150)
            # Table A2 score unchanged (remains 95)
            res_a2 = conn.execute(text(f"SELECT score FROM `{self.table_a2}` WHERE id=1")).scalar()
            self.assertEqual(res_a2, 95)


if __name__ == "__main__":
    unittest.main()
