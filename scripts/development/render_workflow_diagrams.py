#!/usr/bin/env python3
# ruff: noqa: E501 - diagram prose remains intact so the SVG renderer controls wrapping.
"""Render the application workflow atlas as dependency-free SVG diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "flows" / "diagrams"

LANES = ("User & browser", "HTTP boundary", "Services & policy", "Durable state")
LANE_X = (205, 575, 945, 1315)
TOP = 178
ROW_GAP = 112
NODE_WIDTH = 278
NODE_HEIGHT = 70

COLORS = {
    "ink": "#132f3a",
    "muted": "#52666e",
    "line": "#167ba3",
    "panel": "#f7f9fa",
    "lane": "#e8f0f3",
    "action": "#277fa7",
    "decision": "#3dbb8b",
    "terminal": "#25afc1",
    "failure": "#d85852",
    "store": "#725ca8",
    "white": "#ffffff",
}


@dataclass(frozen=True)
class Node:
    key: str
    label: str
    lane: int
    row: int
    kind: str = "action"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""
    tone: str = "normal"


@dataclass(frozen=True)
class Diagram:
    slug: str
    title: str
    subtitle: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    steps: tuple[str, ...] = ()


def n(key: str, label: str, lane: int, row: int, kind: str = "action") -> Node:
    return Node(key, label, lane, row, kind)


def e(source: str, target: str, label: str = "", tone: str = "normal") -> Edge:
    return Edge(source, target, label, tone)


DIAGRAMS = (
    Diagram(
        "application-workflow-overview",
        "DJ Library Studio workflow map",
        "The shared path from a user action to validated state, durable results, and visible feedback.",
        (
            n("action", "Choose a workflow", 0, 0, "terminal"),
            n("feature", "Feature controller", 0, 2),
            n("request", "Create validated request", 1, 2),
            n("route", "Focused FastAPI router", 1, 4),
            n("service", "Owning application service", 2, 4),
            n("valid", "Command valid and safe?", 2, 2, "decision"),
            n("policy", "Domain or musical policy", 2, 6),
            n("repo", "Narrow persistence capability", 3, 6),
            n("store", "SQLite / managed files", 3, 8, "store"),
            n("result", "Render status or result", 0, 8, "terminal"),
            n("error", "Explain recovery action", 1, 0, "failure"),
        ),
        (
            e("action", "feature"),
            e("feature", "request"),
            e("request", "route"),
            e("route", "service"),
            e("service", "valid"),
            e("valid", "policy", "YES"),
            e("valid", "error", "NO", "failure"),
            e("policy", "repo"),
            e("repo", "store"),
            e("store", "result", "receipt / projection"),
            e("error", "feature", "retry or revise"),
        ),
        steps=(
            "The selected frontend feature converts the user action into explicit request state.",
            "The shared API client serializes the request and normalizes HTTP errors.",
            "A focused FastAPI router parses the contract and injects the owning service.",
            "The service validates workflow invariants before changing durable state.",
            "Domain policy computes musical, identity, or safety decisions without HTTP concerns.",
            "A narrow persistence capability commits SQLite rows or managed-file state.",
            "Projection publishers invalidate caches and rebuild consumer-facing read models.",
            "The browser receives a result or operation receipt and renders the next safe action.",
        ),
    ),
    Diagram(
        "startup-and-navigation",
        "Startup and navigation",
        "One atomic frontend revision is composed with backend services before navigation becomes ready.",
        (
            n("launch", "Launch application", 0, 0, "terminal"),
            n("factory", "create_app() factory", 1, 0),
            n("runtime", "Build runtime and services", 2, 1),
            n("recover", "Recover interrupted work", 3, 1, "store"),
            n("manifest", "Validate asset manifest", 2, 3, "decision"),
            n("shell", "Serve revision-safe shell", 1, 5),
            n("entry", "Load app.js and navigation", 0, 5),
            n("ready", "Navigation ready?", 0, 7, "decision"),
            n("page", "Load selected feature", 0, 9, "terminal"),
            n("recovery", "Show startup diagnostics", 1, 7, "failure"),
        ),
        (
            e("launch", "factory"),
            e("factory", "runtime"),
            e("runtime", "recover"),
            e("runtime", "manifest"),
            e("manifest", "shell", "VALID"),
            e("manifest", "recovery", "INVALID", "failure"),
            e("shell", "entry"),
            e("entry", "ready"),
            e("ready", "page", "YES"),
            e("ready", "recovery", "NO", "failure"),
            e("recovery", "entry", "reload current revision"),
        ),
        steps=(
            "The launcher starts Uvicorn with audioextender.web:create_app as an application factory.",
            "ApplicationPaths.from_project() resolves workspace, database, reports, backups, and frontend roots.",
            "ApplicationRuntime.create() constructs JobRepository, workers, registries, and process-local caches.",
            "create_app() installs structured error handlers, middleware, static mounts, and startup hooks.",
            "Import, library, Set Builder, reporting, and settings collaborators are built by owner-specific builders.",
            "_register_routers() attaches every focused router without moving business rules into application.py.",
            "Startup recovery marks interrupted jobs and background operations retryable instead of still running.",
            "FrontendAssetService validates one manifest revision, entrypoint, stylesheet, and recursive module graph.",
            "The server renders index.html with revisioned asset URLs and bootstrap diagnostics.",
            "frontend/app.js creates shared API, DOM, notification, descriptor, and playback services.",
            "createNavigationController() binds tabs and calls the selected feature loader.",
            "Navigation readiness hides recovery UI; a module failure preserves diagnostics and reload controls.",
        ),
    ),
    Diagram(
        "imports",
        "Import workflows",
        "Local audio, playlist matches, authorized URLs, and Creative Commons converge on catalog publication.",
        (
            n("source", "Choose import source", 0, 0, "terminal"),
            n("kind", "Local, playlist, URL, or CC?", 0, 2, "decision"),
            n("upload", "Upload or submit source", 1, 2),
            n("validate", "Validate format and authority", 2, 2, "decision"),
            n("resolve", "Resolve or download audio", 2, 4),
            n("convert", "Convert and inspect WAV", 2, 6),
            n("catalog", "Upsert catalog identity", 3, 6, "store"),
            n("publish", "Publish catalog projections", 3, 8, "store"),
            n("done", "Show imported tracks", 0, 8, "terminal"),
            n("failure", "Record actionable failure", 1, 4, "failure"),
        ),
        (
            e("source", "kind"),
            e("kind", "upload", "selected path"),
            e("upload", "validate"),
            e("validate", "resolve", "VALID"),
            e("validate", "failure", "REJECT", "failure"),
            e("resolve", "convert"),
            e("resolve", "failure", "NOT FOUND", "failure"),
            e("convert", "catalog"),
            e("catalog", "publish"),
            e("publish", "done"),
            e("failure", "upload", "retry / choose match"),
        ),
        steps=(
            "The Import workspace classifies local files, playlist CSVs, authorized URLs, or Creative Commons sources.",
            "LocalAudioImportService validates extensions, stages uploads, converts audio, and records batch lifecycle.",
            "PlaylistMatchService parses rows, normalizes metadata, and proposes local or authorized source matches.",
            "SourceMatchingService.match() inspects a bounded URL and returns provider metadata before import starts.",
            "ImportService.start() validates youtube or soundcloud authority and creates a durable operation identifier.",
            "CreativeCommonsImportService.start() validates reviewed matches and delegates work to its batch worker.",
            "BackgroundTaskRegistry persists pending, running, canceled, failed, or completed progress across restarts.",
            "The browser polls the family-specific status endpoint and renders stages, counts, and recovery actions.",
            "Downloaded audio is converted to managed WAV and inspected before it enters the catalog.",
            "Repository upsert combines normalized metadata, audio fingerprint evidence, playlist, and file paths.",
            "CatalogProjectionPublisher refreshes Music Files, DJ Library, and Set Builder read models.",
            "Actionable failures remain available through ImportIssueService for retry, correction, or deletion.",
        ),
    ),
    Diagram(
        "track-processing",
        "Track processing",
        "Jobs move through durable queue state, analysis, candidate selection, rendering, and publication.",
        (
            n("command", "Analyze, extend, or convert", 0, 0, "terminal"),
            n("create", "POST /api/jobs", 1, 0),
            n("queue", "Create durable job row", 3, 1, "store"),
            n("worker", "Schedule WebJobService worker", 2, 1),
            n("prepare", "Load, cache, and analyze", 2, 3),
            n("analysis", "Analysis only?", 2, 5, "decision"),
            n("select", "Rank and select candidates", 2, 7),
            n("render", "Render and export artifacts", 2, 9),
            n("publish", "Update job and catalog", 3, 9, "store"),
            n("result", "Show complete or attention state", 0, 9, "terminal"),
            n("cleanup", "Fail safely and clean up", 1, 6, "failure"),
        ),
        (
            e("command", "create"),
            e("create", "queue"),
            e("queue", "worker"),
            e("worker", "prepare"),
            e("prepare", "analysis"),
            e("analysis", "publish", "YES"),
            e("analysis", "select", "NO"),
            e("select", "render"),
            e("render", "publish"),
            e("publish", "result"),
            e("prepare", "cleanup", "ERROR", "failure"),
            e("select", "cleanup", "ERROR", "failure"),
            e("render", "cleanup", "ERROR", "failure"),
            e("cleanup", "queue", "failed receipt"),
        ),
        steps=(
            "The Process workspace builds a JobCreationCommand from uploads, mode, preset, and explicit overrides.",
            "JobWorkflowService rejects unsupported input before persistence, then creates the durable queue row.",
            "WebJobService.enqueue_many() schedules eligible work under the configured concurrency policy.",
            "DatabaseProgress records stage, percentage, logs, cancellation, and attention state in SQLite.",
            "AnalysisPreparationService loads AudioData, checks AnalysisCache, and optionally produces stem evidence.",
            "Analysis derives tempo, beat grid, key confidence, arrangement sections, style, energy, vocals, and timing.",
            "Analysis-only jobs build a FileResult without entering candidate selection or render stages.",
            "CandidateSelectionOrchestrator ranks intro/outro sections and records alternatives and fallback reasons.",
            "Manual-choice requirements pause in an attention state and resume through a new reprocess request.",
            "create_extended_edit() assembles repetitions, optimized boundaries, stem-aware joins, and cue structure.",
            "RenderExportTransaction and ExportService write WAVs, previews, auditions, cues, and artifact paths.",
            "TrackResultBuilder creates the immutable FileResult used by web, CLI, reports, and catalog publication.",
            "ProcessingFailureCleanup stops progress exactly once and prevents later stages from claiming success.",
        ),
    ),
    Diagram(
        "music-files-and-catalog",
        "Music Files and catalog",
        "Catalog reads and mutations remain fast while projection publication keeps every consumer current.",
        (
            n("browse", "Search, filter, or select tracks", 0, 0, "terminal"),
            n("catalog", "GET downloaded library page", 1, 0),
            n("projection", "Read paginated catalog projection", 3, 1, "store"),
            n("mutate", "Edit, delete, retag, or repair?", 0, 3, "decision"),
            n("route", "Send validated mutation", 1, 3),
            n("service", "Metadata / batch service", 2, 3),
            n("safe", "Mutation safe and consistent?", 2, 5, "decision"),
            n("files", "Synchronize WAV and sidecars", 3, 5, "store"),
            n("publish", "Invalidate and rebuild projections", 3, 7, "store"),
            n("refresh", "Refresh page with receipt", 0, 7, "terminal"),
            n("refuse", "Refuse and explain conflict", 1, 5, "failure"),
        ),
        (
            e("browse", "catalog"),
            e("catalog", "projection"),
            e("projection", "mutate", "render results"),
            e("mutate", "refresh", "NO"),
            e("mutate", "route", "YES"),
            e("route", "service"),
            e("service", "safe"),
            e("safe", "files", "YES"),
            e("safe", "refuse", "NO", "failure"),
            e("files", "publish"),
            e("publish", "refresh"),
            e("refuse", "refresh", "unchanged state"),
        ),
        steps=(
            "createRequestStateController() restores filters, debounces input, cancels old requests, and tracks generations.",
            "GET /api/downloaded-library asks DownloadedCatalogQueryService for one page plus current facets.",
            "The catalog projection returns stable track IDs, paths, analysis state, artwork, quality, genres, and playlists.",
            "The view rejects superseded responses, renders filter chips, and preserves selection across safe refreshes.",
            "Delivery routes stream audio, artwork, downloads, Finder reveal results, or selected-track ZIP archives.",
            "Analysis routes enqueue selected or filter-matched tracks through DownloadedTrackAnalysisQueue.",
            "Mutation routes validate delete, genre, metadata, repair, and retag commands before touching files.",
            "TrackMetadataMutationService applies one authoritative metadata rule set to SQLite, WAV tags, and sidecars.",
            "MetadataBatchService and BatchOperationRegistry expose resumable progress for bulk maintenance.",
            "RecordingFamilyService manages duplicate candidates, merge, keep-separate, link, and unlink decisions.",
            "LibraryMaintenanceService reconciles catalog/filesystem drift and refuses unsafe automatic repair.",
            "Every successful mutation invalidates caches, republishes projections, and returns a visible operation receipt.",
        ),
    ),
    Diagram(
        "dj-library",
        "DJ Library",
        "A current search projection becomes performance-ready browsing, compatibility, and selection.",
        (
            n("open", "Open or filter DJ Library", 0, 0, "terminal"),
            n("state", "Update request state", 0, 2),
            n("query", "GET /api/library/catalog", 1, 2),
            n("current", "Projection current?", 2, 2, "decision"),
            n("rebuild", "Rebuild search projection", 2, 4),
            n("page", "Page tracks and facets", 3, 4, "store"),
            n("profile", "Attach musical profile", 2, 6),
            n("stale", "Response still current?", 0, 6, "decision"),
            n("render", "Render library intelligence", 0, 8, "terminal"),
            n("discard", "Discard superseded response", 1, 6, "failure"),
        ),
        (
            e("open", "state"),
            e("state", "query"),
            e("query", "current"),
            e("current", "page", "YES"),
            e("current", "rebuild", "NO"),
            e("rebuild", "page"),
            e("page", "profile"),
            e("profile", "stale"),
            e("stale", "render", "YES"),
            e("stale", "discard", "NO", "failure"),
            e("discard", "state", "latest generation"),
        ),
        steps=(
            "createDjLibraryFeature() composes query state, filters, rendering, intelligence, and selected-track actions.",
            "A filter, search, sort, or page change advances the request generation and aborts an older fetch.",
            "GET /api/library/catalog compares projection source signatures before deciding whether to rebuild.",
            "CatalogProjectionBuilder combines completed job evidence with downloaded-track catalog identity.",
            "replace_library_search_index() persists the derived DJ Library search projection when sources changed.",
            "page_library_tracks() returns one result page and filter facets without loading the full library.",
            "musical_profile() supplies authoritative key, Camelot, energy, role, vocals, timing, confidence, and provenance.",
            "The request controller discards a response when a newer browser generation already exists.",
            "createDjLibraryView() groups and renders tracks while intelligence.js explains compatibility and recommendations.",
            "Selection actions reveal or play media, then hand chosen tracks to processing without duplicating mutation policy.",
        ),
    ),
    Diagram(
        "set-builder",
        "Set Builder",
        "A brief becomes a validated journey, a recording-safe plan, editable transitions, and a saved export.",
        (
            n("brief", "Describe or manually shape set", 0, 0, "terminal"),
            n("interpret", "Interpret intention and journey", 1, 0),
            n("review", "Direction acceptable?", 0, 2, "decision"),
            n("candidates", "Retrieve validated candidates", 2, 2),
            n("plan", "Plan and optimize order", 2, 4),
            n("valid", "Health and uniqueness valid?", 2, 6, "decision"),
            n("workspace", "Review plan workspace", 0, 6),
            n("edit", "Lock, reject, replace, or reorder", 0, 8),
            n("regenerate", "Regenerate around locked tracks", 2, 8),
            n("save", "Save plan and export", 1, 10, "terminal"),
            n("state", "Saved sets / planning state", 3, 10, "store"),
            n("fallback", "Explain fallback or repair", 1, 5, "failure"),
        ),
        (
            e("brief", "interpret"),
            e("interpret", "review"),
            e("review", "candidates", "YES"),
            e("review", "brief", "EDIT"),
            e("candidates", "plan"),
            e("plan", "valid"),
            e("valid", "workspace", "YES"),
            e("valid", "fallback", "NO", "failure"),
            e("fallback", "workspace", "safe draft"),
            e("workspace", "edit"),
            e("edit", "regenerate", "rerun"),
            e("regenerate", "valid"),
            e("edit", "save", "approve"),
            e("save", "state"),
        ),
        steps=(
            "The user selects Describe what I want or Build manually; both paths produce the same editable set brief.",
            "POST /interpret-intention converts natural language into requirements, preferences, limits, and identity terms.",
            "POST /plan-journey proposes editable sections with duration, energy, genres, character, and purpose.",
            "The user reviews and edits the interpretation and journey before any track-selection request is created.",
            "planning-request.js derives target count, section allocation, required/excluded tracks, locks, and base revision.",
            "Candidate retrieval applies availability, analysis, genre, BPM, key, vocal, timing, and recording-family rules.",
            "The candidate pool exposes relevance tiers and reasons while excluding unsafe or duplicate recording identities.",
            "AI-assisted planning receives only validated candidates; deterministic planning uses the same pool and rules.",
            "The asynchronous planning client polls the durable job record until completed, failed, or canceled.",
            "SetPlanValidator checks requested rules, recording uniqueness, duration, section allocation, and track availability.",
            "The workspace renders health, intention fulfillment, transitions, receipt provenance, and recording alternatives.",
            "Edits create undo/redo checkpoints; rejection, replacement, reordering, and transition changes update the draft.",
            "Regeneration sends locked_track_sections and base_plan_revision, then compares stayed, added, and removed tracks.",
            "SavedSetService stores the versioned plan; exports derive CSV, M3U8, cue, or Rekordbox output from that revision.",
        ),
    ),
    Diagram(
        "review-feedback-and-reporting",
        "Review, feedback, and reporting",
        "Human decisions become durable corrections, preference evidence, and refreshed projections.",
        (
            n("review", "Review candidate, track, or set", 0, 0, "terminal"),
            n("decision", "Keep, reject, rate, or correct?", 0, 2, "decision"),
            n("submit", "Submit feedback command", 1, 2),
            n("validate", "Validate identity and reason", 2, 2, "decision"),
            n("persist", "Persist feedback / verification", 3, 4, "store"),
            n("preference", "Update learned preference evidence", 2, 5),
            n("projection", "Refresh reports and projections", 3, 7, "store"),
            n("receipt", "Show saved state and next action", 0, 7, "terminal"),
            n("reject", "Preserve state; explain rejection", 1, 4, "failure"),
        ),
        (
            e("review", "decision"),
            e("decision", "submit", "chosen action"),
            e("submit", "validate"),
            e("validate", "persist", "VALID"),
            e("validate", "reject", "INVALID", "failure"),
            e("persist", "preference"),
            e("preference", "projection"),
            e("projection", "receipt"),
            e("reject", "receipt", "not saved"),
        ),
        steps=(
            "Candidate review loads ranked intro/outro alternatives, audition media, waveforms, cues, and score evidence.",
            "Keep, reject, custom transition, or reprocess actions include stable job and candidate identity.",
            "Job review routes validate candidate position/rank and delegate persistence to the review workflow owner.",
            "TrackFeedbackRequest stores rating and notes separately from authoritative BPM or key verification.",
            "KeyVerificationRequest and BpmVerificationRequest update reviewed analysis values with provenance.",
            "Set Builder feedback converts keep, reject, rating, move, replacement, and transition edits into preference events.",
            "DJPreferenceService stores local events and builds bounded, context-specific preference profiles.",
            "SetReviewRequest records intention fulfillment, cohesion, transitions, pacing, acceptance delta, and notes.",
            "SetReviewService persists the review and refreshes calibration summaries without rewriting historical plans.",
            "Reporting routes rebuild analytics, processing reports, audio indexes, and detailed job evidence as projections.",
            "The UI shows an explicit saved or rejected receipt so a click never leaves feedback durability ambiguous.",
        ),
    ),
    Diagram(
        "settings-and-operations",
        "Settings and operations",
        "Validated configuration, relocation, backup, cleanup, and diagnostics protect durable library state.",
        (
            n("choose", "Choose settings operation", 0, 0, "terminal"),
            n("operation", "Update, relocate, backup, cleanup?", 0, 2, "decision"),
            n("request", "Send explicit command", 1, 2),
            n("guard", "Confirmation and safety checks pass?", 2, 2, "decision"),
            n("execute", "Execute owning service", 2, 4),
            n("verify", "Verify result and integrity", 2, 6, "decision"),
            n("persist", "Persist settings / manifest / backup", 3, 6, "store"),
            n("finish", "Show operation receipt", 0, 8, "terminal"),
            n("refuse", "Stop with recovery guidance", 1, 4, "failure"),
            n("rollback", "Rollback or mark retryable", 1, 6, "failure"),
        ),
        (
            e("choose", "operation"),
            e("operation", "request"),
            e("request", "guard"),
            e("guard", "execute", "YES"),
            e("guard", "refuse", "NO", "failure"),
            e("execute", "verify"),
            e("verify", "persist", "PASS"),
            e("verify", "rollback", "FAIL", "failure"),
            e("persist", "finish"),
            e("refuse", "finish", "unchanged"),
            e("rollback", "finish", "safe state"),
        ),
        steps=(
            "The Settings feature loads effective WebSettings, defaults, library status, health, storage, and diagnostics.",
            "Updates validate WebSettings and persist only overrides through the system-state repository capability.",
            "Library health distinguishes configured, available, writable, cataloged, degraded, and recovery states.",
            "LibraryRelocationPlanner checks source/destination topology, capacity, conflicts, and relink prerequisites.",
            "LibraryFileTransferService copies into staging with resumable progress and cancellation checks.",
            "LibraryRelocationVerifier checks sizes or hashes before LibraryMetadataRelinker changes authoritative paths.",
            "LibraryRelocationCoordinator records a durable manifest and can roll back or mark interrupted work retryable.",
            "LibraryBackupService snapshots SQLite consistently and packages allowlisted managed state with SHA-256 hashes.",
            "Restore preview validates archive paths and contents, requires an exact confirmation, and creates a safety backup.",
            "Storage cleanup accepts only a named managed target; full cleanup requires its separate confirmation phrase.",
            "PerformanceDiagnostics records bounded timing/failure samples and cache hit rates without becoming durable state.",
            "Every operation returns LifecycleProjection or a receipt with status, capabilities, output, and recovery guidance.",
        ),
    ),
    Diagram(
        "data-and-persistence",
        "Data and persistence propagation",
        "A mutation is committed once, synchronized to managed files, and republished to every consumer.",
        (
            n("change", "Import, analysis, or correction", 0, 0, "terminal"),
            n("command", "Validated feature command", 1, 0),
            n("service", "Owning mutation service", 2, 1),
            n("atomic", "Atomic durable update succeeds?", 2, 3, "decision"),
            n("sqlite", "SQLite capability", 3, 3, "store"),
            n("files", "Managed WAV / sidecar state", 3, 5, "store"),
            n("publish", "CatalogProjectionPublisher", 2, 6),
            n("search", "DJ Library search projection", 3, 7, "store"),
            n("set", "Set Builder catalog JSON", 3, 9, "store"),
            n("visible", "Consumers load new generation", 0, 9, "terminal"),
            n("failure", "Rollback and report unchanged state", 1, 3, "failure"),
        ),
        (
            e("change", "command"),
            e("command", "service"),
            e("service", "atomic"),
            e("atomic", "sqlite", "YES"),
            e("atomic", "failure", "NO", "failure"),
            e("sqlite", "files"),
            e("files", "publish"),
            e("publish", "search"),
            e("publish", "set"),
            e("search", "visible"),
            e("set", "visible"),
            e("failure", "visible", "error receipt"),
        ),
        steps=(
            "The route parses an input model and calls a service that depends on the narrowest persistence protocol.",
            "JobRepository remains a compatibility facade; SQL implementations stay in focused jobs, catalog, and system mixins.",
            "RepositorySchemaInitializer applies ordered, idempotent migrations before normal reads or writes begin.",
            "The service performs the SQLite mutation atomically and never lets a route own transaction logic.",
            "Approved metadata or path changes synchronize managed WAV tags, sidecars, artwork, playlists, and file locations.",
            "CatalogProjectionPublisher invalidates in-memory catalog, facet, artwork, or waveform caches as appropriate.",
            "CatalogProjectionBuilder combines durable catalog rows with completed processing evidence.",
            "replace_library_search_index() publishes the paginated DJ Library projection.",
            "The bounded set_builder_catalog.json projection publishes planning-safe track evidence.",
            "Source signatures avoid unnecessary full rebuilds while guaranteeing changed corrections become visible.",
            "Operation receipts state what changed, where it was written, and whether it survives application restart.",
        ),
    ),
)


def node_center(node: Node) -> tuple[int, int]:
    return LANE_X[node.lane], TOP + node.row * ROW_GAP


def node_bounds(node: Node) -> tuple[float, float, float, float]:
    cx, cy = node_center(node)
    if node.kind == "decision":
        return cx - 108, cy - 52, cx + 108, cy + 52
    return cx - NODE_WIDTH / 2, cy - NODE_HEIGHT / 2, cx + NODE_WIDTH / 2, cy + NODE_HEIGHT / 2


def connection_points(source: Node, target: Node) -> tuple[float, float, float, float]:
    sx0, sy0, sx1, sy1 = node_bounds(source)
    tx0, ty0, tx1, ty1 = node_bounds(target)
    scx, scy = node_center(source)
    tcx, tcy = node_center(target)
    if abs(tcx - scx) >= abs(tcy - scy):
        return (sx1 if tcx > scx else sx0, scy, tx0 if tcx > scx else tx1, tcy)
    return (scx, sy1 if tcy > scy else sy0, tcx, ty0 if tcy > scy else ty1)


def edge_path(source: Node, target: Node) -> str:
    x1, y1, x2, y2 = connection_points(source, target)
    if source.lane != target.lane:
        midpoint = (x1 + x2) / 2
        return f"M {x1:.1f} {y1:.1f} H {midpoint:.1f} V {y2:.1f} H {x2:.1f}"
    offset = 30 if x1 <= LANE_X[source.lane] else -30
    return f"M {x1:.1f} {y1:.1f} H {x1 + offset:.1f} V {y2:.1f} H {x2:.1f}"


def render_text(label: str, cx: float, cy: float, *, dark: bool = False) -> str:
    lines = wrap(label, width=28, break_long_words=False) or [label]
    start = cy - (len(lines) - 1) * 10
    color = COLORS["ink"] if dark else COLORS["white"]
    spans = "".join(
        f'<tspan x="{cx:.1f}" y="{start + index * 21:.1f}">{escape(line)}</tspan>' for index, line in enumerate(lines)
    )
    return f'<text class="node-label" fill="{color}" text-anchor="middle">{spans}</text>'


def render_node(node: Node) -> str:
    cx, cy = node_center(node)
    title = f"<title>{escape(node.label)}</title>"
    if node.kind == "decision":
        points = f"{cx},{cy - 58} {cx + 116},{cy} {cx},{cy + 58} {cx - 116},{cy}"
        shape = f'<polygon points="{points}" fill="{COLORS["decision"]}" stroke="#278c68" stroke-width="2"/>'
    else:
        fill = COLORS.get(node.kind, COLORS["action"])
        radius = 35 if node.kind == "terminal" else 8
        shape = (
            f'<rect x="{cx - NODE_WIDTH / 2:.1f}" y="{cy - NODE_HEIGHT / 2:.1f}" '
            f'width="{NODE_WIDTH}" height="{NODE_HEIGHT}" rx="{radius}" fill="{fill}" '
            f'stroke="#185d78" stroke-width="2"/>'
        )
    return f'<g id="{escape(node.key)}">{title}{shape}{render_text(node.label, cx, cy + 1)}</g>'


def render_edge(edge: Edge, nodes: dict[str, Node]) -> str:
    source = nodes[edge.source]
    target = nodes[edge.target]
    x1, y1, x2, y2 = connection_points(source, target)
    color = COLORS["failure"] if edge.tone == "failure" else COLORS["line"]
    marker = "arrow-failure" if edge.tone == "failure" else "arrow"
    label = ""
    if edge.label:
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 7
        label = (
            f'<rect x="{lx - 52:.1f}" y="{ly - 13:.1f}" width="104" height="22" rx="11" fill="#ffffff"/>'
            f'<text class="edge-label" x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="middle">'
            f"{escape(edge.label)}</text>"
        )
    return (
        f'<g><path d="{edge_path(source, target)}" fill="none" stroke="{color}" stroke-width="2.5" '
        f'marker-end="url(#{marker})"/>{label}</g>'
    )


def render_step(step: str, index: int, top: int) -> str:
    column = index % 2
    row = index // 2
    x = 35 + column * 780
    y = top + row * 76
    lines = wrap(step, width=82, break_long_words=False) or [step]
    text_y = y + 26 - (len(lines) - 1) * 9
    spans = "".join(
        f'<tspan x="{x + 57}" y="{text_y + line_index * 18}">{escape(line)}</tspan>'
        for line_index, line in enumerate(lines)
    )
    return (
        f'<g class="step"><rect x="{x}" y="{y}" width="750" height="62" rx="10" '
        f'fill="#f7f9fa" stroke="{COLORS["lane"]}"/>'
        f'<circle cx="{x + 27}" cy="{y + 31}" r="17" fill="{COLORS["action"]}"/>'
        f'<text class="step-number" x="{x + 27}" y="{y + 36}" text-anchor="middle">{index + 1}</text>'
        f'<text class="step-text">{spans}</text></g>'
    )


def render(diagram: Diagram) -> str:
    max_row = max(node.row for node in diagram.nodes)
    flow_height = TOP + max_row * ROW_GAP + 110
    step_rows = (len(diagram.steps) + 1) // 2
    details_height = 105 + step_rows * 76 if diagram.steps else 0
    height = flow_height + details_height
    nodes = {node.key: node for node in diagram.nodes}
    lane_width = 340
    lane_panels = []
    lane_headers = []
    for index, label in enumerate(LANES):
        x = LANE_X[index] - lane_width / 2
        lane_panels.append(
            f'<rect x="{x:.1f}" y="135" width="{lane_width}" height="{flow_height - 160}" rx="18" '
            f'fill="{COLORS["panel"]}" stroke="{COLORS["lane"]}"/>'
        )
        lane_headers.append(
            f'<text class="lane-label" x="{LANE_X[index]}" y="122" text-anchor="middle">{escape(label)}</text>'
        )
    edges = "".join(render_edge(edge, nodes) for edge in diagram.edges)
    node_shapes = "".join(render_node(node) for node in diagram.nodes)
    detail_steps = "".join(render_step(step, index, flow_height + 70) for index, step in enumerate(diagram.steps))
    details = ""
    if diagram.steps:
        details = (
            f'<line x1="35" y1="{flow_height + 25}" x2="1565" y2="{flow_height + 25}" '
            f'stroke="{COLORS["lane"]}"/>'
            f'<text class="details-title" x="35" y="{flow_height + 55}">Detailed implementation steps</text>'
            f"{detail_steps}"
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}"
  viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(diagram.title)}</title>
  <desc id="desc">{escape(diagram.subtitle)}</desc>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{COLORS["line"]}"/>
    </marker>
    <marker id="arrow-failure" viewBox="0 0 10 10" refX="9" refY="5"
      markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="{COLORS["failure"]}"/>
    </marker>
    <style>
      .title {{ font: 700 28px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
      .subtitle {{ font: 400 15px system-ui, -apple-system, sans-serif; fill: {COLORS["muted"]}; }}
      .lane-label {{
        font: 700 14px system-ui, -apple-system, sans-serif;
        letter-spacing: 1.3px;
        fill: {COLORS["muted"]};
        text-transform: uppercase;
      }}
      .node-label {{ font: 700 15px system-ui, -apple-system, sans-serif; }}
      .edge-label {{
        font: 700 11px system-ui, -apple-system, sans-serif;
        fill: {COLORS["ink"]};
        letter-spacing: .4px;
      }}
      .details-title {{ font: 700 19px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
      .step-number {{ font: 700 13px system-ui, -apple-system, sans-serif; fill: {COLORS["white"]}; }}
      .step-text {{ font: 500 13px system-ui, -apple-system, sans-serif; fill: {COLORS["ink"]}; }}
    </style>
  </defs>
  <rect width="1600" height="{height}" fill="#ffffff"/>
  <text class="title" x="35" y="43">{escape(diagram.title)}</text>
  <text class="subtitle" x="35" y="72">{escape(diagram.subtitle)}</text>
  <line x1="35" y1="94" x2="1565" y2="94" stroke="{COLORS["lane"]}"/>
  {"".join(lane_panels)}
  {"".join(lane_headers)}
  {edges}
  {node_shapes}
  {details}
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
