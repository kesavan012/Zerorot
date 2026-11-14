"""
analyzer.py — Project manifest parser for ZeroRot.

Finds and parses the dependency manifest (package.json, requirements.txt,
pyproject.toml, go.mod, Cargo.toml, etc.) and returns structured metadata
about the project name, stack, dependencies, and package manager.
"""
import json
import pathlib
import re
import sys
from typing import Any, Optional

# tomllib is stdlib in Python 3.11+; fall back to tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None  # type: ignore[assignment]


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_manifest(project_path: pathlib.Path) -> dict:
    """
    Locate and parse the project's dependency manifest.

    Returns a dict with keys:
        name, description, version, lang, package_manager,
        dependencies, dev_dependencies, scripts, manifest_file,
        has_docker, has_makefile, has_ci
    """
    result: dict[str, Any] = {
        "name": project_path.name,
        "description": "",
        "version": "1.0.0",
        "lang": "unknown",
        "package_manager": "unknown",
        "dependencies": {},
        "dev_dependencies": {},
        "scripts": {},
        "manifest_file": None,
        "has_docker": _has_file(project_path, {"docker-compose.yml", "docker-compose.yaml", "Dockerfile"}),
        "has_makefile": (project_path / "Makefile").exists(),
        "has_ci": (project_path / ".github" / "workflows").exists()
                  or (project_path / ".gitlab-ci.yml").exists()
                  or (project_path / ".circleci").exists(),
    }

    parsers = [
        (_parse_package_json,     project_path / "package.json"),
        (_parse_pyproject_toml,   project_path / "pyproject.toml"),
        (_parse_requirements_txt, project_path / "requirements.txt"),
        (_parse_go_mod,           project_path / "go.mod"),
        (_parse_cargo_toml,       project_path / "Cargo.toml"),
        (_parse_composer_json,    project_path / "composer.json"),
        (_parse_gemfile,          project_path / "Gemfile"),
        (_parse_pipfile,          project_path / "Pipfile"),
        (_parse_build_gradle,     project_path / "build.gradle"),
        (_parse_pom_xml,          project_path / "pom.xml"),
        (_parse_pubspec_yaml,     project_path / "pubspec.yaml"),
    ]

    for parser, manifest_path in parsers:
        if manifest_path.exists():
            try:
                data = parser(manifest_path)
                # Merge — only overwrite if the new value is non-empty
                for k, v in data.items():
                    if v or not result.get(k):
                        result[k] = v
                result["manifest_file"] = manifest_path.name
                break
            except Exception:
                continue

    return result


# ── Private parsers ────────────────────────────────────────────────────────────

def _has_file(root: pathlib.Path, names: set) -> bool:
    return any((root / n).exists() for n in names)


def _parse_package_json(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    root = path.parent
    if (root / "pnpm-lock.yaml").exists():
        pm = "pnpm"
    elif (root / "yarn.lock").exists():
        pm = "yarn"
    elif (root / "bun.lockb").exists():
        pm = "bun"
    else:
        pm = "npm"

    # Detect TypeScript projects
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    lang = "typescript" if "typescript" in deps or "ts-node" in deps else "javascript"

    return {
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "version": data.get("version", ""),
        "dependencies": data.get("dependencies", {}),
        "dev_dependencies": data.get("devDependencies", {}),
        "scripts": data.get("scripts", {}),
        "lang": lang,
        "package_manager": pm,
    }


def _parse_pyproject_toml(path: pathlib.Path) -> dict:
    if tomllib is None:
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)

    # Support both PEP 621 [project] and Poetry [tool.poetry]
    project = data.get("project") or data.get("tool", {}).get("poetry", {})
    if not project:
        return {}

    raw_deps = project.get("dependencies", {})
    if isinstance(raw_deps, list):
        deps = {}
        for item in raw_deps:
            if isinstance(item, str):
                pkg = re.split(r"[>=<!~\[;]", item)[0].strip()
                if pkg and pkg != "python":
                    deps[pkg] = "*"
    elif isinstance(raw_deps, dict):
        deps = {k: str(v) for k, v in raw_deps.items() if k != "python"}
    else:
        deps = {}

    root = path.parent
    if (root / "poetry.lock").exists():
        pm = "poetry"
    elif (root / "Pipfile").exists():
        pm = "pipenv"
    elif (root / "pdm.lock").exists():
        pm = "pdm"
    else:
        pm = "pip"

    return {
        "name": project.get("name", ""),
        "description": project.get("description", ""),
        "version": str(project.get("version", "")),
        "dependencies": deps,
        "lang": "python",
        "package_manager": pm,
    }


def _parse_requirements_txt(path: pathlib.Path) -> dict:
    deps: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg = re.split(r"[>=<!~\[;]", line)[0].strip()
            if pkg:
                deps[pkg.lower()] = "*"
    return {
        "dependencies": deps,
        "lang": "python",
        "package_manager": "pip",
    }


def _parse_go_mod(path: pathlib.Path) -> dict:
    deps: dict[str, str] = {}
    name = ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    m = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
    if m:
        name = m.group(1).split("/")[-1]

    for m in re.finditer(r"^\s+(\S+)\s+v([\d.]+)", content, re.MULTILINE):
        pkg = m.group(1).split("/")[-1]
        deps[pkg] = f"v{m.group(2)}"

    return {
        "name": name,
        "dependencies": deps,
        "lang": "go",
        "package_manager": "go",
    }


def _parse_cargo_toml(path: pathlib.Path) -> dict:
    if tomllib is None:
        return {"lang": "rust", "package_manager": "cargo"}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    pkg = data.get("package", {})
    raw_deps = data.get("dependencies", {})
    deps = {k: (v if isinstance(v, str) else str(v.get("version", "*")))
            for k, v in raw_deps.items()}
    return {
        "name": pkg.get("name", ""),
        "description": pkg.get("description", ""),
        "version": str(pkg.get("version", "")),
        "dependencies": deps,
        "lang": "rust",
        "package_manager": "cargo",
    }


def _parse_composer_json(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    name = data.get("name", "").split("/")[-1]
    return {
        "name": name,
        "description": data.get("description", ""),
        "dependencies": data.get("require", {}),
        "dev_dependencies": data.get("require-dev", {}),
        "lang": "php",
        "package_manager": "composer",
    }


def _parse_gemfile(path: pathlib.Path) -> dict:
    deps: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*gem\s+['\"]([^'\"]+)['\"]", line)
            if m:
                deps[m.group(1)] = "*"
    return {
        "dependencies": deps,
        "lang": "ruby",
        "package_manager": "bundler",
    }


def _parse_pipfile(path: pathlib.Path) -> dict:
    if tomllib is None:
        return {"lang": "python", "package_manager": "pipenv"}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    deps = {k: str(v) for k, v in data.get("packages", {}).items()}
    dev_deps = {k: str(v) for k, v in data.get("dev-packages", {}).items()}
    return {
        "dependencies": deps,
        "dev_dependencies": dev_deps,
        "lang": "python",
        "package_manager": "pipenv",
    }


def _parse_build_gradle(path: pathlib.Path) -> dict:
    deps: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Extract group:artifact:version patterns
    for m in re.finditer(r"['\"]([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([^'\"]+)['\"]", content):
        deps[m.group(2)] = m.group(3)
    return {
        "dependencies": deps,
        "lang": "java",
        "package_manager": "gradle",
    }


def _parse_pom_xml(path: pathlib.Path) -> dict:
    import xml.etree.ElementTree as ET
    deps: dict[str, str] = {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        for dep in root.iter(f"{ns}dependency"):
            artifact = dep.findtext(f"{ns}artifactId")
            version = dep.findtext(f"{ns}version") or "*"
            if artifact:
                deps[artifact] = version
        name_el = root.find(f"{ns}artifactId")
        name = name_el.text if name_el is not None else ""
        desc_el = root.find(f"{ns}description")
        desc = desc_el.text if desc_el is not None else ""
    except Exception:
        return {"lang": "java", "package_manager": "maven"}

    return {
        "name": name,
        "description": desc,
        "dependencies": deps,
        "lang": "java",
        "package_manager": "maven",
    }


def _parse_pubspec_yaml(path: pathlib.Path) -> dict:
    """Parse Flutter/Dart pubspec.yaml manifest."""
    import re
    deps: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"lang": "dart", "package_manager": "pub"}

    # name
    name_m = re.search(r"^name:\s*['\"]?([A-Za-z0-9_\-]+)", content, re.MULTILINE)
    name = name_m.group(1) if name_m else ""

    # description
    desc_m = re.search(r"^description:\s*['\"]?(.+?)['\"]?\s*$", content, re.MULTILINE)
    description = desc_m.group(1).strip() if desc_m else ""

    # version
    ver_m = re.search(r"^version:\s*([0-9][^\s]+)", content, re.MULTILINE)
    version = ver_m.group(1) if ver_m else "1.0.0"

    # dependencies block — capture until next top-level key or EOF
    dep_section = re.search(
        r"^dependencies:\s*\n((?:[ \t]+.+\n?)*)", content, re.MULTILINE
    )
    if dep_section:
        for line in dep_section.group(1).splitlines():
            m = re.match(r"^\s{2}([A-Za-z][A-Za-z0-9_\-]+)\s*:", line)
            if m and m.group(1) != "flutter":
                deps[m.group(1)] = "*"

    return {
        "name":            name,
        "description":     description,
        "version":         version,
        "lang":            "dart",
        "package_manager": "pub",
        "dependencies":    deps,
        "dev_dependencies": {},
        "scripts":         {},
        "manifest_file":   "pubspec.yaml",
    }
