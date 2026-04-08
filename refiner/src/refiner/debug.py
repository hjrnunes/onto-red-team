import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_call_counter = 0
_debug_dir: Path | None = None


def configure(debug_dir: Path | None) -> None:
    global _debug_dir, _call_counter
    _debug_dir = debug_dir
    _call_counter = 0
    if _debug_dir:
        _debug_dir.mkdir(parents=True, exist_ok=True)


def log_call(
    stage: str,
    messages: list[dict],
    response,
    *,
    context: dict | None = None,
) -> None:
    global _call_counter
    _call_counter += 1

    # Build slug from context (reused for JSON filename and span name)
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    # Extract response data
    if hasattr(response, "model_dump"):
        response_data = response.model_dump()
    elif isinstance(response, list):
        response_data = [r.model_dump() if hasattr(r, "model_dump") else r for r in response]
    else:
        response_data = str(response)

    # JSON file (existing behavior)
    if _debug_dir is not None:
        entry = {
            "call_number": _call_counter,
            "stage": stage,
            "messages": messages,
            "response": response_data,
        }
        if context:
            entry["context"] = context

        filename = f"{_call_counter:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug log written to %s", path)

    # MLflow tracing (conditional)
    try:
        import mlflow
        if mlflow.active_run():
            span = mlflow.start_span(name=f"{stage}{slug}")
            span.set_inputs({"messages": messages})
            span.set_outputs({"response": response_data})
            if context:
                span.set_attributes(context)
            span.end()
    except ImportError:
        pass
    except Exception:
        logger.debug("MLflow span creation failed", exc_info=True)


def log_event(
    stage: str,
    data: dict,
    *,
    context: dict | None = None,
) -> None:
    """Log a non-LLM pipeline event (e.g. candidate tier reporting)."""
    global _call_counter
    _call_counter += 1

    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    if _debug_dir is not None:
        entry = {
            "call_number": _call_counter,
            "stage": stage,
            "messages": [],
            "response": data,
        }
        if context:
            entry["context"] = context

        filename = f"{_call_counter:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug event written to %s", path)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _extract_instruction(system_content: str) -> str:
    """Extract the human-readable instruction from a system prompt,
    stripping the Instructor JSON schema boilerplate."""
    marker = "\n\n        As a genius expert"
    idx = system_content.find(marker)
    if idx != -1:
        return system_content[:idx].strip()
    return system_content.strip()


def _render_context(ctx: dict) -> str:
    """Render the context dict as a compact metadata line."""
    parts = []
    if "policy_concept" in ctx:
        parts.append(f"**Policy:** {ctx['policy_concept']}")
    if "policy_type" in ctx:
        parts.append(f"**Type:** {ctx['policy_type']}")
    if "risk_name" in ctx:
        parts.append(f"**Risk:** {ctx['risk_name']}")
    if "risk_id" in ctx:
        parts.append(f"`{ctx['risk_id']}`")
    if "axis_label" in ctx:
        parts.append(f"**Axis:** {ctx['axis_label']}")
    if "axis_uri" in ctx:
        parts.append(f"`{ctx['axis_uri'].split('/')[-1]}`")
    if "num_candidates" in ctx:
        parts.append(f"**Candidates:** {ctx['num_candidates']}")
    if "num_axes" in ctx:
        parts.append(f"**Axes:** {ctx['num_axes']}")
    return " · ".join(parts)


def _render_classify_response(data: list[dict]) -> str:
    lines = ["| Policy | Type | Definition | Justification |",
             "|--------|------|------------|---------------|"]
    for item in data:
        lines.append(
            f"| {item.get('policy_concept', '')} "
            f"| {item.get('policy_type', '')} "
            f"| {item.get('concept_definition', '')} "
            f"| {item.get('justification', '')} |"
        )
    return "\n".join(lines)


def _render_identify_domains_response(data: dict) -> str:
    domains = ", ".join(f"`{d}`" for d in data.get("domains", []))
    return f"**Domains:** {domains}\n\n> {data.get('justification', '')}"


def _render_map_risks_response(data: dict) -> str:
    risks = data.get("matched_risks", [])
    if not risks:
        return "_No risks matched._"
    lines = ["| # | Risk | Relevance | Justification |",
             "|---|------|-----------|---------------|"]
    for r in risks:
        lines.append(
            f"| {r.get('risk_index', '')} "
            f"| {r.get('risk_name', '')} "
            f"| {r.get('relevance', '')} "
            f"| {r.get('justification', '')} |"
        )
    return "\n".join(lines)


def _render_anchor_response(data: dict) -> str:
    axes = data.get("axes", [])
    if not axes:
        return "_No axes selected._"
    lines = ["| ID | Class | Rationale |",
             "|----|-------|-----------|"]
    for a in axes:
        class_id = a.get("class_id", "")
        label = a.get("class_label", a.get("cco_class_label", ""))
        lines.append(
            f"| {class_id} "
            f"| {label} "
            f"| {a.get('rationale', '')} |"
        )
    return "\n".join(lines)


def _render_contextualize_response(data: dict) -> str:
    # Current format: {"variations": [{"instance": "...", "relevance": "high"}, ...]}
    variations = data.get("variations", [])
    if variations:
        lines = ["| Instance | Relevance |",
                 "|----------|-----------|"]
        for v in variations:
            lines.append(f"| {v.get('instance', '')} | {v.get('relevance', '')} |")
        return "\n".join(lines)
    # Legacy format: {"axes": [{"cco_class_uri": "...", "enumerations": [...]}]}
    axes = data.get("axes", [])
    if not axes:
        return "_No context profiles._"
    parts = []
    for ax in axes:
        uri = ax.get("cco_class_uri", "")
        enums = ax.get("enumerations", [])
        lines = [f"**Axis:** `{uri}`\n",
                 "| Class | Relevance |",
                 "|-------|-----------|"]
        for e in enums:
            lines.append(f"| {e.get('class_label', '')} | {e.get('relevance', '')} |")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _render_candidate_tiers_response(data: dict) -> str:
    seeds = data.get("seeds", 0)
    structural = data.get("structural", 0)
    search_connected = data.get("search_connected", 0)
    search_only = data.get("search_only", 0)
    merged = data.get("merged", 0)

    lines = [
        "| Metric | Count |",
        "|--------|-------|",
        f"| Seeds | {seeds} |",
        f"| Structural | {structural} |",
        f"| Search (connected) | {search_connected} |",
        f"| Search (only) | {search_only} |",
        f"| **Merged** | **{merged}** |",
    ]

    seed_uris = data.get("seed_uris", [])
    if seed_uris:
        lines.append("")
        lines.append("**Seed mappings:**\n")
        for s in seed_uris:
            label = s.get("label", "")
            uri = s.get("uri", "")
            predicate = s.get("predicate", "")
            lines.append(f"- `{label or uri}` ({predicate})")

    return "\n".join(lines)


def _render_ingest_response(data) -> str:
    """Render ingest stage responses (context/policies/enrichment)."""
    if isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2, default=str)}\n```"
    if isinstance(data, list):
        return f"```json\n{json.dumps(data, indent=2, default=str)}\n```"
    return str(data)


_STAGE_RENDERERS = {
    "classify": lambda d: _render_classify_response(d) if isinstance(d, list) else _render_ingest_response(d),
    "identify_domains": _render_identify_domains_response,
    "map_risks": _render_map_risks_response,
    "anchor": _render_anchor_response,
    "anchor_tiers": _render_candidate_tiers_response,
    "contextualize": _render_contextualize_response,
}


def _render_entry(entry: dict) -> str:
    """Render a single debug JSON entry to markdown."""
    call = entry.get("call_number", "?")
    stage = entry.get("stage", "unknown")
    context = entry.get("context", {})
    messages = entry.get("messages", [])
    response = entry.get("response")

    # Heading
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = f" — {context[key]}"
                break
    lines = [f"### {call}. {stage}{slug}\n"]

    # Context metadata
    if context:
        lines.append(_render_context(context))
        lines.append("")

    # System instruction (stripped of JSON schema noise)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    if system_msgs:
        instruction = _extract_instruction(system_msgs[0]["content"])
        lines.append("<details><summary>System prompt</summary>\n")
        lines.append(instruction)
        lines.append("\n</details>\n")

    # User prompt (collapsible — often long)
    user_msgs = [m for m in messages if m.get("role") == "user"]
    if user_msgs:
        lines.append("<details><summary>User prompt</summary>\n")
        lines.append(user_msgs[0]["content"])
        lines.append("\n</details>\n")

    # Response — stage-specific rendering
    lines.append("**Response:**\n")
    renderer = _STAGE_RENDERERS.get(stage, _render_ingest_response)
    lines.append(renderer(response))
    lines.append("")

    return "\n".join(lines)


def render_markdown(debug_dir: Path | None = None) -> Path | None:
    """Read all debug JSON files from the directory and write a
    consolidated debug.md alongside them.

    Returns the path to the written markdown file, or None if no debug dir."""
    target = debug_dir or _debug_dir
    if target is None or not target.is_dir():
        return None

    json_files = sorted(target.glob("*.json"))
    if not json_files:
        return None

    entries = []
    for jf in json_files:
        try:
            entries.append(json.loads(jf.read_text()))
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping unreadable debug file: %s", jf)

    # Sort by call_number
    entries.sort(key=lambda e: e.get("call_number", 0))

    # Group by stage for a TOC
    stages_seen: dict[str, int] = {}
    for e in entries:
        s = e.get("stage", "unknown")
        stages_seen[s] = stages_seen.get(s, 0) + 1

    lines = [
        "# Debug Log\n",
        f"**{len(entries)} LLM calls** across stages: "
        + ", ".join(f"{s} ({n})" for s, n in stages_seen.items()),
        "\n---\n",
    ]

    for entry in entries:
        lines.append(_render_entry(entry))
        lines.append("---\n")

    md_path = target / "debug.md"
    md_path.write_text("\n".join(lines))
    logger.info("Debug markdown written to %s", md_path)
    return md_path
