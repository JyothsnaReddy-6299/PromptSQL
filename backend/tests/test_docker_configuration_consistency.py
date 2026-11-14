import unittest
import os
import re
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings


class TestDockerConfigurationConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cls.backend_dir = os.path.join(cls.root_dir, "backend")
        cls.frontend_dir = os.path.join(cls.root_dir, "frontend")

    def test_01_docker_compose_structure_and_syntax(self):
        """Verify docker-compose.yml structure, dependencies, ports, and healthchecks."""
        compose_path = os.path.join(self.root_dir, "docker-compose.yml")
        self.assertTrue(os.path.exists(compose_path), "docker-compose.yml must exist at repository root")

        with open(compose_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check required services
        self.assertIn("db:", content)
        self.assertIn("backend:", content)
        self.assertIn("frontend:", content)

        # Check ports without conflicts
        self.assertIn('"3306:3306"', content)
        self.assertIn('"8000:8000"', content)
        self.assertIn('"5173:5173"', content)

        # Check healthchecks defined for services
        self.assertIn("healthcheck:", content)
        self.assertIn("mysqladmin", content, "db service must have mysqladmin ping healthcheck")
        self.assertIn("curl", content, "backend service must have curl healthcheck")
        self.assertIn("wget", content, "frontend service must have wget healthcheck")

        # Check dependency conditions
        self.assertIn("condition: service_healthy", content, "Services must wait for dependencies to be healthy")

        # Check persistent volume
        self.assertIn("mysql_data:/var/lib/mysql", content)
        self.assertIn("volumes:\n  mysql_data:", content)

    def test_02_dockerignore_security_and_exclusion(self):
        """Verify .dockerignore files prevent copying local secrets, virtualenvs, and node_modules."""
        root_ignore = os.path.join(self.root_dir, ".dockerignore")
        backend_ignore = os.path.join(self.backend_dir, ".dockerignore")
        frontend_ignore = os.path.join(self.frontend_dir, ".dockerignore")

        for path, name in [(root_ignore, "Root"), (backend_ignore, "Backend"), (frontend_ignore, "Frontend")]:
            self.assertTrue(os.path.exists(path), f"{name} .dockerignore must exist")
            with open(path, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()
                # Ensure .env is ignored
                self.assertTrue(any(".env" in p for p in patterns), f"{name} must ignore .env files")

        with open(backend_ignore, "r", encoding="utf-8") as f:
            b_text = f.read()
            self.assertIn("venv", b_text, "Backend .dockerignore must ignore virtualenv")
            self.assertIn("__pycache__", b_text, "Backend .dockerignore must ignore __pycache__")

        with open(frontend_ignore, "r", encoding="utf-8") as f:
            f_text = f.read()
            self.assertIn("node_modules", f_text, "Frontend .dockerignore must ignore node_modules")
            self.assertIn("dist", f_text, "Frontend .dockerignore must ignore dist")

    def test_03_backend_dockerfile_instructions(self):
        """Verify backend/Dockerfile has correct base, packages, directories, exposure, and commands."""
        df_path = os.path.join(self.backend_dir, "Dockerfile")
        self.assertTrue(os.path.exists(df_path))
        with open(df_path, "r", encoding="utf-8") as f:
            lines = f.read()

        self.assertIn("FROM python:3.10-slim", lines)
        self.assertIn("WORKDIR /app", lines)
        self.assertIn("curl", lines, "Dockerfile must install curl for container health check")
        self.assertIn("pip install --no-cache-dir -r requirements.txt", lines)
        self.assertIn("EXPOSE 8000", lines)
        self.assertIn("HEALTHCHECK", lines)
        self.assertIn("uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}", lines)

    def test_04_frontend_dockerfile_instructions(self):
        """Verify frontend/Dockerfile has correct base, dependencies, exposure, and commands."""
        df_path = os.path.join(self.frontend_dir, "Dockerfile")
        self.assertTrue(os.path.exists(df_path))
        with open(df_path, "r", encoding="utf-8") as f:
            lines = f.read()

        self.assertIn("FROM node:18-alpine", lines)
        self.assertIn("WORKDIR /app", lines)
        self.assertIn("RUN npm install", lines)
        self.assertIn("EXPOSE 5173", lines)
        self.assertIn("HEALTHCHECK", lines)
        self.assertIn('"npm", "run", "dev"', lines)
        self.assertIn("--host", lines)

    def test_05_backend_database_ssl_boundary_for_docker(self):
        """Verify Docker internal network database (@db:3306) does NOT trigger SSL requirement."""
        docker_db_url = "mysql+pymysql://root:root_password@db:3306/promptsql"
        s = Settings(DATABASE_URL=docker_db_url)
        self.assertFalse(s.is_remote_db, "Docker local container db must NOT be treated as remote SSL database")

        cloud_db_url = "mysql+pymysql://avnadmin:pass@mysql-aivencloud.com:12345/defaultdb"
        s_cloud = Settings(DATABASE_URL=cloud_db_url)
        self.assertTrue(s_cloud.is_remote_db, "Cloud Aiven database must be identified as remote SSL database")

    def test_06_frontend_backend_proxy_and_health_endpoint(self):
        """Verify frontend proxy dynamically supports BACKEND_URL and backend /health endpoint returns 200."""
        # 1. Backend health check endpoint
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

        # 2. Vite config proxy target
        vite_config_path = os.path.join(self.frontend_dir, "vite.config.ts")
        with open(vite_config_path, "r", encoding="utf-8") as f:
            v_content = f.read()
        self.assertIn("process.env.BACKEND_URL", v_content, "Vite proxy must support BACKEND_URL environment variable")

    def test_07_render_deployment_preservation(self):
        """Verify Render Procfile and port variables remain intact."""
        procfile_path = os.path.join(self.root_dir, "Procfile")
        self.assertTrue(os.path.exists(procfile_path), "Procfile must exist for Render deployment")
        with open(procfile_path, "r", encoding="utf-8") as f:
            proc_content = f.read()
        self.assertIn("uvicorn app.main:app", proc_content)
        self.assertIn("${PORT:-8000}", proc_content)

    def test_08_jwt_secret_mandatory_in_docker_compose_without_silent_fallback(self):
        """Verify docker-compose.yml strictly requires JWT_SECRET and has no silent insecure fallback."""
        compose_path = os.path.join(self.root_dir, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            compose_text = f.read()

        # Must not contain any default insecure fallback
        self.assertNotIn("dev-insecure-secret", compose_text, "docker-compose.yml must not contain default insecure JWT fallback")

        # Must use mandatory Docker Compose variable requirement syntax (${JWT_SECRET:?...})
        self.assertRegex(
            compose_text,
            r"JWT_SECRET=\$\{JWT_SECRET:\?[^}]+\}",
            "docker-compose.yml must require JWT_SECRET using mandatory :? error syntax"
        )

    def test_09_production_blocks_default_development_database_credentials(self):
        """Verify production environment blocks default local docker development database credentials."""
        docker_dev_db_url = "mysql+pymysql://root:root_password@db:3306/promptsql"
        with self.assertRaises(ValueError) as ctx:
            Settings(
                APP_ENV="production",
                JWT_SECRET="valid-production-secret-of-length-32-chars!",
                DATABASE_URL=docker_dev_db_url,
                GROQ_API_KEY="gsk_valid_prod_key_1234567890"
            )
        self.assertIn("Default development database credentials", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
