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
        """Production secrets under 32 characters (256-bit entropy) must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="only-20-chars-secret",
                DATABASE_URL="mysql+pymysql://user:pass@remotehost:3306/db",
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        self.assertIn("too short", str(ctx.exception))

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


if __name__ == "__main__":
    unittest.main()
