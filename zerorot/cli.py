"""
cli.py — ZeroRot command-line interface.

Entry point registered via pyproject.toml as `zerorot`.
Uses Click for argument parsing and Rich for beautiful terminal output.
"""
import os
import pathlib
import sys
import time

# ── Windows UTF-8 fix (must be before any output) ─────────────────────────────
# Set env var so child processes also get UTF-8; reconfigure stdout safely.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        # Only reconfigure if the stream supports it (not already replaced)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from . import __version__
from .scanner import scan_directory, select_core_files
from .analyzer import analyze_manifest
from .framework_detector import detect_framework
from .env_extractor import extract_env_vars
from .import_mapper import map_imports
from .diagram_builder import build_mermaid_diagram
from .quickstart_builder import build_quickstart
from .readme_builder import build_readme
from .content_analyzer import analyze_content

# Rich console — force_terminal so it renders in cmd.exe / PowerShell
console = Console(highlight=False)

BANNER = """[bold #6366f1]
  ______              ____        __
 |___  /             |  _ \\      / _|
    / / ___ _ __ ___ | |_) | ___| |_
   / / / _ \\ '__/ _ \\|  _ < / _ \\  _|
  / /_|  __/ | | (_) | |_) |  __/ |
 /_____\\___|_|  \\___/|____/ \\___|_|
[/bold #6366f1]
[dim]  Automated README generation · pure static analysis · no AI API[/dim]
"""


# ── CLI entry point ────────────────────────────────────────────────────────────

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output", "-o", default="README.md", show_default=True,
    help="Output filename for the generated README.",
)
@click.option(
    "--max-files", "-m", default=15, show_default=True,
    help="Maximum number of source files to include in analysis.",
)
@click.option(
    "--max-file-size", default=200, show_default=True,
    help="Maximum file size in KB to read.",
)
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Overwrite existing README without prompting.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Preview the generated README without writing to disk.",
)
@click.version_option(__version__, "--version", "-v", prog_name="zerorot")
def main(path: str, output: str, max_files: int, max_file_size: int,
         force: bool, dry_run: bool) -> None:
    """
    \b
    ZeroRot — Generate a production-ready README.md via static code analysis.

    \b
    PATH defaults to the current directory (.).

    \b
    Examples:
      python -m zerorot .
      python -m zerorot C:\\path\\to\\project
      python -m zerorot C:\\path\\to\\project --output DOCS.md --force
      python -m zerorot . --dry-run
    """
    console.print(BANNER)

    project_path = pathlib.Path(path).resolve()
    output_path = project_path / output

    # ── Guard: output already exists ──────────────────────────────────────────
    if output_path.exists() and not force and not dry_run:
        console.print(
            f"\n[yellow]WARNING[/yellow]  [bold]{output}[/bold] already exists.\n"
            f"         Use [bold]--force[/bold] to overwrite, or [bold]--dry-run[/bold] to preview."
        )
        if not click.confirm("   Overwrite it?", default=False):
            console.print("[dim]Aborted.[/dim]")
            sys.exit(0)

    console.print(f"[bold cyan]Analysing:[/bold cyan] {project_path}\n")

    start = time.perf_counter()
    error: Exception | None = None

    with Progress(
        SpinnerColumn(spinner_name="dots", style="bold cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=28, style="cyan", complete_style="green"),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning directory...", total=7)

        try:
            # 1 — Scan
            progress.update(task, description="Scanning directory tree...")
            scan_result = scan_directory(str(project_path), max_file_size_kb=max_file_size)
            progress.advance(task)

            # 2 — Select core files
            progress.update(task, description="Selecting core source files...")
            core_files = select_core_files(scan_result, max_files=max_files)
            progress.advance(task)

            # 3 — Manifest
            progress.update(task, description="Parsing dependency manifest...")
            manifest_data = analyze_manifest(project_path)
            progress.advance(task)

            # 4 — Framework
            progress.update(task, description="Detecting framework & tech stack...")
            framework_data = detect_framework(manifest_data, scan_result["files"])
            progress.advance(task)

            # 5 — Env vars
            progress.update(task, description="Extracting environment variables...")
            env_vars = extract_env_vars(scan_result["files"], project_path)
            progress.advance(task)

            # 6 — Import graph + Mermaid
            progress.update(task, description="Mapping module graph...")
            import_graph = map_imports(core_files, project_path)
            mermaid_diagram = build_mermaid_diagram(
                manifest_data, framework_data, scan_result, import_graph
            )
            progress.advance(task)

            # 7 — Deep content analysis + Render README
            progress.update(task, description="Reading source content & features...")
            content_data     = analyze_content(scan_result, manifest_data, project_path)
            quickstart_steps = build_quickstart(manifest_data, framework_data, scan_result)
            mermaid_diagram  = build_mermaid_diagram(
                manifest_data, framework_data, scan_result, import_graph, content_data
            )
            readme_content   = build_readme(
                manifest_data=manifest_data,
                framework_data=framework_data,
                content_data=content_data,
                env_vars=env_vars,
                quickstart_steps=quickstart_steps,
                scan_result=scan_result,
                import_graph=import_graph,
                mermaid_diagram=mermaid_diagram,
            )
            progress.advance(task)

        except Exception as exc:
            error = exc

    elapsed = time.perf_counter() - start

    # ── Handle any pipeline error ──────────────────────────────────────────────
    if error is not None:
        console.print(f"\n[bold red]ERROR[/bold red]  Analysis failed: {error}")
        console.print("[dim]Run with PYTHONUTF8=1 python -m zerorot . if you see encoding errors.[/dim]")
        import traceback
        console.print("[dim]" + traceback.format_exc() + "[/dim]")
        sys.exit(1)

    # ── Print summary table ────────────────────────────────────────────────────
    _print_summary(
        scan_result=scan_result,
        core_files=core_files,
        manifest_data=manifest_data,
        framework_data=framework_data,
        content_data=content_data,
        env_vars=env_vars,
        quickstart_steps=quickstart_steps,
        elapsed=elapsed,
    )

    # ── Dry run: preview only ──────────────────────────────────────────────────
    if dry_run:
        console.print(Panel(
            readme_content[:3000] + (
                "\n\n[dim]... (truncated — full content will be written to disk)[/dim]"
                if len(readme_content) > 3000 else ""
            ),
            title="[bold]README Preview (dry run — nothing written)[/bold]",
            border_style="cyan",
        ))
        console.print("\n[yellow]Dry run complete — no files written.[/yellow]")
        return

    # ── Write output ───────────────────────────────────────────────────────────
    output_path.write_text(readme_content, encoding="utf-8", newline="\n")

    console.print(Panel(
        f"[bold green]SUCCESS[/bold green]  {output} written to:\n"
        f"  {output_path}\n\n"
        f"  [dim]{len(readme_content):,} chars  |  "
        f"{len(readme_content.splitlines())} lines  |  "
        f"{elapsed:.2f}s[/dim]",
        border_style="green",
        padding=(1, 2),
    ))


# ── Summary helper ─────────────────────────────────────────────────────────────

def _print_summary(scan_result, core_files, manifest_data,
                   framework_data, content_data, env_vars, quickstart_steps, elapsed):
    table = Table(
        title="[bold]Analysis Summary[/bold]",
        border_style="dim",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Category", style="dim", width=22)
    table.add_column("Detected", style="bold white")

    fw_label  = framework_data.get("primary", {}).get("label", "unknown")
    tech_str  = ", ".join(framework_data.get("tech_stack", [])[:4]) or "unknown"
    dbs       = ", ".join(framework_data.get("databases", [])) or "none"
    manifest  = manifest_data.get("manifest_file") or "none found"
    platform  = content_data.get("platform", "") or "—"
    features  = content_data.get("features", [])

    table.add_row("Project name",      content_data.get("app_name") or manifest_data.get("name") or scan_result["root"].name)
    table.add_row("App type",          content_data.get("app_type", "Application"))
    table.add_row("Platform",          platform)
    table.add_row("Language",          manifest_data.get("lang", "unknown"))
    table.add_row("Package manager",   manifest_data.get("package_manager", "unknown"))
    table.add_row("Manifest file",     manifest)
    table.add_row("Framework",         fw_label)
    table.add_row("Tech stack",        tech_str)
    table.add_row("Databases",         dbs)
    table.add_row("Features detected", str(len(features)))
    table.add_row("Files scanned",     str(len(scan_result["files"])))
    table.add_row("Files analysed",    str(len(core_files)))
    table.add_row("Env variables",     str(len(env_vars)))
    table.add_row("Quickstart steps",  str(len(quickstart_steps)))
    table.add_row("Time",              f"{elapsed:.2f}s")

    console.print()
    console.print(table)
    console.print()


# ── Allow `python -m zerorot.cli` ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
