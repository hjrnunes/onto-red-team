import json
import os
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml

from risk_landscaper import debug
from risk_landscaper.llm import LLMConfig, TokenTracker, create_client
from risk_landscaper.models import Policy, PolicyProfile, RunReport
from risk_landscaper.nexus_adapter import detect_nexus_format, nexus_to_policy_profile

app = typer.Typer()


@app.callback()
def main():
    """Risk landscaper — policy-driven risk landscape generation."""


def _load_input(path: Path) -> tuple[str, str, PolicyProfile | None]:
    text = path.read_text()
    if path.suffix == ".json":
        raw = json.loads(text)
        if isinstance(raw, list):
            return text, "json_array", None
        if detect_nexus_format(raw):
            profile = nexus_to_policy_profile(raw)
            return text, "policy_profile", profile
        if "policies" in raw:
            profile = PolicyProfile(**raw)
            return text, "policy_profile", profile
    return text, "markdown", None


def _create_risk_handlers(nexus_base_dir: str, nexus_chroma_dir: Path) -> dict:
    from nexus_mcp.server import create_tool_handlers
    from nexus_mcp.risk_index import RiskIndex
    from ai_atlas_nexus import AIAtlasNexus

    nexus = AIAtlasNexus(base_dir=nexus_base_dir)
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")
    nexus_chroma_dir.mkdir(parents=True, exist_ok=True)

    from nexus_mcp.risk_index import build_structural_context

    idx = RiskIndex(nexus_chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        ctx = build_structural_context(risks_by_id, groups, actions_by_id)
        idx.index_risks(all_risks, structural_context=ctx)
    return create_tool_handlers(
        risk_index=idx, risks_by_id=risks_by_id, actions_by_id=actions_by_id,
        taxonomies=taxonomies, groups=groups,
    )


@app.command()
def run(
    policy_file: Path = typer.Argument(..., help="Policy document (.md/.txt/.json)"),
    output: Path = typer.Option(..., "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR", help="Path to ai-atlas-nexus repo"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR", help="Nexus ChromaDB directory"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs"),
    skip_enrichment: bool = typer.Option(False, "--skip-enrichment", help="Skip ingest enrichment pass"),
    max_concurrent: int = typer.Option(1, "--max-concurrent", help="Max parallel LLM calls in map_risks"),
    input_format: str = typer.Option(None, "--input-format", help="Input format: markdown or json_array (auto-detected if omitted)"),
):
    """Run the risk landscaper pipeline: ingest -> detect_domain -> map_risks -> build_landscape."""
    if not policy_file.exists():
        typer.echo(f"Error: {policy_file} does not exist", err=True)
        raise typer.Exit(1)

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    if not nexus_base_dir:
        typer.echo("Error: --nexus-base-dir is required (or set NEXUS_BASE_DIR)", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key, max_concurrent=max_concurrent)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policy_file.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    output.mkdir(parents=True, exist_ok=True)

    # --- Stage 1: Ingest ---
    text, detected_format, pre_parsed = _load_input(policy_file)
    fmt = input_format or detected_format

    if pre_parsed is not None:
        profile = pre_parsed
        typer.echo(f"Loaded pre-parsed profile: {len(profile.policies)} policies")
        report.stages_completed.append("ingest")
    else:
        from risk_landscaper.stages.ingest import ingest
        typer.echo(f"Ingesting {policy_file.name} (format: {fmt})...")
        profile = ingest(
            text, fmt, client, config,
            skip_enrichment=skip_enrichment,
            report=report,
        )
        report.stages_completed.append("ingest")
        typer.echo(f"  Organization: {profile.organization.name if profile.organization else ''}")
        typer.echo(f"  Domain: {profile.domain}")
        typer.echo(f"  Policies: {len(profile.policies)}")

    profile_path = output / "policy-profile.json"
    profile_path.write_text(json.dumps(profile.model_dump(), indent=2))

    # --- Stage 2: Detect domain ---
    from risk_landscaper.stages.detect_domain import detect_domain
    selected_domains = detect_domain(profile, client, config, report=report)
    report.stages_completed.append("detect_domain")
    typer.echo(f"  Domain: {selected_domains}")

    # --- Stage 3: Map risks ---
    from risk_landscaper.stages.map_risks import map_risks
    risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)
    typer.echo(f"Mapping {len(profile.policies)} policies to risks...")
    mappings, risk_details, seen_ids, related_risks, risk_actions, coverage_gaps = map_risks(
        profile.policies, client, config, risk_handlers, report=report,
    )
    report.stages_completed.append("map_risks")
    total_matches = sum(len(m.matched_risks) for m in mappings)
    typer.echo(f"  {total_matches} risk matches across {len(mappings)} policies")
    if coverage_gaps:
        typer.echo(f"  {len(coverage_gaps)} coverage gap(s) detected")

    # --- Stage 4: Build landscape ---
    from risk_landscaper.stages.build_landscape import build_risk_landscape

    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details,
        related_risks=related_risks,
        risk_actions=risk_actions,
        selected_domains=selected_domains,
        model=config.model,
        run_slug=policy_file.stem,
        timestamp=report.timestamp,
        coverage_gaps=coverage_gaps,
        policy_profile=profile,
    )
    report.stages_completed.append("build_landscape")

    landscape_path = output / "risk-landscape.yaml"
    landscape_path.write_text(yaml.dump(
        landscape.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Risk landscape written to {landscape_path}")
    typer.echo(f"  {len(landscape.risks)} unique risks, {len(landscape.framework_coverage)} frameworks")

    # --- Write report ---
    report.token_usage = tracker.to_dict()
    report_path = output / "run-report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))

    typer.echo(f"Token usage: {tracker.prompt_tokens:,} prompt + {tracker.completion_tokens:,} completion = {tracker.total_tokens:,} total ({tracker.calls} calls)")
    typer.echo("Done.")
