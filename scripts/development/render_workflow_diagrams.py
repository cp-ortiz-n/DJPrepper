#!/usr/bin/env python3
"""Render compact, numbered workflow diagrams as dependency-free SVG files."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "flows" / "diagrams"

WIDTH = 1440
CARD_WIDTH = 300
CARD_HEIGHT = 122
CARD_GAP = 34
START_X = 52
TOP_ROW_Y = 185
BOTTOM_ROW_Y = 382

COLORS = {
    "ink": "#18323c",
    "muted": "#60747c",
    "line": "#1680a6",
    "panel": "#f4f8fa",
    "border": "#d7e4e9",
    "browser": "#147f9f",
    "http": "#4b6cb7",
    "service": "#258b72",
    "state": "#705aa8",
    "failure": "#c95955",
    "white": "#ffffff",
}


@dataclass(frozen=True)
class Call:
    """One primary call in execution order."""

    title: str
    owner: str
    symbol: str
    tone: str = "service"


@dataclass(frozen=True)
class Diagram:
    slug: str
    title: str
    subtitle: str
    calls: tuple[Call, ...]
    alternate_paths: tuple[str, ...] = ()


def call(title: str, owner: str, symbol: str, tone: str = "service") -> Call:
    return Call(title, owner, symbol, tone)


DIAGRAMS = (
    Diagram(
        "application-workflow-overview",
        "DJ Library Studio workflow map",
        "The common call path from a user action to durable state and a visible result.",
        (
            call("Choose an action", "Browser", "feature event", "browser"),
            call("Build request state", "Feature", "controller / view model", "browser"),
            call("Send API request", "HTTP client", "shared api client", "http"),
            call("Parse the contract", "Router", "focused FastAPI route", "http"),
            call("Run the workflow", "Service", "owning application service"),
            call("Apply policy and write", "Domain + data", "policy + repository", "state"),
            call("Publish read models", "Projection", "cache invalidation / publish", "state"),
            call("Render the result", "Feature", "receipt / next safe action", "browser"),
        ),
        (
            "Validation failure → return an actionable error without changing durable state.",
            "Long-running work → return an operation ID and poll until a terminal state.",
        ),
    ),
    Diagram(
        "startup-and-navigation",
        "Startup and navigation",
        "Backend composition and one frontend revision become a navigation-ready application.",
        (
            call("Start the server", "Launcher", "audioextender.web:create_app", "browser"),
            call("Resolve paths", "Composition", "ApplicationPaths.from_project", "service"),
            call("Create runtime", "Composition", "ApplicationRuntime.create", "service"),
            call("Build and register", "Application", "builders + _register_routers", "http"),
            call("Recover interrupted work", "Startup", "repository.recover_interrupted", "state"),
            call("Render one asset revision", "Assets", "FrontendAssetService", "http"),
            call("Compose the frontend", "Browser", "frontend/app.js", "browser"),
            call("Load the selected page", "Navigation", "navigation-controller.js", "browser"),
        ),
        (
            "Asset-linking failure → keep the recovery banner visible with copyable diagnostics.",
            "Warm-cache restart → the manifest revisions the full module graph atomically.",
        ),
    ),
    Diagram(
        "imports",
        "Import workflows",
        "Every source path converges on a managed WAV, a catalog row, and refreshed projections.",
        (
            call("Choose a source", "Import UI", "local / CSV / URL / CC", "browser"),
            call("Validate and stage", "Route + service", "source-specific start()", "http"),
            call("Create operation state", "Lifecycle", "registry / batch ID", "state"),
            call("Resolve and convert", "Import worker", "download / inspect / WAV", "service"),
            call("Upsert catalog identity", "Persistence", "upsert_downloaded_track", "state"),
            call("Publish projections", "Library", "CatalogProjectionPublisher", "state"),
            call("Poll and show outcome", "Import UI", "status / retry / cancel", "browser"),
        ),
        (
            "Unsupported or unauthorized source → stop before download and preserve the user input.",
            "Item failure → record an import issue that can be retried or dismissed explicitly.",
        ),
    ),
    Diagram(
        "track-processing",
        "Track processing",
        "A durable job moves through analysis, optional edit creation, export, and publication.",
        (
            call("Submit processing command", "Process UI", "POST /api/jobs", "browser"),
            call("Validate and persist job", "Workflow", "JobWorkflowService.create", "http"),
            call("Schedule worker", "Queue", "WebJobService.enqueue_many", "service"),
            call("Load and analyze", "Analysis", "AnalysisPreparationService.prepare", "service"),
            call("Select edit candidates", "Selection", "CandidateSelectionOrchestrator", "service"),
            call("Render and export", "Audio", "RenderExportTransaction", "service"),
            call("Publish result", "Queue + catalog", "FileResult + projections", "state"),
            call("Show queue state", "Process UI", "poll active / attention / history", "browser"),
        ),
        (
            "Analysis-only job → skip candidate selection and rendering, then publish analysis.",
            "Stage failure → run exactly-once cleanup and persist a failed receipt.",
        ),
    ),
    Diagram(
        "music-files-and-catalog",
        "Music Files and catalog",
        "Fast catalog reads and authoritative mutations stay synchronized with managed files.",
        (
            call("Change query state", "Music Files UI", "search / filters / page", "browser"),
            call("Request one page", "Catalog route", "GET /api/downloaded-library", "http"),
            call("Read projection", "Query service", "DownloadedCatalogQueryService", "state"),
            call("Choose a mutation", "Music Files UI", "edit / delete / repair", "browser"),
            call("Apply mutation rules", "Mutation service", "TrackMetadataMutationService", "service"),
            call("Sync managed files", "Library", "WAV tags / sidecars / paths", "state"),
            call("Republish consumers", "Projection", "invalidate + rebuild", "state"),
            call("Refresh with receipt", "Music Files UI", "latest generation", "browser"),
        ),
        (
            "Read-only browsing → stop after the projection response.",
            "Unsafe conflict → refuse the mutation and keep catalog and files unchanged.",
        ),
    ),
    Diagram(
        "dj-library",
        "DJ Library",
        "A generation-safe query becomes performance-ready browsing and compatibility insight.",
        (
            call("Update query generation", "DJ Library UI", "request-state-controller", "browser"),
            call("Request catalog page", "Library route", "GET /api/library/catalog", "http"),
            call("Check source signature", "Projection", "is search index current?", "service"),
            call("Rebuild when stale", "Projection", "CatalogProjectionBuilder", "state"),
            call("Page tracks and facets", "Persistence", "page_library_tracks", "state"),
            call("Attach musical profile", "Policy", "musical_profile()", "service"),
            call("Reject stale response", "DJ Library UI", "generation check", "browser"),
            call("Render library insight", "DJ Library UI", "view + intelligence", "browser"),
        ),
        (
            "Current signature → skip rebuild and page the stored search projection directly.",
            "Superseded request → discard its response without replacing the newer screen state.",
        ),
    ),
    Diagram(
        "set-builder",
        "Set Builder",
        "An editable brief becomes a validated plan, a revisioned workspace, and an export.",
        (
            call("Create the brief", "Set Builder UI", "describe or build manually", "browser"),
            call("Interpret the journey", "Planning routes", "prepare-brief / plan-journey", "http"),
            call("Review direction", "Set Builder UI", "edit sections and constraints", "browser"),
            call("Retrieve candidates", "Planning service", "SetCandidateRetriever", "service"),
            call("Generate proposals", "Planner", "AI or deterministic planner", "service"),
            call("Validate and compare", "Policy", "SetPlanValidator + comparator", "service"),
            call("Edit or regenerate", "Workspace", "lock / replace / reorder", "browser"),
            call("Save and export", "Saved sets", "SavedSetService + preflight", "state"),
        ),
        (
            "Invalid or weaker AI proposal → select the validated deterministic baseline.",
            "Regeneration → preserve locked tracks and restore the prior revision on failure.",
        ),
    ),
    Diagram(
        "review-feedback-and-reporting",
        "Review, feedback, and reporting",
        "A human decision becomes durable evidence, bounded preference input, and a visible receipt.",
        (
            call("Open review context", "Review UI", "candidate / track / set", "browser"),
            call("Choose action and reason", "Review UI", "keep / reject / rate / correct", "browser"),
            call("Validate identity", "Review route", "stable job / track / revision ID", "http"),
            call("Persist evidence", "Review service", "feedback / verification / review", "state"),
            call("Update bounded signals", "Preference", "DJPreferenceService", "service"),
            call("Refresh projections", "Reporting", "reports / analytics / catalog", "state"),
            call("Show saved receipt", "Review UI", "saved state + next action", "browser"),
        ),
        (
            "Rating or preference event → never rewrites raw analyzer evidence or bypasses hard rules.",
            "Invalid identity or reason → reject the command and show that nothing was saved.",
        ),
    ),
    Diagram(
        "settings-and-operations",
        "Settings and operations",
        "Explicit commands and verification protect settings, storage, relocation, and backups.",
        (
            call("Choose an operation", "Settings UI", "update / move / backup / clean", "browser"),
            call("Send explicit command", "Settings route", "validated request model", "http"),
            call("Run safety preflight", "Operation service", "confirmation + capability checks", "service"),
            call("Execute operation", "Owner", "update / transfer / archive", "service"),
            call("Verify integrity", "Verifier", "size / hash / health", "service"),
            call("Commit durable state", "Persistence", "settings / manifest / backup", "state"),
            call("Show operation receipt", "Settings UI", "status + recovery action", "browser"),
        ),
        (
            "Preflight refusal → leave durable state unchanged and explain the required correction.",
            "Verification failure → roll back when possible or mark the operation retryable.",
        ),
    ),
    Diagram(
        "data-and-persistence",
        "Data and persistence propagation",
        "One authoritative mutation is synchronized and republished to every read model.",
        (
            call("Parse the command", "Feature route", "validated request model", "http"),
            call("Own the transaction", "Mutation service", "workflow invariant checks", "service"),
            call("Call narrow capability", "Persistence", "repository protocol", "state"),
            call("Commit SQLite state", "Persistence", "atomic catalog / job update", "state"),
            call("Sync managed files", "Library", "WAV / sidecar / artwork", "state"),
            call("Invalidate caches", "Projection", "affected read models only", "service"),
            call("Publish projections", "Projection", "DJ Library + Set Builder", "state"),
            call("Load new generation", "Consumers", "Music Files / DJ Library / Set", "browser"),
        ),
        (
            "Atomic update failure → roll back and report unchanged state.",
            "Unchanged source signature → retain the current projection instead of rebuilding it.",
        ),
    ),
)


def card_position(index: int) -> tuple[int, int]:
    """Lay calls out as a two-row snake so arrows never cross."""
    if index < 4:
        return START_X + index * (CARD_WIDTH + CARD_GAP), TOP_ROW_Y
    return START_X + (7 - index) * (CARD_WIDTH + CARD_GAP), BOTTOM_ROW_Y


def text_lines(text: str, width: int) -> list[str]:
    return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [text]


def render_lines(lines: list[str], x: float, first_y: float, css_class: str, gap: int) -> str:
    spans = "".join(
        f'<tspan x="{x:.1f}" y="{first_y + index * gap:.1f}">{escape(line)}</tspan>' for index, line in enumerate(lines)
    )
    return f'<text class="{css_class}" text-anchor="middle">{spans}</text>'


def render_call(item: Call, index: int) -> str:
    x, y = card_position(index)
    center_x = x + CARD_WIDTH / 2
    fill = COLORS[item.tone]
    title_lines = text_lines(item.title, 29)
    symbol_lines = text_lines(item.symbol, 38)
    title_y = y + 54 - (len(title_lines) - 1) * 10
    symbol_y = y + 91 - (len(symbol_lines) - 1) * 8
    return f'''<g class="call" id="call-{index + 1}">
  <text class="call-number" x="{x:.1f}" y="{y - 13:.1f}">({index + 1})</text>
  <rect x="{x}" y="{y}" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="16"
    fill="{COLORS["white"]}" stroke="{COLORS["border"]}" stroke-width="2"/>
  <rect x="{x + 15}" y="{y + 14}" width="{min(150, 26 + len(item.owner) * 7)}" height="25" rx="12.5"
    fill="{fill}"/>
  <text class="owner" x="{x + 28}" y="{y + 31}">{escape(item.owner)}</text>
  {render_lines(title_lines, center_x, title_y, "call-title", 21)}
  {render_lines(symbol_lines, center_x, symbol_y, "symbol", 17)}
</g>'''


def arrow_path(source_index: int, target_index: int) -> str:
    sx, sy = card_position(source_index)
    tx, ty = card_position(target_index)
    if sy == ty:
        if tx > sx:
            return f"M {sx + CARD_WIDTH} {sy + CARD_HEIGHT / 2} H {tx - 8}"
        return f"M {sx} {sy + CARD_HEIGHT / 2} H {tx + CARD_WIDTH + 8}"
    right_x = sx + CARD_WIDTH + CARD_GAP / 2
    return f"M {sx + CARD_WIDTH} {sy + CARD_HEIGHT / 2} H {right_x} V {ty + CARD_HEIGHT / 2} H {tx + CARD_WIDTH + 8}"


def render_alternate_paths(paths: tuple[str, ...], top: int) -> str:
    if not paths:
        return ""
    cards = []
    card_width = 655
    for index, path in enumerate(paths):
        x = 52 + index * 681
        lines = text_lines(path, 76)
        spans = "".join(
            f'<tspan x="{x + 48}" y="{top + 48 + line_index * 18}">{escape(line)}</tspan>'
            for line_index, line in enumerate(lines)
        )
        cards.append(
            f'<g class="alternate"><rect x="{x}" y="{top + 18}" width="{card_width}" height="72" rx="14" '
            f'fill="#fff8f7" stroke="#eed1cf"/><circle cx="{x + 25}" cy="{top + 54}" r="8" '
            f'fill="{COLORS["failure"]}"/><text class="alternate-text">{spans}</text></g>'
        )
    return f'<text class="alternate-title" x="52" y="{top}">ALTERNATE PATHS</text>' + "".join(cards)


def render(diagram: Diagram) -> str:
    if not 6 <= len(diagram.calls) <= 8:
        raise ValueError(f"{diagram.slug} must contain 6–8 primary calls")
    alternate_top = 565
    height = 700 if diagram.alternate_paths else 585
    calls = "".join(render_call(item, index) for index, item in enumerate(diagram.calls))
    arrows = "".join(
        f'<path class="arrow" d="{arrow_path(index, index + 1)}" marker-end="url(#arrow)"/>'
        for index in range(len(diagram.calls) - 1)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}"
  viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(diagram.title)}</title>
  <desc id="desc">{escape(diagram.subtitle)} Calls are numbered in execution order.</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{COLORS["line"]}"/>
    </marker>
    <style>
      .title {{ font: 750 30px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
      .subtitle {{ font: 400 15px system-ui, -apple-system, sans-serif; fill: {COLORS["muted"]}; }}
      .order-note {{
        font: 650 12px system-ui, -apple-system, sans-serif;
        fill: {COLORS["line"]};
        letter-spacing: .7px;
      }}
      .call-number {{ font: 700 14px system-ui, -apple-system, sans-serif; fill: {COLORS["line"]}; }}
      .owner {{ font: 700 11px system-ui, -apple-system, sans-serif; fill: {COLORS["white"]}; letter-spacing: .25px; }}
      .call-title {{ font: 720 17px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
      .symbol {{ font: 500 12px ui-monospace, SFMono-Regular, Menlo, monospace; fill: {COLORS["muted"]}; }}
      .arrow {{
        fill: none;
        stroke: {COLORS["line"]};
        stroke-width: 2.5;
        stroke-linecap: round;
        stroke-linejoin: round;
      }}
      .alternate-title {{
        font: 750 12px system-ui, -apple-system, sans-serif;
        fill: {COLORS["muted"]};
        letter-spacing: 1.3px;
      }}
      .alternate-text {{ font: 500 13px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
    </style>
  </defs>
  <rect width="{WIDTH}" height="{height}" fill="{COLORS["white"]}"/>
  <rect x="28" y="25" width="1384" height="510" rx="24" fill="{COLORS["panel"]}"/>
  <text class="title" x="52" y="67">{escape(diagram.title)}</text>
  <text class="subtitle" x="52" y="95">{escape(diagram.subtitle)}</text>
  <text class="order-note" x="52" y="132">PRIMARY CALL ORDER</text>
  {arrows}
  {calls}
  {render_alternate_paths(diagram.alternate_paths, alternate_top)}
</svg>
'''


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for diagram in DIAGRAMS:
        path = OUTPUT_DIR / f"{diagram.slug}.svg"
        path.write_text(render(diagram), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
