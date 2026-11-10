import os
import re
from typing import List, Optional
from functools import lru_cache
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

# Locate and load .env file from backend or root directory
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_base_dir, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
load_dotenv()

# To generate a cryptographically secure, high-entropy secret for production:
# python -c "import secrets; print(secrets.token_urlsafe(32))"
WEAK_JWT_SECRETS = {
    "secret",
    "changeme",
    "password",
    "jwtsecret",
    "supersecretkey_change_me_in_production",
    "your_jwt_secret",
    "your-super-secret-key",
    "your_super_secret_jwt_sign_key",
    "your-minimum-32-character-cryptographically-secure-secret-key-here",
    "dev-insecure-secret-key-minimum-32-chars-long!",
    "12345678901234567890123456789012",
    "abcdefghijklmnopqrstuvwxyz123456",
    "00000000000000000000000000000000",
}

ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


class Settings(BaseModel):
    """
    Centralized, strongly-validated application configuration.
    Validates required secrets and enforces security boundaries across environments.
    """
    APP_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=False)

    # Database Settings
    DATABASE_URL: Optional[str] = None
    MYSQL_HOST: Optional[str] = None
    MYSQL_PORT: str = "3306"
    MYSQL_USER: Optional[str] = None
    MYSQL_PASSWORD: Optional[str] = None
    MYSQL_DATABASE: Optional[str] = None

    # JWT Authentication
    JWT_SECRET: str = Field(default="dev-insecure-secret-key-minimum-32-chars-long!")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)

    # Groq LLM
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = Field(default="qwen/qwen3.8-27b")

    # Network / CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV.lower() in ("testing", "test")

    @property
    def is_development(self) -> bool:
        return not (self.is_production or self.is_testing)

    @property
    def resolved_database_url(self) -> str:
        """
        Returns the resolved, normalized database connection URL.
        """
        url = self.DATABASE_URL
        if not url:
            if self.MYSQL_USER and self.MYSQL_HOST and self.MYSQL_DATABASE:
                pwd = self.MYSQL_PASSWORD or ""
                url = (
                    f"mysql+pymysql://{self.MYSQL_USER}:{pwd}"
                    f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
                )
            else:
                url = "mysql+pymysql://root:@localhost:3306/promptsql"

        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+pymysql://", 1)
        return url

    @property
    def safe_database_url(self) -> str:
        """
        Returns the database URL with password masked for safe logging/diagnostics.
        """
        raw = self.resolved_database_url
        return re.sub(r":([^:@]+)@", r":***@", raw)

    @property
    def is_remote_db(self) -> bool:
        """
        Detects if database is hosted on a remote cloud provider requiring SSL transport.
        """
        url = self.resolved_database_url.lower()
        return (
            ("localhost" not in url and "127.0.0.1" not in url)
            or "aivencloud" in url
            or "amazonaws" in url
            or "ssl" in url
        )

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        env = self.APP_ENV.lower().strip()

        # Enforce debug settings in production
        if env in ("production", "prod"):
            if self.DEBUG:
                # Force DEBUG to False in production
                object.__setattr__(self, "DEBUG", False)

        # Validate JWT Algorithm
        if self.JWT_ALGORITHM not in ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"Unsupported JWT_ALGORITHM '{self.JWT_ALGORITHM}'. "
                f"Must be one of: {sorted(list(ALLOWED_JWT_ALGORITHMS))}"
            )

        # Validate Access Token Expiration
        if self.ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer.")

        # In production, enforce strict secrets validation
        if env in ("production", "prod"):
            # 1. JWT Secret validation
            secret = (self.JWT_SECRET or "").strip()
            if not secret:
                raise ValueError("CRITICAL: JWT_SECRET must be configured in production environment.")
            lower_secret = secret.lower()
            if (
                lower_secret in WEAK_JWT_SECRETS
                or "change_me" in lower_secret
                or "your_jwt" in lower_secret
                or "placeholder" in lower_secret
                or "dev-insecure" in lower_secret
            ):
                raise ValueError(
                    "CRITICAL: JWT_SECRET uses an insecure known default or placeholder value. "
                    "A cryptographically generated secret is required in production. "
                    "Generate a secure secret using: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            if len(secret) < 32:
                raise ValueError(
                    f"CRITICAL: JWT_SECRET is too short ({len(secret)} characters). "
                    "Production signing secrets must have a minimum length of 32 characters. "
                    "Note: string length alone does not verify cryptographic entropy; "
                    "generate a high-entropy secret using: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

            # 2. Database credentials
            db_url = self.DATABASE_URL
            if not db_url:
                if not (self.MYSQL_USER and self.MYSQL_HOST and self.MYSQL_DATABASE):
                    raise ValueError(
                        "CRITICAL: Production database configuration is missing. "
                        "Provide either DATABASE_URL or MYSQL_HOST, MYSQL_USER, and MYSQL_DATABASE."
                    )
            if db_url and ("localhost" in db_url or "127.0.0.1" in db_url) and not os.getenv("ALLOW_LOCAL_PROD_DB"):
                # Warning or check for accidental local database in production
                pass

            # 3. LLM API Key in production
            groq_key = (self.GROQ_API_KEY or "").strip()
            if not groq_key or groq_key.startswith("gsk_your_groq_api_key"):
                raise ValueError("CRITICAL: GROQ_API_KEY must be configured in production environment.")

        # Normalize GROQ model name
        if "qwen3.6" in self.GROQ_MODEL.lower():
            object.__setattr__(self, "GROQ_MODEL", "qwen/qwen3.8-27b")

        return self

    @classmethod
    def load_from_env(cls) -> "Settings":
        """
        Instantiates Settings by parsing current environment variables.
        """
        cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
        cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] or ["*"]

        debug_val = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

        return cls(
            APP_ENV=os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development",
            DEBUG=debug_val,
            DATABASE_URL=os.getenv("DATABASE_URL"),
            MYSQL_HOST=os.getenv("MYSQL_HOST"),
            MYSQL_PORT=os.getenv("MYSQL_PORT", "3306"),
            MYSQL_USER=os.getenv("MYSQL_USER"),
            MYSQL_PASSWORD=os.getenv("MYSQL_PASSWORD"),
            MYSQL_DATABASE=os.getenv("MYSQL_DATABASE"),
            JWT_SECRET=os.getenv("JWT_SECRET") or "dev-insecure-secret-key-minimum-32-chars-long!",
            JWT_ALGORITHM=os.getenv("JWT_ALGORITHM", "HS256").upper(),
            ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
            GROQ_API_KEY=os.getenv("GROQ_API_KEY"),
            GROQ_MODEL=os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
            CORS_ORIGINS=cors_origins,
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns the cached application settings instance.
    """
    return Settings.load_from_env()


def reload_settings() -> Settings:
    """
    Clears cache and reloads settings from environment (used in test cases).
    """
    get_settings.cache_clear()
    return get_settings()
