"""
content_analyzer.py — Deep source content analyser for ZeroRot.

Reads actual source file content (comments, class/function/component names,
docstrings, metadata files) to extract a meaningful description and feature
list for the project — without any AI API.

Strategy:
  1. Read metadata.json / pubspec.yaml / README if they already exist
  2. Extract top-level comments / docstrings from entry-point files
  3. Parse component/class/function names and map them to feature phrases
     using a built-in semantic vocabulary
  4. Detect language-specific patterns (Flutter, React Native, etc.)
  5. Return: description, features[], app_type, platform
"""
import pathlib
import re
import json
from typing import Optional

from .utils import safe_read

# ── Semantic vocabulary: identifier fragment → readable feature phrase ─────────
# Keys are lowercase substrings matched against component/class/function names.
# Longer, more specific keys take priority.
SEMANTIC_MAP: list[tuple[str, str]] = [
    # Surveying / GIS / Total Station domain
    ("theodolite",        "Theodolite angle measurement and digital display"),
    ("totalstation",      "Total station integration for precise field measurements"),
    ("total_station",     "Total station integration for precise field measurements"),
    ("stakeout",          "Stakeout mode for on-site point placement and navigation"),
    ("traversesurvey",    "Traverse survey workflow for connected measurement chains"),
    ("traverse",          "Traverse computation for connected survey points"),
    ("radarplot",         "Radar polar plot for visualising angular measurements"),
    ("radar",             "Radar-style visualisation of sensor data"),
    ("tacheometry",       "Tacheometric calculation for distance and elevation"),
    ("triangulation",     "Triangulation engine for coordinate computation"),
    ("geosight",          "GeoSight total station data collection and visualisation"),
    ("surveyor",          "Surveyor workflow tools and measurement utilities"),
    ("surveylog",         "Survey log manager — stores, exports, and replays sessions"),
    ("benchmark",         "Benchmark reference point management"),
    ("elevation",         "Elevation and vertical angle computation"),
    ("azimuth",           "Azimuth bearing calculation and display"),
    ("bearing",           "Bearing computation between coordinates"),
    ("coordinate",        "Coordinate computation and transformation utilities"),
    ("gps",               "GPS / GNSS position integration"),
    ("gnss",              "GNSS receiver data parsing and display"),
    ("rtk",               "RTK correction stream processing"),
    ("contour",           "Contour map generation from point cloud data"),
    ("pointcloud",        "Point cloud capture and rendering"),
    ("landsurvey",        "Land survey data collection and processing"),
    ("cadastral",         "Cadastral boundary mapping and parcel management"),
    ("parcel",            "Parcel boundary definition and area calculation"),
    ("fieldwork",         "Field data collection and offline sync"),

    # Sensor / Hardware / Calibration
    ("calibration",       "Physical sensor calibration workflow"),
    ("sensorservice",     "Background sensor service for IMU / compass data"),
    ("sensor",            "Device sensor (IMU, accelerometer, gyroscope) integration"),
    ("imu",               "IMU inertial measurement unit data acquisition"),
    ("gyroscope",         "Gyroscope angular rate processing"),
    ("accelerometer",     "Accelerometer tilt and motion detection"),
    ("magnetometer",      "Magnetometer compass bearing correction"),
    ("compass",           "Digital compass heading display"),
    ("inclinometer",      "Inclinometer for slope and tilt measurement"),
    ("leveling",          "Electronic leveling and bubble display"),
    ("bubble",            "Electronic spirit bubble / level indicator"),
    ("prism",             "Reflector prism tracking and EDM distance measurement"),
    ("edm",               "Electronic distance measurement (EDM) module"),
    ("bluetooth",         "Bluetooth device pairing for external sensors"),
    ("serial",            "Serial port communication with total station hardware"),
    ("usb",               "USB device communication for data transfer"),
    ("ntrip",             "NTRIP correction data streaming for RTK"),

    # Camera / AR / Vision
    ("cameraoverlay",     "Augmented reality camera overlay for on-site guidance"),
    ("camera",            "Camera integration for photo documentation"),
    ("arview",            "Augmented reality view for field positioning"),
    ("overlay",           "Real-time measurement overlay on live camera feed"),
    ("qr",                "QR code scanning for point identification"),
    ("lidar",             "LiDAR depth scan capture and point cloud processing"),

    # Data / Storage / Export
    ("dbhelper",          "SQLite local database for offline data persistence"),
    ("database",          "Database layer for structured data storage and retrieval"),
    ("export",            "Data export to CSV / DXF / GeoJSON / Shapefile"),
    ("import",            "Data import from standard survey file formats"),
    ("dxf",               "DXF CAD file export for survey drawings"),
    ("shapefile",         "Shapefile export for GIS integration"),
    ("geojson",           "GeoJSON export for web mapping"),
    ("kml",               "KML export for Google Earth / Maps"),
    ("csv",               "CSV export for spreadsheet analysis"),
    ("sync",              "Cloud sync for field data backup and sharing"),
    ("cloud",             "Cloud integration for remote data storage"),

    # UI / Visualisation
    ("canvas",            "Interactive canvas rendering for measurement visualisation"),
    ("map",               "Interactive map view with survey data overlay"),
    ("chart",             "Chart / graph visualisation of measurement data"),
    ("dashboard",         "Dashboard with real-time measurement summary"),
    ("report",            "Report generation from collected survey data"),
    ("pdf",               "PDF report generation and sharing"),
    ("plot",              "Measurement data plotting and graphing"),
    ("viewer",            "Data viewer for reviewing collected measurements"),

    # Generic app patterns
    ("auth",              "User authentication and session management"),
    ("login",             "User login and credential management"),
    ("settings",          "Application settings and preferences"),
    ("profile",           "User profile management"),
    ("notification",      "Push notification support"),
    ("offline",           "Offline-first data collection with local caching"),
    ("sync",              "Data synchronisation between device and server"),
    ("api",               "REST API integration layer"),
    ("websocket",         "Real-time WebSocket data streaming"),
    ("worker",            "Background worker for processing tasks"),
    ("scheduler",         "Task scheduler for periodic operations"),
    ("payment",           "Payment processing integration"),
    ("search",            "Full-text search and filter functionality"),
    ("upload",            "File upload and media management"),
    ("download",          "File download and local caching"),
    ("permission",        "Device permission management (camera, location, storage)"),
    ("location",          "Device GPS location tracking and geofencing"),
    ("map",               "Interactive map integration"),
]

# Platform / app-type signals
PLATFORM_SIGNALS: dict[str, str] = {
    # File-based
    "pubspec.yaml":      "Flutter / Dart mobile app",
    "AndroidManifest.xml": "Android app",
    "Info.plist":        "iOS app",
    "CMakeLists.txt":    "C++ desktop / embedded app",
    "tauri.conf.json":   "Tauri desktop app",
    "electron.js":       "Electron desktop app",
    "main.electron.js":  "Electron desktop app",
    "capacitor.config":  "Capacitor cross-platform mobile app",
    "ionic.config.json": "Ionic mobile app",
    "expo.json":         "Expo / React Native mobile app",
    "app.json":          "React Native / Expo mobile app",
    # Extension-based
    ".dart":  "Flutter / Dart",
    ".swift": "Swift / iOS",
    ".kt":    "Kotlin / Android",
    ".java":  "Java / Android",
    ".xaml":  "XAML / .NET MAUI",
}

# Docstring / comment extractors per language
_COMMENT_PATTERNS: list[tuple[re.Pattern, int]] = [
    # Python / Dart / JS block comment
    (re.compile(r'/\*\*?\s*(.*?)\s*\*/', re.DOTALL), 1),
    # Python triple-quote
    (re.compile(r'"""(.*?)"""', re.DOTALL), 1),
    (re.compile(r"'''(.*?)'''", re.DOTALL), 1),
    # Single-line comment cluster (3+ consecutive lines)
    (re.compile(r'^(?:///|//|#)\s*(.+)$', re.MULTILINE), 1),
]


def analyze_content(
    scan_result: dict,
    manifest_data: dict,
    project_root: pathlib.Path,
) -> dict:
    """
    Deep-read source files to extract app description, features, and platform.

    Returns:
        {
            'description':  str,          # Richer description than manifest fallback
            'features':     list[str],    # Bullet-ready feature descriptions
            'app_type':     str,          # e.g. "Mobile App", "CLI Tool", "Web API"
            'platform':     str,          # e.g. "Flutter / Dart", "React", "Node.js"
            'app_name':     str,          # Best-guess display name
        }
    """
    files: list[pathlib.Path] = scan_result["files"]

    # ── 1. Read metadata / description files ──────────────────────────────────
    meta_desc = _read_metadata_files(project_root)

    # ── 2. Detect platform from file extensions + special files ───────────────
    platform, app_type = _detect_platform(project_root, files, manifest_data)

    # ── 3. Extract features from component / class / function names ───────────
    features = _extract_features(files, project_root)

    # ── 4. Extract inline doc comments from entry-point files ─────────────────
    inline_desc = _extract_inline_docs(scan_result.get("entry_points", []), files)

    # ── 5. Determine best description ─────────────────────────────────────────
    description = (
        meta_desc
        or manifest_data.get("description", "").strip()
        or inline_desc
        or _build_description_from_features(features, platform, manifest_data)
    )

    # ── 6. Best-guess app name ─────────────────────────────────────────────────
    app_name = _resolve_app_name(project_root, manifest_data)

    return {
        "description": description,
        "features":    features[:12],   # cap at 12 bullets
        "app_type":    app_type,
        "platform":    platform,
        "app_name":    app_name,
    }


# ── Metadata file readers ──────────────────────────────────────────────────────

def _read_metadata_files(root: pathlib.Path) -> str:
    """Read description from metadata.json, pubspec.yaml, package.json, etc."""

    # metadata.json (common in AI Studio / template projects)
    for fname in ("metadata.json", "app.json", "manifest.json"):
        p = root / fname
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                desc = (
                    data.get("description")
                    or data.get("short_description")
                    or data.get("summary")
                    or ""
                )
                if desc and len(desc) > 20:
                    return str(desc).strip()
            except Exception:
                pass

    # pubspec.yaml (Flutter)
    pubspec = root / "pubspec.yaml"
    if pubspec.exists():
        content = safe_read(pubspec) or ""
        m = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        if m:
            desc = m.group(1).strip()
            if len(desc) > 15:
                return desc

    # existing README.md first paragraph (if user already has one)
    for readme_name in ("README.md", "readme.md", "README.rst"):
        readme = root / readme_name
        if readme.exists():
            content = safe_read(readme) or ""
            # grab first non-heading, non-badge paragraph
            for line in content.splitlines():
                line = line.strip()
                if (line and not line.startswith("#") and not line.startswith("!")
                        and not line.startswith("[") and len(line) > 40):
                    return line

    return ""


# ── Platform detector ──────────────────────────────────────────────────────────

def _detect_platform(
    root: pathlib.Path,
    files: list[pathlib.Path],
    manifest_data: dict,
) -> tuple[str, str]:
    """Return (platform_label, app_type_label)."""

    # Check special files first
    for fname, label in PLATFORM_SIGNALS.items():
        if fname.startswith("."):
            # extension check
            if any(f.suffix == fname for f in files):
                return label, _app_type_from_label(label)
        else:
            if (root / fname).exists():
                return label, _app_type_from_label(label)

    # Check file extensions in scanned files
    exts = {f.suffix.lower() for f in files}
    if ".dart" in exts:
        return "Flutter / Dart", "Mobile App"
    if ".swift" in exts:
        return "Swift / iOS", "Mobile App"
    if ".kt" in exts:
        return "Kotlin / Android", "Mobile App"

    # Fallback to manifest lang
    lang = manifest_data.get("lang", "unknown")
    fw   = manifest_data.get("framework_label", "")
    label = fw or lang.title()
    return label, _infer_app_type(root, files, manifest_data)


def _app_type_from_label(label: str) -> str:
    label_lower = label.lower()
    if any(k in label_lower for k in ("mobile", "flutter", "ios", "android", "expo", "react native")):
        return "Mobile App"
    if any(k in label_lower for k in ("desktop", "electron", "tauri", "maui")):
        return "Desktop App"
    return "Application"


def _infer_app_type(root: pathlib.Path, files: list[pathlib.Path], manifest: dict) -> str:
    scripts = manifest.get("scripts", {})
    if any(k in scripts for k in ("dev", "start", "serve")):
        deps = {**manifest.get("dependencies", {}), **manifest.get("dev_dependencies", {})}
        dep_keys = {k.lower() for k in deps}
        if any(k in dep_keys for k in ("react", "vue", "svelte", "next", "nuxt", "angular")):
            return "Web Application"
        if any(k in dep_keys for k in ("express", "fastify", "koa", "hapi", "nestjs")):
            return "Web API / Backend Service"
    if manifest.get("lang") == "python":
        entry_names = {f.name for f in files}
        if "manage.py" in entry_names:
            return "Django Web Application"
        if any(n in entry_names for n in ("main.py", "app.py", "server.py")):
            return "Web API / Backend Service"
    if manifest.get("lang") == "go":
        return "Go Service"
    return "Application"


# ── Feature extractor ──────────────────────────────────────────────────────────

def _extract_features(files: list[pathlib.Path], root: pathlib.Path) -> list[str]:
    """
    Extract meaningful feature phrases by:
    1. Collecting all component / class / function identifier names
    2. Mapping fragments to the semantic vocabulary
    3. De-duplicating and sorting by specificity
    """
    identifiers: list[str] = []

    for f in files:
        content = safe_read(f)
        if not content:
            continue
        ext = f.suffix.lower()

        if ext in (".ts", ".tsx", ".js", ".jsx"):
            identifiers.extend(_extract_js_identifiers(content))
        elif ext == ".dart":
            identifiers.extend(_extract_dart_identifiers(content))
        elif ext == ".py":
            identifiers.extend(_extract_py_identifiers(content))
        elif ext in (".kt", ".java"):
            identifiers.extend(_extract_java_identifiers(content))
        elif ext == ".swift":
            identifiers.extend(_extract_swift_identifiers(content))

    # Also extract from file names themselves (very reliable signal)
    for f in files:
        identifiers.append(f.stem)

    return _map_to_features(identifiers)


def _map_to_features(identifiers: list[str]) -> list[str]:
    """Match identifier fragments to semantic vocabulary entries."""
    matched: dict[str, int] = {}   # feature_phrase → match_count

    for ident in identifiers:
        ident_lower = ident.lower().replace("_", "").replace("-", "")
        for keyword, phrase in SEMANTIC_MAP:
            kw_clean = keyword.replace("_", "").replace("-", "")
            if kw_clean in ident_lower:
                matched[phrase] = matched.get(phrase, 0) + 1

    # Sort by match frequency (most-evidenced features first), then alpha
    sorted_features = sorted(matched.keys(), key=lambda p: (-matched[p], p))
    return sorted_features


# ── Language-specific identifier extractors ───────────────────────────────────

_JS_COMPONENT_RE   = re.compile(r'\bfunction\s+([A-Z][A-Za-z0-9]+)|const\s+([A-Z][A-Za-z0-9]+)\s*[:=]|class\s+([A-Z][A-Za-z0-9]+)')
_JS_HOOK_RE        = re.compile(r'\buse([A-Z][A-Za-z0-9]+)\s*\(')
_JSX_COMPONENT_RE  = re.compile(r'<([A-Z][A-Za-z0-9]+)')

def _extract_js_identifiers(content: str) -> list[str]:
    names: list[str] = []
    for m in _JS_COMPONENT_RE.finditer(content):
        names.append(m.group(1) or m.group(2) or m.group(3) or "")
    for m in _JS_HOOK_RE.finditer(content):
        names.append(m.group(1))
    for m in _JSX_COMPONENT_RE.finditer(content):
        names.append(m.group(1))
    return [n for n in names if n]


_DART_CLASS_RE = re.compile(r'\bclass\s+([A-Z][A-Za-z0-9]+)')
_DART_FUNC_RE  = re.compile(r'\b([a-z][A-Za-z0-9]{4,})\s*\(')

def _extract_dart_identifiers(content: str) -> list[str]:
    names: list[str] = []
    for m in _DART_CLASS_RE.finditer(content):
        names.append(m.group(1))
    for m in _DART_FUNC_RE.finditer(content):
        names.append(m.group(1))
    return names


_PY_CLASS_RE = re.compile(r'^class\s+([A-Za-z][A-Za-z0-9_]+)', re.MULTILINE)
_PY_FUNC_RE  = re.compile(r'^def\s+([a-z][A-Za-z0-9_]{4,})', re.MULTILINE)

def _extract_py_identifiers(content: str) -> list[str]:
    names: list[str] = []
    for m in _PY_CLASS_RE.finditer(content):
        names.append(m.group(1))
    for m in _PY_FUNC_RE.finditer(content):
        names.append(m.group(1))
    return names


_JAVA_CLASS_RE = re.compile(r'\bclass\s+([A-Z][A-Za-z0-9]+)')

def _extract_java_identifiers(content: str) -> list[str]:
    return [m.group(1) for m in _JAVA_CLASS_RE.finditer(content)]


_SWIFT_CLASS_RE = re.compile(r'\b(?:class|struct|protocol|enum)\s+([A-Z][A-Za-z0-9]+)')

def _extract_swift_identifiers(content: str) -> list[str]:
    return [m.group(1) for m in _SWIFT_CLASS_RE.finditer(content)]


# ── Inline doc extractor ───────────────────────────────────────────────────────

def _extract_inline_docs(entry_points: list[pathlib.Path],
                          all_files: list[pathlib.Path]) -> str:
    """Read the first meaningful comment / docstring from entry-point files."""
    candidates = list(entry_points) + [
        f for f in all_files
        if f.name.lower() in ("main.dart", "app.dart", "main.py", "app.py",
                               "main.tsx", "app.tsx", "main.ts", "app.ts",
                               "index.js", "index.ts")
    ]

    for f in candidates[:5]:
        content = safe_read(f)
        if not content:
            continue

        # Block comment (/** ... */ or /* ... */)
        m = re.search(r'/\*+\s*([\s\S]+?)\s*\*/', content)
        if m:
            text = re.sub(r'\s*\*\s*', ' ', m.group(1)).strip()
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 30:
                return text[:300]

        # Triple-quoted Python docstring
        m = re.search(r'"""([\s\S]+?)"""', content)
        if m:
            text = m.group(1).strip().splitlines()[0].strip()
            if len(text) > 30:
                return text[:300]

        # Cluster of 3+ consecutive // or /// lines
        lines = content.splitlines()
        comment_block: list[str] = []
        for line in lines[:40]:
            stripped = line.strip()
            if stripped.startswith("///") or stripped.startswith("//"):
                comment_block.append(stripped.lstrip("/").strip())
            elif comment_block:
                break
        if len(comment_block) >= 2:
            text = " ".join(comment_block)
            if len(text) > 30:
                return text[:300]

    return ""


# ── Description builder ────────────────────────────────────────────────────────

def _build_description_from_features(
    features: list[str],
    platform: str,
    manifest_data: dict,
) -> str:
    """Build a meaningful description from detected features when nothing else is available."""
    project_name = manifest_data.get("name", "This project")
    name_clean = re.sub(r'[-_]', ' ', project_name).title()

    if not features:
        fw = manifest_data.get("framework_label", platform or "a modern stack")
        return (
            f"{name_clean} is built with {fw}. "
            "It provides a modular, maintainable codebase ready for production deployment."
        )

    # Use top 3 features to write a summary sentence
    top = features[:3]
    feature_text = "; ".join(top).rstrip(".")

    platform_str = f" built with {platform}" if platform and platform != "unknown" else ""
    return (
        f"{name_clean}{platform_str}. "
        f"Core capabilities include: {feature_text}. "
        f"The project contains {len(features)} distinct functional modules."
    )


def _resolve_app_name(root: pathlib.Path, manifest_data: dict) -> str:
    """Return the best display name for the app."""
    # Check pubspec.yaml name field
    pubspec = root / "pubspec.yaml"
    if pubspec.exists():
        content = safe_read(pubspec) or ""
        m = re.search(r'^name:\s*["\']?([A-Za-z0-9_\-]+)', content, re.MULTILINE)
        if m:
            return m.group(1).replace("_", " ").title()

    # metadata.json
    for fname in ("metadata.json", "app.json"):
        p = root / fname
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                name = data.get("name") or data.get("title") or data.get("app_name")
                if name:
                    return str(name)
            except Exception:
                pass

    return manifest_data.get("name") or root.name
