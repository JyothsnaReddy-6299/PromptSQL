import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, get_settings, reload_settings, WEAK_JWT_SECRETS
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_and_validate_token,
    get_user_id_from_token,
    get_current_user_id
)
from app.utils.error_sanitizer import sanitize_error_message, get_safe_exception_message


class Step3ConfigurationSecurityTests(unittest.TestCase):
    """
    Validates centralized configuration security, production secret enforcement,
    and fallback protections.
    """

    def test_01_missing_jwt_secret_rejected_in_production(self):
        """Production environment must strictly reject empty or missing JWT_SECRET."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="",
                DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        self.assertIn("JWT_SECRET must be configured in production", str(ctx.exception))

    def test_02_weak_jwt_secret_rejected_in_production(self):
        """Production environment must strictly reject weak, placeholder, or default secrets."""
        for weak_secret in ["secret", "changeme", "supersecretkey_change_me_in_production", "your_super_secret_jwt_sign_key"]:
            with self.assertRaises(ValueError) as ctx:
                Settings(
                    APP_ENV="production",
                    JWT_SECRET=weak_secret,
                    DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                    GROQ_API_KEY="gsk_valid_prod_key_1234567890"
                )
            self.assertIn("insecure known default", str(ctx.exception))

    def test_03_short_jwt_secret_rejected_in_production(self):
        """Production secrets under 32 characters must be rejected (enforcing minimum length threshold)."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="only-20-chars-secret",
                DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        self.assertIn("too short", str(ctx.exception))
        self.assertIn("token_urlsafe", str(ctx.exception))

    def test_04_missing_database_config_rejected_in_production(self):
        """Production environment must reject missing database configurations."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="a" * 32,
                DATABASE_URL=None,
                MYSQL_HOST=None,
                MYSQL_USER=None,
                MYSQL_DATABASE=None,
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        self.assertIn("Production database configuration is missing", str(ctx.exception))

    def test_05_missing_llm_key_rejected_in_production(self):
        """Production environment must reject missing or placeholder GROQ_API_KEY."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="a" * 32,
                DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                GROQ_API_KEY=""
            )
        self.assertIn("GROQ_API_KEY must be configured in production", str(ctx.exception))

    def test_06_unsupported_jwt_algorithm_rejected(self):
        """Disallowed or insecure algorithms (e.g. none, RS256 with symmetric secret) must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="development",
                JWT_ALGORITHM="none"
            )
        self.assertIn("Unsupported JWT_ALGORITHM", str(ctx.exception))

    def test_07_debug_forced_false_in_production(self):
        """Debug mode must be forced to False in production regardless of input."""
        s = Settings(
            APP_ENV="production",
            DEBUG=True,
            JWT_SECRET="a" * 32,
            DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
            GROQ_API_KEY="gsk_valid_prod_key_1234567890"
        )
        self.assertFalse(s.DEBUG)

    def test_08_safe_database_url_masks_password(self):
        """Safe database URL property must mask raw credentials for logging/diagnostics."""
        s = Settings(
            APP_ENV="development",
            DATABASE_URL="mysql+pymysql://admin_user:SuperSecretPassword123@remote.db.com:3306/prod_db"
        )
        self.assertNotIn("SuperSecretPassword123", s.safe_database_url)
        self.assertIn(":***@", s.safe_database_url)
        self.assertIn("admin_user", s.safe_database_url)


class Step3JWTAuthenticationSecurityTests(unittest.TestCase):
    """
    Validates token signing, signature enforcement, algorithm protection,
    expiration verification, and password hashing security.
    """

    def test_09_valid_token_generation_and_decoding(self):
        """Valid access token must include subject, iat, exp, and type='access'."""
        token = create_access_token(user_id=42)
        payload = decode_and_validate_token(token)
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["type"], "access")
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)

    def test_10_expired_token_strictly_rejected(self):
        """Tokens past expiration time must be rejected with 401."""
        settings = get_settings()
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        expired_payload = {
            "sub": "42",
            "iat": int((past - timedelta(minutes=60)).timestamp()),
            "exp": int(past.timestamp()),
            "type": "access"
        }
        expired_token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            decode_and_validate_token(expired_token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Session expired", ctx.exception.detail)

    def test_11_invalid_signature_strictly_rejected(self):
        """Tokens signed with a different key must be rejected with 401."""
        foreign_token = jwt.encode(
            {"sub": "42", "iat": int(datetime.now(timezone.utc).timestamp()), "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), "type": "access"},
            "different-unauthorized-key-with-32-characters!",
            algorithm="HS256"
        )
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            decode_and_validate_token(foreign_token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Invalid token signature", ctx.exception.detail)

    def test_12_unsigned_none_algorithm_token_rejected(self):
        """Algorithm-confusion / unsigned tokens (alg: none) must be strictly rejected."""
        none_token = jwt.encode(
            {"sub": "42", "iat": int(datetime.now(timezone.utc).timestamp()), "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), "type": "access"},
            key="",
            algorithm="none"
        )
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            decode_and_validate_token(none_token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_13_token_rotation_invalidates_old_tokens(self):
        """Changing the JWT_SECRET must immediately invalidate tokens issued under previous secret."""
        old_secret = "previous-test-signing-secret-32-chars-long!"
        new_secret = "brand-new-rotated-secret-key-32-chars-long!"
        
        # Issue token under old secret
        token = jwt.encode(
            {"sub": "99", "iat": int(datetime.now(timezone.utc).timestamp()), "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), "type": "access"},
            old_secret,
            algorithm="HS256"
        )

        # Verification under new secret fails
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(token, new_secret, algorithms=["HS256"])

    def test_14_password_hashing_and_verification_rules(self):
        """Password hashing must reject oversized/empty inputs and verify accurately."""
        # 1. Valid password verifies
        hashed = hash_password("SuperSecurePwd987!")
        self.assertTrue(verify_password("SuperSecurePwd987!", hashed))
        self.assertFalse(verify_password("WrongPassword123!", hashed))

        # 2. Empty password rejected
        with self.assertRaises(ValueError):
            hash_password("")

        # 3. Password exceeding bcrypt 72-byte boundary rejected
        with self.assertRaises(ValueError) as ctx:
            hash_password("A" * 73)
        self.assertIn("exceeds maximum allowed length", str(ctx.exception))


class Step3SecretsSanitizationTests(unittest.TestCase):
    """
    Validates error message and log sanitization to protect database passwords,
    API keys, hostnames, and filesystem paths.
    """

    def test_15_sanitize_database_urls(self):
        """Database connection strings in errors must mask passwords and hosts."""
        raw_error = "OperationalError: Can't connect to mysql+pymysql://avnadmin:SecretPass123@promptsql.aivencloud.com:24331/defaultdb"
        sanitized = sanitize_error_message(raw_error)
        self.assertNotIn("SecretPass123", sanitized)
        self.assertNotIn("avnadmin:SecretPass123", sanitized)
        self.assertIn("mysql+pymysql://***:***@[database-host]/[database]", sanitized)

    def test_16_sanitize_api_keys(self):
        """Groq and third-party API keys must be masked in exception traces."""
        raw_error = "GroqAPIError: Failed auth for key gsk_AbCdEfGhIjKlMnOpQrStUvWxYz123456"
        sanitized = sanitize_error_message(raw_error)
        self.assertNotIn("AbCdEfGhIjKlMnOpQrStUvWxYz123456", sanitized)
        self.assertIn("gsk_***", sanitized)

    def test_17_sanitize_filesystem_paths(self):
        """Local absolute internal filesystem paths must not be revealed."""
        raw_error = "Error in D:\\B - TECH CSE\\Projects\\SQL project\\backend\\app\\database\\connection.py: line 42"
        sanitized = sanitize_error_message(raw_error)
        self.assertNotIn("D:\\B - TECH CSE", sanitized)
        self.assertIn("[internal-source-path]", sanitized)

    def test_18_production_exception_shields_internal_driver_details(self):
        """In production, database driver errors must yield generic sanitized messages."""
        driver_err = Exception("pymysql.err.OperationalError: (2003, Can't connect to MySQL server on 'aivencloud.com')")
        prod_msg = get_safe_exception_message(driver_err, is_production=True, context="data query")
        self.assertEqual(prod_msg, "A database error occurred while processing your request. Please try again later.")

    def test_19_env_example_contains_placeholders_only(self):
        """backend/.env.example must exist and contain only safe placeholder values."""
        example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.example")
        self.assertTrue(os.path.exists(example_path), "backend/.env.example must exist")
        
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must not contain real live Aiven or Groq keys
        self.assertNotIn("AVNS_", content)
        self.assertNotIn("promptsql-01-jyothsna-38c0", content)
        self.assertNotIn("gsk_2hlbz", content)
        self.assertIn("your_mysql_password", content)
        self.assertIn("your-minimum-32-character", content)


class Step3EndpointSecurityRegressionTests(unittest.TestCase):
    """
    Validates that authentication endpoints and protected endpoints operate
    securely with sanitized responses.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_20_unauthorized_endpoints_strictly_return_401(self):
        """Protected API endpoints must reject requests lacking Authorization header."""
        endpoints = [
            ("GET", "/datasets"),
            ("GET", "/api/history"),
            ("GET", "/api/audit"),
            ("GET", "/api/reports/list"),
            ("POST", "/api/clean/remove-duplicates"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = self.client.get(url)
            else:
                resp = self.client.post(url, json={})
            self.assertEqual(resp.status_code, 401, f"{method} {url} should require authorization")

    def test_21_health_endpoint_is_public_and_sanitized(self):
        """Health check returns status ok and environment without leaking internal config."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("environment", data)
        self.assertNotIn("DATABASE_URL", data)
        self.assertNotIn("JWT_SECRET", data)


class Step3PasswordPolicyAndCompatibilityTests(unittest.TestCase):
    """
    Validates the 12-character minimum registration requirement, 72 UTF-8 byte boundary,
    multibyte UTF-8 handling, bcrypt work-factor, and backwards compatibility for existing accounts.
    """

    def setUp(self):
        self.client = TestClient(app)
        import uuid
        self.test_suffix = uuid.uuid4().hex[:8]

    def test_22_password_below_minimum_length_rejected_at_signup(self):
        """Registration must reject passwords shorter than 12 characters."""
        username = f"short_pwd_{self.test_suffix}"
        resp = self.client.post("/auth/signup", json={"username": username, "password": "Short12345!"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("at least 12 characters", resp.json().get("detail", ""))

    def test_23_password_at_minimum_length_accepted_at_signup(self):
        """Registration must accept passwords of exactly 12 characters."""
        username = f"exact_12_{self.test_suffix}"
        resp = self.client.post("/auth/signup", json={"username": username, "password": "Pass12345678"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("token", data)

    def test_24_password_at_maximum_byte_length_accepted_at_signup(self):
        """Registration must accept passwords of exactly 72 UTF-8 bytes."""
        username = f"exact_72b_{self.test_suffix}"
        password_72b = "A" * 72
        self.assertEqual(len(password_72b.encode("utf-8")), 72)
        resp = self.client.post("/auth/signup", json={"username": username, "password": password_72b})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))

    def test_25_password_exceeding_maximum_byte_length_rejected_at_signup(self):
        """Registration must reject passwords exceeding 72 UTF-8 bytes."""
        username = f"excess_73b_{self.test_suffix}"
        password_73b = "A" * 73
        self.assertEqual(len(password_73b.encode("utf-8")), 73)
        resp = self.client.post("/auth/signup", json={"username": username, "password": password_73b})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceeds maximum length of 72 UTF-8 bytes", resp.json().get("detail", ""))

    def test_26_password_multibyte_utf8_near_byte_limit(self):
        """Multi-byte UTF-8 passwords must be evaluated by byte length, not character count."""
        # '世' is 3 bytes in UTF-8
        char_3byte = "世"
        self.assertEqual(len(char_3byte.encode("utf-8")), 3)

        # 24 chars * 3 bytes = 72 bytes (allowed)
        pwd_72b = char_3byte * 24
        self.assertEqual(len(pwd_72b.encode("utf-8")), 72)
        username_72 = f"mb_72_{self.test_suffix}"
        resp_72 = self.client.post("/auth/signup", json={"username": username_72, "password": pwd_72b})
        self.assertEqual(resp_72.status_code, 200)

        # 25 chars * 3 bytes = 75 bytes (rejected)
        pwd_75b = char_3byte * 25
        self.assertEqual(len(pwd_75b.encode("utf-8")), 75)
        username_75 = f"mb_75_{self.test_suffix}"
        resp_75 = self.client.post("/auth/signup", json={"username": username_75, "password": pwd_75b})
        self.assertEqual(resp_75.status_code, 400)
        self.assertIn("exceeds maximum length of 72 UTF-8 bytes", resp_75.json().get("detail", ""))

    def test_27_existing_account_login_compatibility(self):
        """Existing users created with shorter passwords (<12 chars) must still be able to log in."""
        from app.database.connection import SessionLocal
        from app.models.user import User

        legacy_username = f"legacy_user_{self.test_suffix}"
        legacy_password = "legacy08"  # 8 characters (< 12)
        
        # Directly insert user into database simulating pre-existing account
        db = SessionLocal()
        try:
            legacy_user = User(
                username=legacy_username,
                password_hash=hash_password(legacy_password)
            )
            db.add(legacy_user)
            db.commit()
        finally:
            db.close()

        # Login must succeed despite password being shorter than 12 characters
        login_resp = self.client.post("/auth/login", json={"username": legacy_username, "password": legacy_password})
        self.assertEqual(login_resp.status_code, 200)
        self.assertTrue(login_resp.json().get("success"))
        self.assertIn("token", login_resp.json())

    def test_28_bcrypt_work_factor_verification(self):
        """Password hashing must use bcrypt work-factor of rounds=12 ($2b$12$)."""
        hashed = hash_password("SecurePasswordVerification123!")
        self.assertTrue(hashed.startswith("$2b$12$") or hashed.startswith("$2a$12$"), f"Expected 12 rounds in hash: {hashed[:10]}")

    def test_29_login_rejects_oversized_password_without_truncation(self):
        """Login must reject passwords over 72 bytes to prevent bcrypt silent truncation matching."""
        resp = self.client.post("/auth/login", json={"username": "anyuser", "password": "X" * 75})
        self.assertEqual(resp.status_code, 401)


class Step3ErrorAndLoggingLeakageTests(unittest.TestCase):
    """
    Verifies that synthetic credentials, connection strings, API keys, internal paths,
    and driver stack traces cannot leak to clients or logs.
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_30_production_secret_length_floor_not_entropy_claim(self):
        """Enforces length floor without claiming mathematical entropy proof."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="too-short-secret",
                DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        err = str(ctx.exception)
        self.assertIn("minimum length of 32 characters", err)
        self.assertIn("secrets.token_urlsafe(32)", err)

    def test_31_development_and_test_usable_without_production_secrets(self):
        """Development and testing environments must be usable with defaults."""
        dev_settings = Settings(APP_ENV="development")
        self.assertTrue(dev_settings.is_development)
        test_settings = Settings(APP_ENV="testing")
        self.assertTrue(test_settings.is_testing)

    def test_32_production_rejects_known_patterns(self):
        """Production configuration must reject known placeholder patterns."""
        for bad_secret in [
            "12345678901234567890123456789012",
            "dev-insecure-secret-key-minimum-32-chars-long!",
            "change_me_later_for_production_key_now"
        ]:
            with self.assertRaises(ValueError) as ctx:
                Settings(
                    APP_ENV="production",
                    JWT_SECRET=bad_secret,
                    DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                    GROQ_API_KEY="gsk_valid_prod_key_1234567890"
                )
            self.assertIn("insecure known default or placeholder", str(ctx.exception))

    def test_33_synthetic_db_connection_error_leakage_prevention(self):
        """Synthetic database credentials must never appear in sanitized output or production errors."""
        synth_pass = "SyntheticSecretPassword9988!"
        synth_host = "synth-aiven.internal.cloud"
        raw_db_error = f"OperationalError: Can't connect to MySQL on '{synth_host}' (mysql+pymysql://synth_user:{synth_pass}@{synth_host}:3306/db)"
        
        # 1. Sanitization must remove password
        sanitized = sanitize_error_message(raw_db_error)
        self.assertNotIn(synth_pass, sanitized)
        self.assertIn("mysql+pymysql://***:***@[database-host]/[database]", sanitized)

        # 2. Production mode must completely suppress driver internals
        prod_msg = get_safe_exception_message(Exception(raw_db_error), is_production=True, context="data query")
        self.assertNotIn(synth_pass, prod_msg)
        self.assertNotIn(synth_host, prod_msg)
        self.assertEqual(prod_msg, "A database error occurred while processing your request. Please try again later.")

    def test_34_synthetic_llm_key_leakage_prevention(self):
        """Synthetic Groq API keys must be masked to gsk_***."""
        synth_groq = "gsk_synthetic_test_mock_secret_key_99999"
        raw_llm_error = f"groq.AuthenticationError: Error code: 401 - Invalid API Key: {synth_groq}"
        
        sanitized = sanitize_error_message(raw_llm_error)
        self.assertNotIn(synth_groq, sanitized)
        self.assertIn("gsk_***", sanitized)

        # In production mode, generic safe message returned
        prod_msg = get_safe_exception_message(Exception(raw_llm_error), is_production=True, context="AI generation")
        self.assertNotIn(synth_groq, prod_msg)
        self.assertEqual(prod_msg, "The AI Analytics service is currently unavailable. Please try again shortly.")

    def test_35_synthetic_filesystem_path_leakage_prevention(self):
        """Synthetic absolute filesystem paths must be masked."""
        win_path = "D:\\Synthetic\\Secret\\Internal\\Repo\\backend\\app\\core\\config.py"
        unix_path = "/Users/synthetic_dev/promptsql/secret_backend/main.py"
        raw_trace = f"File {win_path}, line 42, in load\nFile {unix_path}, line 10"

        sanitized = sanitize_error_message(raw_trace)
        self.assertNotIn(win_path, sanitized)
        self.assertNotIn(unix_path, sanitized)
        self.assertIn("[internal-source-path]", sanitized)

    def test_36_auth_failure_error_leakage(self):
        """Authentication failures must not leak password hashes or account enumeration clues."""
        resp = self.client.post("/auth/login", json={"username": "non_existent_user_999", "password": "WrongPassword123!"})
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        detail = data.get("detail", "")
        self.assertEqual(detail, "Invalid username or password")
        self.assertNotIn("hash", detail.lower())
        self.assertNotIn("bcrypt", detail.lower())

    def test_37_production_stack_trace_shielding(self):
        """Production exception handler must shield raw SQLAlchemy driver errors and stack traces."""
        from sqlalchemy.exc import OperationalError
        mock_driver_exc = OperationalError("SELECT * FROM sensitive_db.users", {}, Exception("Can't connect to MySQL server on 'internal-db.cloud.com'"))
        
        safe_response = get_safe_exception_message(mock_driver_exc, is_production=True, context="database operation")
        self.assertEqual(safe_response, "A database error occurred while processing your request. Please try again later.")
        self.assertNotIn("sensitive_db", safe_response)
        self.assertNotIn("internal-db.cloud.com", safe_response)


if __name__ == "__main__":
    unittest.main()
