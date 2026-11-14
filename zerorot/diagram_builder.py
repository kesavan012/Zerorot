"""
diagram_builder.py — Mermaid.js flowchart generator for ZeroRot.

Analyses the folder structure, import graph, framework type, and detected
databases to produce a `flowchart TD` Mermaid diagram representing the
project's architecture.
"""
import pathlib
import re
from typing import Optional


# ── Layer discovery from folder names ─────────────────────────────────────────

LAYER_FOLDERS = {
    "api":        ("API Layer",         "route definitions and HTTP handlers"),
    "routes":     ("Router",            "URL-to-handler mappings"),
    "controllers":("Controllers",       "request processing and response formatting"),
    "handlers":   ("Handlers",          "endpoint logic"),
    "services":   ("Services",          "business logic and application operations"),
    "service":    ("Services",          "business logic and application operations"),
    "workers":    ("Workers",           "async background task processors"),
    "tasks":      ("Task Queue",        "queued job definitions"),
    "jobs":       ("Jobs",              "scheduled and background jobs"),
    "middleware": ("Middleware",        "auth, logging, and request pipeline"),
    "models":     ("Models",            "data entities and ORM schemas"),
    "schemas":    ("Schemas",           "validation and data-shape definitions"),
    "db":         ("Database Layer",    "connection, queries, and migrations"),
    "database":   ("Database Layer",    "connection, queries, and migrations"),
    "repositories":("Repositories",    "typed CRUD operations per entity"),
    "repo":       ("Repositories",     "typed CRUD operations per entity"),
    "core":       ("Core",             "domain logic and business rules"),
    "domain":     ("Domain",           "business entities and domain services"),
    "graphql":    ("GraphQL",          "schema, resolvers, and mutations"),
    "grpc":       ("gRPC",             "remote procedure call service handlers"),
    "events":     ("Event Bus",        "domain events and message schemas"),
    "queues":     ("Message Queue",    "event publishing and consumer groups"),
    "websocket":  ("WebSocket",        "real-time bidirectional communication"),
    "cache":      ("Cache Layer",      "Redis or in-memory caching"),
    "auth":       ("Auth",             "authentication and authorisation"),
    "config":     ("Config",           "environment and application settings"),
}

# Map of database label → Mermaid node style
DB_STYLES = {
    "PostgreSQL": "fill:#336791,color:#fff",
    "MySQL":      "fill:#4479A1,color:#fff",
    "MongoDB":    "fill:#47A248,color:#fff",
    "Redis":      "fill:#DC382D,color:#fff",
    "SQLite":     "fill:#003B57,color:#fff",
    "Elasticsearch": "fill:#FEC514,color:#000",
    "Prisma ORM": "fill:#2D3748,color:#fff",
    "Cassandra":  "fill:#1287B1,color:#fff",
    "DynamoDB":   "fill:#FF9900,color:#000",
}

FRAMEWORK_ENTRY_LABELS = {
    "Express.js":      "Express.js Server",
    "Fastify":         "Fastify Server",
    "NestJS":          "NestJS App",
    "Koa.js":          "Koa.js Server",
    "FastAPI":         "FastAPI App",
    "Flask":           "Flask App",
    "Django":          "Django WSGI App",
    "aiohttp":         "aiohttp Server",
    "Gin":             "Gin HTTP Server",
    "Echo":            "Echo HTTP Server",
    "Fiber":           "Fiber HTTP Server",
    "Actix Web":       "Actix Web Server",
    "Axum":            "Axum HTTP Server",
    "Ruby on Rails":   "Rails App",
    "Laravel":         "Laravel App",
    "Spring Boot":     "Spring Boot App",
    "Next.js":         "Next.js App",
    "Nuxt.js":         "Nuxt.js App",
}


def build_mermaid_diagram(
    manifest_data: dict,
    framework_data: dict,
    scan_result: dict,
    import_graph: dict,
    content_data: dict | None = None,
) -> str:
    """
    Generate a Mermaid `flowchart TD` diagram from project analysis data.
    """
    root: pathlib.Path = scan_result["root"]
    files: list[pathlib.Path] = scan_result["files"]
    databases: list[str] = framework_data.get("databases", [])
    services: list[str] = framework_data.get("services", [])
    primary = framework_data.get("primary", {})
    fw_label: str = primary.get("label", "Application")
    # Merge platform from content_data into fw_type for mobile detection
    fw_type: str = (
        (content_data or {}).get("app_type", "")
        or primary.get("type", "unknown")
    )

    # ── Discover top-level architectural folders ───────────────────────────────
    top_dirs = _get_top_dirs(root, files)
    layers = _classify_layers(top_dirs)

    # ── Detect if this is a mobile / desktop app (non-HTTP) ───────────────────
    fw_type_lower = fw_type.lower()
    is_mobile = any(k in fw_type_lower for k in ("mobile", "flutter", "dart", "android", "ios"))
    is_desktop = any(k in fw_type_lower for k in ("desktop", "electron", "tauri"))

    # ── Build diagram nodes ────────────────────────────────────────────────────
    lines = ["flowchart TD"]
    node_id = _NodeCounter()

    if is_mobile:
        # Mobile: User → App → Sensors/DB
        user_id = node_id("USER")
        lines.append(f'    {user_id}([User])')
        entry_id = node_id("ENTRY")
        entry_file = _detect_entry_file(scan_result["entry_points"])
        app_label  = FRAMEWORK_ENTRY_LABELS.get(fw_label, f"{fw_label} App")
        entry_comment = f"\\n{entry_file}" if entry_file else ""
        lines.append(f'    {entry_id}["{app_label}{entry_comment}"]')
        lines.append(f"    {user_id} -->|launches| {entry_id}")
        prev_id = entry_id

        # Views layer
        if "views" in layers or "screens" in layers or "pages" in layers:
            vk = next(k for k in ("views", "screens", "pages") if k in layers)
            view_id = node_id("VIEW")
            lines.append(f'    {view_id}["{_folder_label(layers[vk])}"]')
            lines.append(f"    {prev_id} --> {view_id}")
            prev_id = view_id

        # Services layer
        if "services" in layers:
            svc_id = node_id("SVC")
            lines.append(f'    {svc_id}["{_folder_label(layers["services"])}"]')
            lines.append(f"    {prev_id} --> {svc_id}")
            prev_id = svc_id

        # DB layer
        if "database" in layers or "db" in layers:
            db_key = "database" if "database" in layers else "db"
            db_id = node_id("DB")
            lines.append(f'    {db_id}[("{_folder_label(layers[db_key])}")]')
            lines.append(f"    {prev_id} --> {db_id}")

        # Hardware sensor node
        if any("sensor" in f.name.lower() or "calibrat" in f.name.lower()
               for f in files):
            hw_id = node_id("HW")
            lines.append(f'    {hw_id}(["Device Hardware\\nIMU / Camera / GPS"])')
            lines.append(f"    {node_id.last('SVC') or prev_id} --> {hw_id}")

        lines.append("")
        lines.append(f"    style {user_id} fill:#6366f1,color:#fff,stroke:none")
        lines.append(f"    style {entry_id} fill:#0f172a,color:#fff,stroke:#6366f1,stroke-width:2px")

    else:
        # Web / API: standard Client → Server flow
        client_id = node_id("CLIENT")
        lines.append(f'    {client_id}([fa:fa-globe Client / Consumer])')

        server_label = FRAMEWORK_ENTRY_LABELS.get(fw_label, f"{fw_label} Server")
        entry_id = node_id("ENTRY")
        entry_file = _detect_entry_file(scan_result["entry_points"])
        entry_comment = f"\\n{entry_file}" if entry_file else ""
        lines.append(f'    {entry_id}["{server_label}{entry_comment}"]')
        lines.append(f"    {client_id} -->|HTTP Request| {entry_id}")

        prev_id = entry_id

        # Auth/Middleware layer (if present)
        if "middleware" in layers or "auth" in layers:
            mw_id = node_id("MW")
            mw_folder = layers.get("middleware") or layers.get("auth", "middleware/")
            lines.append(f'    {mw_id}{{"{_folder_label(mw_folder)}"}}')
            lines.append(f"    {prev_id} --> {mw_id}")
            prev_id = mw_id

        # API / Router layer
        if "api" in layers or "routes" in layers or "controllers" in layers:
            api_key = next(k for k in ("api", "routes", "controllers") if k in layers)
            api_id = node_id("API")
            api_folder = layers[api_key]
            lines.append(f'    {api_id}["{_folder_label(api_folder)}"]')
            lines.append(f"    {prev_id} --> {api_id}")
            prev_id = api_id

        # Service / Business logic layer
        if "services" in layers or "core" in layers or "domain" in layers:
            svc_key = next(k for k in ("services", "core", "domain") if k in layers)
            svc_id = node_id("SVC")
            svc_folder = layers[svc_key]
            lines.append(f'    {svc_id}["{_folder_label(svc_folder)}"]')
            lines.append(f"    {prev_id} --> {svc_id}")
            prev_id = svc_id

    # Worker layer (branch) — web apps only
    worker_id = None
    if not is_mobile and ("workers" in layers or "tasks" in layers or "jobs" in layers):
        wk_key = next(k for k in ("workers", "tasks", "jobs") if k in layers)
        worker_id = node_id("WKR")
        wk_folder = layers[wk_key]
        lines.append(f'    {worker_id}["{_folder_label(wk_folder)}"]')
        branch_from = node_id.last("API") or node_id.last("ENTRY") or prev_id
        lines.append(f"    {branch_from} -->|async| {worker_id}")

    # Data / Model layer — web apps only
    data_id = None
    if not is_mobile and ("models" in layers or "db" in layers or "repositories" in layers or "schemas" in layers):
        data_key = next(k for k in ("db", "repositories", "models", "schemas") if k in layers)
        data_id = node_id("DATA")
        data_folder = layers[data_key]
        lines.append(f'    {data_id}["{_folder_label(data_folder)}"]')
        lines.append(f"    {prev_id} --> {data_id}")
        if worker_id:
            lines.append(f"    {worker_id} --> {data_id}")
        prev_id = data_id

    # External databases — web apps only
    db_ids = []
    if not is_mobile:
        for db in databases[:3]:
            db_id = node_id("DB")
            db_ids.append(db_id)
            lines.append(f'    {db_id}[("{db}")]')
            anchor = data_id or prev_id
            lines.append(f"    {anchor} --> {db_id}")

    # External services — web apps only
    if not is_mobile:
        svc_queue_keywords = {"celery", "bullmq", "kafka", "rabbitmq", "redis"}
        queue_services = [s for s in services
                          if any(k in s.lower() for k in svc_queue_keywords)]
        for svc in queue_services[:2]:
            svc_id = node_id("EXT")
            lines.append(f'    {svc_id}(("{svc}"))')
            lines.append(f"    {prev_id} -->|publish| {svc_id}")

    # Response back to client (web only)
    if not is_mobile:
        lines.append(f"    {entry_id} -->|HTTP Response| {client_id}")

    # ── Style important nodes ──────────────────────────────────────────────────
    if not is_mobile:
        lines.append("")
        lines.append(f"    style {client_id} fill:#6366f1,color:#fff,stroke:none")
        lines.append(f"    style {entry_id} fill:#0f172a,color:#fff,stroke:#6366f1,stroke-width:2px")
        for db_label, db_id in zip(databases[:3], db_ids):
            style = DB_STYLES.get(db_label, "fill:#334155,color:#fff")
            lines.append(f"    style {db_id} {style},stroke:none")

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_top_dirs(root: pathlib.Path, files: list[pathlib.Path]) -> set[str]:
    """Collect the names of all top-level (and second-level) directories that contain files."""
    dirs: set[str] = set()
    for f in files:
        try:
            rel = f.relative_to(root)
            parts = rel.parts
            if len(parts) >= 2:
                dirs.add(parts[0])           # top-level
                dirs.add(parts[1])           # second-level
            elif len(parts) == 1:
                pass  # root-level files, no folder
        except ValueError:
            continue
    return dirs


def _classify_layers(dirs: set[str]) -> dict[str, str]:
    """Map canonical layer names to the matching folder name found in the project."""
    mapping: dict[str, str] = {}
    for d in dirs:
        d_lower = d.lower()
        for key in LAYER_FOLDERS:
            if key == d_lower and key not in mapping:
                mapping[key] = d
    return mapping


def _folder_label(folder_name: str) -> str:
    info = LAYER_FOLDERS.get(folder_name.lower(), ("", ""))
    label = info[0] if isinstance(info, tuple) else folder_name.title()
    return f"{label}\\n{folder_name}/"


def _detect_entry_file(entry_points: list[pathlib.Path]) -> str:
    if not entry_points:
        return ""
    return entry_points[0].name


class _NodeCounter:
    """Generates unique Mermaid node IDs and tracks the last ID per prefix."""
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._last: dict[str, str] = {}

    def __call__(self, prefix: str) -> str:
        n = self._counts.get(prefix, 0)
        self._counts[prefix] = n + 1
        node_id = f"{prefix}{n}" if n > 0 else prefix
        self._last[prefix] = node_id
        return node_id

    def last(self, prefix: str) -> Optional[str]:
        return self._last.get(prefix)
