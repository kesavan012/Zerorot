"""
quickstart_builder.py — Generates Quick Start & Execution commands for ZeroRot.

Determines the correct install/run commands based on the detected language,
package manager, framework type, and presence of Docker / Makefile.
"""
import pathlib
from typing import Optional


# ── Package-manager command templates ─────────────────────────────────────────

PM_INSTALL = {
    "npm":      "npm install",
    "pnpm":     "pnpm install",
    "yarn":     "yarn install",
    "bun":      "bun install",
    "pip":      "pip install -r requirements.txt",
    "poetry":   "poetry install",
    "pipenv":   "pipenv install",
    "pdm":      "pdm install",
    "go":       "go mod download",
    "cargo":    "cargo build",
    "composer": "composer install",
    "bundler":  "bundle install",
    "gradle":   "./gradlew build",
    "maven":    "mvn install",
    "pub":      "flutter pub get",
}

PM_RUN_DEV = {
    "npm":      "npm run dev",
    "pnpm":     "pnpm dev",
    "yarn":     "yarn dev",
    "bun":      "bun dev",
    "poetry":   "poetry run python main.py",
    "pipenv":   "pipenv run python main.py",
    "pdm":      "pdm run python main.py",
    "go":       "go run ./cmd/main.go",
    "cargo":    "cargo run",
    "composer": "php artisan serve",
    "bundler":  "bundle exec rails server",
    "gradle":   "./gradlew bootRun",
    "maven":    "mvn spring-boot:run",
    "pub":      "flutter run",
}

PM_TEST = {
    "npm":      "npm test",
    "pnpm":     "pnpm test",
    "yarn":     "yarn test",
    "bun":      "bun test",
    "pip":      "pytest",
    "poetry":   "poetry run pytest",
    "pipenv":   "pipenv run pytest",
    "go":       "go test ./...",
    "cargo":    "cargo test",
    "composer": "php artisan test",
    "bundler":  "bundle exec rspec",
    "gradle":   "./gradlew test",
    "maven":    "mvn test",
    "pub":      "flutter test",
}


def build_quickstart(
    manifest_data: dict,
    framework_data: dict,
    scan_result: dict,
) -> list[dict]:
    """
    Build a list of ordered Quick Start steps.

    Each step is:
        {'title': str, 'commands': list[str]}
    """
    pm: str = manifest_data.get("package_manager", "unknown")
    lang: str = manifest_data.get("lang", "unknown")
    scripts: dict = manifest_data.get("scripts", {})
    root: pathlib.Path = scan_result["root"]
    has_docker: bool = manifest_data.get("has_docker", False)
    has_makefile: bool = manifest_data.get("has_makefile", False)
    fw_type: str = framework_data.get("primary", {}).get("type", "unknown")

    steps: list[dict] = []

    # ── Step 1: Clone ──────────────────────────────────────────────────────────
    steps.append({
        "title": "Clone the Repository",
        "commands": [
            f"git clone https://github.com/your-org/{manifest_data.get('name', 'project')}.git",
            f"cd {manifest_data.get('name', 'project')}",
        ],
    })

    # ── Step 2: Python venv setup ──────────────────────────────────────────────
    if lang == "python" and pm in ("pip", "pipenv"):
        steps.append({
            "title": "Create Virtual Environment",
            "commands": [
                "python -m venv .venv",
                "# Windows:",
                ".venv\\Scripts\\activate",
                "# macOS / Linux:",
                "source .venv/bin/activate",
            ],
        })

    # ── Step 3: Install dependencies ──────────────────────────────────────────
    install_cmd = PM_INSTALL.get(pm, "# Install dependencies")
    steps.append({
        "title": "Install Dependencies",
        "commands": [install_cmd],
    })

    # ── Step 4: Configure environment ─────────────────────────────────────────
    env_src = _find_env_example(root)
    if env_src:
        steps.append({
            "title": "Configure Environment",
            "commands": [
                f"cp {env_src} .env",
                "# Edit .env and fill in required values",
            ],
        })

    # ── Step 5: Docker infrastructure ─────────────────────────────────────────
    if has_docker:
        compose_file = _find_compose_file(root)
        cmd = f"docker compose -f {compose_file} up -d" if compose_file else "docker compose up -d"
        steps.append({
            "title": "Start Infrastructure (Docker)",
            "commands": [cmd],
        })

    # ── Step 6: Database migrations ───────────────────────────────────────────
    migration_cmd = _detect_migration_command(manifest_data, scan_result)
    if migration_cmd:
        steps.append({
            "title": "Run Database Migrations",
            "commands": [migration_cmd],
        })

    # ── Step 7: Run the application ───────────────────────────────────────────
    run_cmd = _resolve_run_command(pm, lang, scripts, scan_result)
    steps.append({
        "title": "Start the Application",
        "commands": [run_cmd],
    })

    # ── Step 8: Run tests ──────────────────────────────────────────────────────
    test_cmd = _resolve_test_command(pm, scripts)
    steps.append({
        "title": "Run Tests",
        "commands": [test_cmd],
    })

    return steps


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_env_example(root: pathlib.Path) -> Optional[str]:
    for name in (".env.example", ".env.sample", ".env.template"):
        if (root / name).exists():
            return name
    return None


def _find_compose_file(root: pathlib.Path) -> Optional[str]:
    for name in ("docker-compose.yml", "docker-compose.yaml",
                 "docker/compose.dev.yml", "docker/compose.yml"):
        if (root / name).exists():
            return name
    return None


def _detect_migration_command(manifest_data: dict, scan_result: dict) -> Optional[str]:
    """Return a migration command if the project uses a known migration tool."""
    deps = {**manifest_data.get("dependencies", {}), **manifest_data.get("dev_dependencies", {})}
    dep_lower = {k.lower() for k in deps}
    pm = manifest_data.get("package_manager", "")
    root = scan_result["root"]

    # Prisma
    if "prisma" in dep_lower:
        return "npx prisma migrate dev"
    # Alembic
    if "alembic" in dep_lower or (root / "alembic.ini").exists():
        return "alembic upgrade head"
    # Django
    if "django" in dep_lower:
        return "python manage.py migrate"
    # Sequelize
    if "sequelize" in dep_lower:
        return "npx sequelize-cli db:migrate"
    # TypeORM
    if "typeorm" in dep_lower:
        return "npx typeorm migration:run"
    # Rails
    if manifest_data.get("lang") == "ruby":
        return "bundle exec rails db:migrate"
    # Flyway / Liquibase (Java)
    if (root / "flyway.conf").exists():
        return "mvn flyway:migrate"

    return None


def _resolve_run_command(pm: str, lang: str, scripts: dict, scan_result: dict) -> str:
    """Pick the best run command, preferring explicit script definitions."""
    # Check package.json scripts for well-known dev/start targets
    for script_name in ("dev", "start:dev", "serve", "start"):
        if script_name in scripts:
            runner = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(pm, "npm run")
            return f"{runner} {script_name}"

    # Python: detect entry point file
    if lang == "python":
        entries = scan_result.get("entry_points", [])
        if entries:
            entry = entries[0].name
            pm_run = {
                "poetry": f"poetry run python {entry}",
                "pipenv": f"pipenv run python {entry}",
            }
            return pm_run.get(pm, f"python {entry}")

    return PM_RUN_DEV.get(pm, "# Run the application")


def _resolve_test_command(pm: str, scripts: dict) -> str:
    """Pick the test command, preferring the defined script."""
    for script_name in ("test", "test:unit", "test:run"):
        if script_name in scripts:
            runner = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn"}.get(pm, "npm run")
            return f"{runner} {script_name}"
    return PM_TEST.get(pm, "# Run tests")
