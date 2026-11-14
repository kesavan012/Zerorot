"""
readme_builder.py — Jinja2-based README assembler for ZeroRot.

Takes all collected analysis data, loads the master Jinja2 template,
and renders it into a final README.md string.
"""
import json
import pathlib
import re

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .utils import slugify

_TEMPLATE_DIR     = pathlib.Path(__file__).parent / "templates"
_FOLDER_DESC_FILE = pathlib.Path(__file__).parent / "data" / "folder_descriptions.json"

with open(_FOLDER_DESC_FILE, "r", encoding="utf-8") as _f:
    _FOLDER_DESCS: dict = json.load(_f)


def build_readme(
    manifest_data:   dict,
    framework_data:  dict,
    content_data:    dict,
    env_vars:        list[dict],
    quickstart_steps: list[dict],
    scan_result:     dict,
    import_graph:    dict,
    mermaid_diagram: str,
) -> str:
    """
    Render the master README Jinja2 template with all collected project data.
    Returns the final README.md string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    root = scan_result["root"]

    # ── Resolve project name ───────────────────────────────────────────────────
    project_name = (
        content_data.get("app_name")
        or manifest_data.get("name")
        or root.name
    )
    display_name = slugify(project_name)

    # ── Resolve description (content_analyzer wins over manifest fallback) ─────
    description = (
        content_data.get("description", "").strip()
        or manifest_data.get("description", "").strip()
        or _generate_description(manifest_data, framework_data)
    )

    # ── Build directory component list ─────────────────────────────────────────
    components = _build_components(scan_result)

    # ── Platform / app_type enrichment ────────────────────────────────────────
    platform  = content_data.get("platform", "")
    app_type  = content_data.get("app_type", "Application")
    features  = content_data.get("features", [])

    # Merge platform into tech stack if not already present
    tech_stack = list(framework_data.get("tech_stack", []))
    if platform and platform not in tech_stack:
        tech_stack.insert(0, platform)

    context = {
        # Identity
        "project_name":     display_name,
        "raw_name":         project_name,
        "description":      description,
        "version":          manifest_data.get("version", ""),
        "lang":             manifest_data.get("lang", "unknown"),
        "package_manager":  manifest_data.get("package_manager", "unknown"),
        "manifest_file":    manifest_data.get("manifest_file", ""),
        "app_type":         app_type,
        "platform":         platform,

        # Tech stack
        "tech_stack":       tech_stack,
        "framework_label":  framework_data.get("primary", {}).get("label", ""),
        "databases":        framework_data.get("databases", []),
        "services":         framework_data.get("services", []),

        # Content analysis
        "features":         features,
        "has_features":     bool(features),

        # Sections
        "mermaid_diagram":  mermaid_diagram,
        "env_vars":         env_vars,
        "quickstart_steps": quickstart_steps,
        "tree_str":         scan_result.get("tree_str", ""),
        "components":       components,

        # Flags
        "has_docker":       manifest_data.get("has_docker", False),
        "has_makefile":     manifest_data.get("has_makefile", False),
        "has_ci":           manifest_data.get("has_ci", False),
        "has_env_vars":     bool(env_vars),
    }

    template = env.get_template("readme.md.j2")
    return template.render(**context)


# ── Description fallback ───────────────────────────────────────────────────────

def _generate_description(manifest_data: dict, framework_data: dict) -> str:
    fw = framework_data.get("primary", {}).get("label", "")
    lang_labels = {
        "javascript": "Node.js", "typescript": "TypeScript",
        "python": "Python", "go": "Go", "rust": "Rust",
        "ruby": "Ruby", "php": "PHP", "java": "Java", "dart": "Flutter / Dart",
    }
    lang   = lang_labels.get(manifest_data.get("lang", ""), "")
    dbs    = framework_data.get("databases", [])
    db_str = " and ".join(dbs[:2]) if dbs else ""

    seen: set[str] = set()
    parts: list[str] = []
    for p in [lang, fw, db_str]:
        if p and p not in seen:
            seen.add(p)
            parts.append(p)

    stack = ", ".join(parts) if parts else "a modern tech stack"
    return (
        f"A {stack} application. "
        "Built with a modular architecture for scalability and maintainability."
    )


def parts_seen(parts):
    return parts


# ── Component directory builder ────────────────────────────────────────────────

def _build_components(scan_result: dict) -> list[dict]:
    root:  pathlib.Path       = scan_result["root"]
    files: list[pathlib.Path] = scan_result["files"]
    seen_dirs: set[str]       = set()
    components: list[dict]    = []

    dirs_with_files: dict[str, int] = {}
    for f in files:
        try:
            rel   = f.relative_to(root)
            parts = rel.parts
            for depth in range(1, min(len(parts), 3)):
                dp = "/".join(parts[:depth])
                dirs_with_files[dp] = dirs_with_files.get(dp, 0) + 1
        except ValueError:
            continue

    for dir_path in sorted(dirs_with_files, key=lambda d: (d.count("/"), d)):
        folder_name = dir_path.split("/")[-1].lower()
        if folder_name in seen_dirs:
            continue
        seen_dirs.add(folder_name)

        desc = _FOLDER_DESCS.get(folder_name)
        if not desc:
            for key, val in _FOLDER_DESCS.items():
                if key in folder_name or folder_name in key:
                    desc = val
                    break
        if not desc:
            desc = f"Contains {dirs_with_files.get(dir_path, 0)} source file(s)"

        components.append({
            "path":        dir_path + "/",
            "description": desc,
            "file_count":  dirs_with_files.get(dir_path, 0),
        })

    notable_files = {
        "Dockerfile":           "Docker container image definition",
        "docker-compose.yml":   "Docker Compose multi-service orchestration",
        "Makefile":             "Makefile with convenience automation targets",
        ".env.example":         "Environment variable template — copy to .env before running",
        "tsconfig.json":        "TypeScript compiler configuration",
        "vite.config.ts":       "Vite bundler configuration",
        "jest.config.js":       "Jest test runner configuration",
        "vitest.config.ts":     "Vitest unit test configuration",
        "pubspec.yaml":         "Flutter / Dart package manifest and dependencies",
        "prisma/schema.prisma": "Prisma ORM schema — database table definitions",
        "alembic.ini":          "Alembic database migration configuration",
    }
    for fname, fdesc in notable_files.items():
        if (root / fname).exists():
            components.append({"path": fname, "description": fdesc, "file_count": 0})

    return components
