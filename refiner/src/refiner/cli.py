import json
import os
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml

from refiner import debug
from refiner.llm import LLMConfig, TokenTracker, create_client
from refiner.models import Policy, PolicyProfile, RunReport
from refiner.nexus_adapter import detect_nexus_format, nexus_to_policy_profile
from refiner.pipeline import run_pipeline, STAGES
from refiner.export import export_taxonomy

app = typer.Typer()

INGEST_PASSES = ("context", "policies", "enrichment")


def _load_policies(path: Path) -> tuple[list[Policy], PolicyProfile | None]:
    """Load policies from flat array, nexus format, or PolicyProfile JSON."""
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        return [Policy(**p) for p in raw], None
    elif detect_nexus_format(raw):
        doc = nexus_to_policy_profile(raw)
        typer.echo(f"Detected nexus format: {len(doc.policies)} risks projected to policies")
        return doc.policies, doc
    else:
        doc = PolicyProfile(**raw)
        return doc.policies, doc


def _echo_token_usage(tracker: TokenTracker) -> None:
    if tracker.calls == 0:
        return
    typer.echo(f"Token usage: {tracker.prompt_tokens:,} prompt + {tracker.completion_tokens:,} completion = {tracker.total_tokens:,} total ({tracker.calls} calls)")


def _parse_tags(tags: list[str]) -> dict[str, str]:
    """Parse key=value tag strings into a dict."""
    result = {}
    for t in tags:
        if "=" in t:
            k, v = t.split("=", 1)
            result[k] = v
    return result


@app.command()
def ingest(
    document: Path = typer.Argument(..., help="Policy document (.md/.txt) or flat JSON (.json)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path (default: <stem>-policy-profile.json)"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs"),
    skip_enrichment: bool = typer.Option(False, "--skip-enrichment", help="Skip boundary enrichment (Pass 3)"),
    domain: str = typer.Option(None, "--domain", help="Override inferred domain"),
    organization: str = typer.Option(None, "--organization", help="Override inferred organization"),
    until: str = typer.Option(None, "--until", help=f"Run up to this pass: {', '.join(INGEST_PASSES)}"),
):
    """Ingest a policy document or flat JSON into enriched PolicyProfile format."""
    if not document.exists():
        typer.echo(f"Error: {document} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in INGEST_PASSES:
        typer.echo(f"Error: --until must be one of: {', '.join(INGEST_PASSES)}", err=True)
        raise typer.Exit(1)

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    # Detect input format
    document_text = document.read_text()
    if document.suffix == ".json":
        raw = json.loads(document_text)
        if isinstance(raw, dict) and "policies" in raw:
            typer.echo("Error: Already an enriched PolicyProfile — use 'refiner run' directly.", err=True)
            raise typer.Exit(1)
        input_format = "json_array"
    else:
        input_format = "markdown"

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=document.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    from refiner.stages.ingest import ingest as do_ingest
    result = do_ingest(
        document_text, input_format, client, config,
        skip_enrichment=skip_enrichment, until=until,
        domain_override=domain, organization_override=organization,
        report=report,
    )

    out_path = output or document.with_stem(f"{document.stem}-policy-profile").with_suffix(".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    typer.echo(f"Enriched PolicyProfile written to {out_path}")
    typer.echo(f"  Organization: {result.organization.name if result.organization else ''}")
    typer.echo(f"  Domain: {result.domain}")
    typer.echo(f"  Policies: {len(result.policies)}")
    _echo_token_usage(tracker)

    md_path = debug.render_markdown()
    if md_path:
        typer.echo(f"Debug markdown written to {md_path}")

    # Generate ingest report HTML
    from refiner.ingest_report import build_ingest_report
    passes = ["context"]
    if until != "context":
        passes.append("policies")
    if until not in ("context", "policies") and not skip_enrichment:
        passes.append("enrichment")
    meta = {
        "model": config.model,
        "source_document": document.name,
        "timestamp": report.timestamp,
        "input_format": input_format,
        "passes_completed": passes,
    }
    report_path = build_ingest_report(result, report, out_path.parent / f"{document.stem}-ingest-report.html", meta)
    typer.echo(f"Ingest report written to {report_path}")


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
    chroma_dir = nexus_chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)

    from nexus_mcp.risk_index import build_structural_context

    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        ctx = build_structural_context(risks_by_id, groups, actions_by_id)
        idx.index_risks(all_risks, structural_context=ctx)
    return create_tool_handlers(
        risk_index=idx, risks_by_id=risks_by_id, actions_by_id=actions_by_id,
        taxonomies=taxonomies, groups=groups,
    )


def _create_onto_handlers(ontoquery_chroma_dir: Path) -> dict:
    from ontoquery.mcp_server import create_tool_handlers
    return create_tool_handlers(ontoquery_chroma_dir)


@app.command()
def run(
    policy_json: Path = typer.Argument(..., help="Path to policy JSON file"),
    until: str = typer.Option(None, "--until", help=f"Run up to this stage: {', '.join(STAGES)}"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory (default: current dir)"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs (prompts + responses)"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR", help="Path to ai-atlas-nexus repo"),
    ontoquery_chroma_dir: Path = typer.Option(Path(".chroma"), "--ontoquery-chroma-dir", envvar="ONTOQUERY_CHROMA_DIR", help="Ontoquery ChromaDB directory"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR", help="Nexus ChromaDB directory"),
    search_strategy: str = typer.Option("llm", "--search-strategy", help="Search merge strategy: llm (default), weighted, or grouped"),
    track: bool = typer.Option(False, "--track", help="Enable MLflow tracking + tracing"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
    tags: list[str] = typer.Option([], "--tag", help="MLflow tags as key=value (repeatable)"),
):
    """Run the refiner pipeline on a policy JSON file."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in STAGES:
        typer.echo(f"Error: --until must be one of: {', '.join(STAGES)}", err=True)
        raise typer.Exit(1)

    # Load policies — detect flat array vs nexus format vs enriched PolicyProfile
    policies, policy_profile = _load_policies(policy_json)
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    # Create report
    report = RunReport(
        model=config.model,
        policy_set=policy_json.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Create handlers — only load what's needed for the requested stages
    needs_risk = until not in ("identify_domains",)
    needs_onto = until not in ("identify_domains", "map_risks")
    if needs_risk:
        if not nexus_base_dir:
            typer.echo("Error: --nexus-base-dir is required (or set NEXUS_BASE_DIR)", err=True)
            raise typer.Exit(1)
        risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)
    else:
        risk_handlers = {}
    onto_handlers = _create_onto_handlers(ontoquery_chroma_dir) if needs_onto else {}

    # Load SSSOM seed mappings
    layer1_mappings = None
    layer2_mappings = None
    data_dir = Path(__file__).parent.parent.parent / "data"
    layer1_path = data_dir / "risk-to-vocabulary.sssom.tsv"
    layer2_path = data_dir / "vocabulary-to-ontology.sssom.tsv"
    bfo_fallbacks = None
    bfo_path = data_dir / "ontology-to-bfo.sssom.tsv"
    if layer1_path.exists() and layer2_path.exists():
        from refiner.ontology_seeds import SSSOMIndex, load_bfo_fallbacks
        layer1_mappings = SSSOMIndex.from_tsv(layer1_path)
        layer2_mappings = SSSOMIndex.from_tsv(layer2_path, expand_objects=True)
        typer.echo(f"Loaded SSSOM seeds: {len(layer1_mappings.mappings)} layer-1, {len(layer2_mappings.mappings)} layer-2 mappings")
        if bfo_path.exists():
            bfo_fallbacks = load_bfo_fallbacks(bfo_path)
            typer.echo(f"Loaded BFO fallbacks: {len(bfo_fallbacks)} mappings")

    if search_strategy != "llm":
        typer.echo(f"Warning: --search-strategy is deprecated (SSSOM seeds used instead)", err=True)

    # Run pipeline
    client_slug = policy_json.stem
    for _sfx in ("-policy-profile", "-policy-document", "-enriched"):
        if client_slug.endswith(_sfx):
            client_slug = client_slug[:-len(_sfx)]
            break
    typer.echo(f"Running pipeline{f' until {until}' if until else ''}...")
    state = run_pipeline(
        policies, client, config, risk_handlers, onto_handlers,
        until=until, report=report,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        bfo_fallbacks=bfo_fallbacks,
        run_slug=client_slug,
    )
    # TODO: thread policy_profile into pipeline stages (e.g. identify_domains domain hint)
    state.policy_profile = policy_profile

    # Attach policy source to risk landscape
    if state.risk_landscape is not None and policy_profile:
        from refiner.models import PolicySourceRef
        state.risk_landscape.policy_source = PolicySourceRef(
            organization=policy_profile.organization.name if policy_profile.organization else None,
            domain=policy_profile.domain,
            policy_count=len(policy_profile.policies),
        )

    # Output
    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)

    mlflow_active = False
    if track:
        try:
            import mlflow
            from refiner.tracking import _get_git_context, write_run_id
        except ImportError:
            typer.echo("Error: MLflow is required for --track. Install with: uv sync --extra tracking", err=True)
            raise typer.Exit(1)

        if not tracking_uri:
            typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required for --track", err=True)
            raise typer.Exit(1)

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(policy_json.stem)
        mlflow.start_run()
        mlflow_active = True

        git_sha, git_dirty = _get_git_context()
        mlflow.log_params({
            "model": config.model,
            "policy_set": policy_json.name,
            "git_sha": git_sha,
            "git_dirty": str(git_dirty),
        })
        if description:
            mlflow.set_tag("description", description)
        parsed_tags = _parse_tags(tags)
        if parsed_tags:
            mlflow.set_tags(parsed_tags)

        write_run_id(out, mlflow.active_run().info.run_id)

    try:
        if state.domain_context is not None and state.risk_mappings is not None:
            doc = state.domain_context

            # Set policy source from PolicyProfile
            if state.policy_profile:
                from refiner.models import PolicySourceRef
                doc.policy_source = PolicySourceRef(
                    organization=state.policy_profile.organization.name if state.policy_profile.organization else None,
                    domain=state.policy_profile.domain,
                    policy_count=len(state.policy_profile.policies),
                )

            # Validate cross-mapping targets against all risk IDs shown to the model
            taxonomy, _profiles = export_taxonomy(
                client_slug,
                domain_context=state.domain_context,
                risk_landscape=state.risk_landscape,
                valid_risk_ids=state.seen_risk_ids,
                report=report,
            )
            report.stages_completed.append("structure")
            report.token_usage = tracker.to_dict()

            # Serialize RiskLandscape artifact
            if state.risk_landscape is not None:
                rl_path = out / f"{client_slug}-risk-landscape.yaml"
                rl_path.write_text(yaml.dump(
                    state.risk_landscape.model_dump(), default_flow_style=False, sort_keys=False,
                ))
                typer.echo(f"Risk landscape written to {rl_path}")
                from refiner.artifact_reports import build_risk_landscape_report
                build_risk_landscape_report(
                    state.risk_landscape.model_dump(),
                    out / f"{client_slug}-risk-landscape.html",
                )

            tax_path = out / f"{client_slug}-taxonomy.yaml"
            tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
            typer.echo(f"Taxonomy written to {tax_path}")
            from refiner.artifact_reports import build_taxonomy_report
            build_taxonomy_report(taxonomy, out / f"{client_slug}-taxonomy.html")

            prof_path = out / f"{client_slug}-domain-context.yaml"
            prof_path.write_text(yaml.dump(
                doc.model_dump(), default_flow_style=False, sort_keys=False,
            ))
            typer.echo(f"Domain context written to {prof_path}")
            from refiner.artifact_reports import build_domain_context_report
            build_domain_context_report(
                doc.model_dump(),
                out / f"{client_slug}-domain-context.html",
            )

            report_path = out / f"{client_slug}-run-report.yaml"
            report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
            typer.echo(f"Report written to {report_path}")
            from refiner.artifact_reports import build_run_report_html
            build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
        else:
            report.token_usage = tracker.to_dict()
            # Partial run — dump intermediate state as JSON
            state_path = out / f"{client_slug}-state.json"
            state_data = {
                "policies": [p.model_dump() for p in state.policies],
            }
            if state.selected_domains:
                state_data["selected_domains"] = state.selected_domains
            if state.risk_mappings:
                state_data["risk_mappings"] = [m.model_dump() for m in state.risk_mappings]
            if state.risk_details:
                state_data["risk_details"] = state.risk_details
            if state.variation_axes:
                state_data["variation_axes"] = [a.model_dump() for a in state.variation_axes]
            if state.risk_landscape:
                rl_path = out / f"{client_slug}-risk-landscape.yaml"
                rl_path.write_text(yaml.dump(
                    state.risk_landscape.model_dump(), default_flow_style=False, sort_keys=False,
                ))
                typer.echo(f"Risk landscape written to {rl_path}")
                from refiner.artifact_reports import build_risk_landscape_report
                build_risk_landscape_report(
                    state.risk_landscape.model_dump(),
                    out / f"{client_slug}-risk-landscape.html",
                )
            state_path.write_text(json.dumps(state_data, indent=2))
            typer.echo(f"Intermediate state written to {state_path}")

            if report.events:
                report_path = out / f"{client_slug}-run-report.yaml"
                report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
                typer.echo(f"Report written to {report_path}")
                from refiner.artifact_reports import build_run_report_html
                build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
        md_path = debug.render_markdown()
        if md_path:
            typer.echo(f"Debug markdown written to {md_path}")
    except Exception:
        if mlflow_active:
            import mlflow
            mlflow.end_run(status="FAILED")
        raise
    else:
        _echo_token_usage(tracker)
        if mlflow_active:
            import mlflow
            from refiner.tracking import _collect_artifacts
            if tracker.calls > 0:
                mlflow.log_metrics({
                    "tokens.prompt": tracker.prompt_tokens,
                    "tokens.completion": tracker.completion_tokens,
                    "tokens.total": tracker.total_tokens,
                    "tokens.calls": tracker.calls,
                })
            files, dirs = _collect_artifacts(out)
            for f in files:
                mlflow.log_artifact(str(f))
            for d in dirs:
                mlflow.log_artifacts(str(d), artifact_path=d.name)
            run_id = mlflow.active_run().info.run_id
            mlflow.end_run()
            typer.echo(f"Logged to MLflow: run {run_id}")


@app.command("map-risks")
def map_risks_cmd(
    policy_json: Path = typer.Argument(..., help="Enriched PolicyProfile JSON"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR"),
    debug_dir: Path = typer.Option(None, "--debug"),
):
    """Run risk landscape mapping on a PolicyProfile. Produces a RiskLandscape YAML artifact."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)
    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required", err=True)
        raise typer.Exit(1)
    if not nexus_base_dir:
        typer.echo("Error: --nexus-base-dir is required", err=True)
        raise typer.Exit(1)

    policies, doc = _load_policies(policy_json)
    if doc is None:
        typer.echo("Error: expected enriched PolicyProfile, got flat array. Run 'refiner ingest' first.", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policy_json.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)

    # Stage 1: identify domains
    from refiner.stages.identify_domains import identify_domains
    selected_domains = identify_domains(policies, client, config, report=report)

    # Stage 2: map risks
    from refiner.stages.map_risks import map_risks
    mappings, risk_details, seen_ids, related, actions, coverage_gaps = map_risks(
        policies, client, config, risk_handlers, report=report,
    )

    # Build RiskLandscape artifact
    from refiner.stages.build_landscape import build_risk_landscape
    landscape = build_risk_landscape(
        mappings=mappings,
        risk_details_cache=risk_details,
        related_risks=related,
        risk_actions=actions,
        selected_domains=selected_domains,
        model=config.model,
        run_slug=policy_json.stem,
        timestamp=report.timestamp,
        policy_profile=doc,
        coverage_gaps=coverage_gaps,
    )

    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = policy_json.stem

    rl_path = out / f"{client_slug}-risk-landscape.yaml"
    rl_path.write_text(yaml.dump(
        landscape.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Risk landscape written to {rl_path}")
    from refiner.artifact_reports import build_risk_landscape_report
    build_risk_landscape_report(landscape.model_dump(), out / f"{client_slug}-risk-landscape.html")

    report.token_usage = tracker.to_dict()
    report_path = out / f"{client_slug}-run-report.yaml"
    report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
    typer.echo(f"Report written to {report_path}")
    from refiner.artifact_reports import build_run_report_html
    build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
    _echo_token_usage(tracker)


@app.command()
def ground(
    risk_landscape_yaml: Path = typer.Argument(..., help="RiskLandscape YAML from 'refiner map-risks'"),
    policies: Path = typer.Option(..., "--policies", help="Enriched PolicyProfile JSON"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY"),
    ontoquery_chroma_dir: Path = typer.Option(Path(".chroma"), "--ontoquery-chroma-dir", envvar="ONTOQUERY_CHROMA_DIR"),
    nexus_base_dir: str = typer.Option(None, "--nexus-base-dir", envvar="NEXUS_BASE_DIR"),
    nexus_chroma_dir: Path = typer.Option(Path(".chroma"), "--nexus-chroma-dir", envvar="NEXUS_CHROMA_DIR"),
    debug_dir: Path = typer.Option(None, "--debug"),
):
    """Run ontological grounding on a RiskLandscape. Produces DomainContext YAML + taxonomy."""
    if not risk_landscape_yaml.exists():
        typer.echo(f"Error: {risk_landscape_yaml} does not exist", err=True)
        raise typer.Exit(1)
    if not policies.exists():
        typer.echo(f"Error: {policies} does not exist", err=True)
        raise typer.Exit(1)
    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required", err=True)
        raise typer.Exit(1)

    from refiner.models import RiskLandscape
    landscape = RiskLandscape(**yaml.safe_load(risk_landscape_yaml.read_text()))

    policy_list, doc = _load_policies(policies)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    tracker = TokenTracker()
    client = create_client(config, tracker=tracker)
    debug.configure(debug_dir)

    report = RunReport(
        model=config.model,
        policy_set=policies.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    onto_handlers = _create_onto_handlers(ontoquery_chroma_dir)

    # Load SSSOM seeds
    data_dir = Path(__file__).parent.parent.parent / "data"
    layer1_path = data_dir / "risk-to-vocabulary.sssom.tsv"
    layer2_path = data_dir / "vocabulary-to-ontology.sssom.tsv"
    bfo_path = data_dir / "ontology-to-bfo.sssom.tsv"
    layer1_mappings = None
    layer2_mappings = None
    bfo_fallbacks = None
    if layer1_path.exists() and layer2_path.exists():
        from refiner.ontology_seeds import SSSOMIndex, load_bfo_fallbacks
        layer1_mappings = SSSOMIndex.from_tsv(layer1_path)
        layer2_mappings = SSSOMIndex.from_tsv(layer2_path, expand_objects=True)
        if bfo_path.exists():
            bfo_fallbacks = load_bfo_fallbacks(bfo_path)

    # Optional: nexus handlers for cross-mapping resolution
    nexus_handlers = None
    if nexus_base_dir:
        nexus_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)

    # Compute CSO safety filter
    from refiner.stages.anchor import anchor, build_generic_safety_uris
    from refiner.stages.identify_domains import ALWAYS_INCLUDED
    generic_safety_uris: set[str] = set()
    domain_specific = set(landscape.selected_domains) - set(ALWAYS_INCLUDED)
    if domain_specific:
        uris = build_generic_safety_uris(onto_handlers)
        if uris:
            generic_safety_uris = uris

    # Anchor
    variation_axes, vocabulary_contexts = anchor(
        risk_landscape=landscape,
        client=client,
        config=config,
        onto_handlers=onto_handlers,
        nexus_handlers=nexus_handlers,
        layer1_mappings=layer1_mappings,
        layer2_mappings=layer2_mappings,
        report=report,
        generic_safety_uris=generic_safety_uris,
        policies=policy_list,
        bfo_fallbacks=bfo_fallbacks,
    )

    # Contextualize
    from refiner.stages.contextualize import contextualize
    dcd = contextualize(
        variation_axes, client, config, onto_handlers,
        risk_landscape=landscape,
        report=report,
        policies=policy_list,
        vocabulary_contexts=vocabulary_contexts,
    )

    # Enrich DCD with policy source
    if doc:
        from refiner.models import PolicySourceRef
        dcd.policy_source = PolicySourceRef(
            organization=doc.organization.name if doc.organization else None,
            domain=doc.domain,
            policy_count=len(doc.policies),
        )

    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = risk_landscape_yaml.stem.replace("-risk-landscape", "")

    # Write DCD
    dcd_path = out / f"{client_slug}-domain-context.yaml"
    dcd_path.write_text(yaml.dump(
        dcd.model_dump(), default_flow_style=False, sort_keys=False,
    ))
    typer.echo(f"Domain context written to {dcd_path}")
    from refiner.artifact_reports import build_domain_context_report
    build_domain_context_report(dcd.model_dump(), out / f"{client_slug}-domain-context.html")

    # Export taxonomy
    taxonomy, _ = export_taxonomy(
        client_slug,
        domain_context=dcd,
        risk_landscape=landscape,
        report=report,
    )
    tax_path = out / f"{client_slug}-taxonomy.yaml"
    tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
    typer.echo(f"Taxonomy written to {tax_path}")
    from refiner.artifact_reports import build_taxonomy_report
    build_taxonomy_report(taxonomy, out / f"{client_slug}-taxonomy.html")

    report.token_usage = tracker.to_dict()
    report_path = out / f"{client_slug}-run-report.yaml"
    report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
    typer.echo(f"Report written to {report_path}")
    from refiner.artifact_reports import build_run_report_html
    build_run_report_html(report.to_dict(), out / f"{client_slug}-run-report.html")
    _echo_token_usage(tracker)


def _discover_slug(output_dir: Path) -> str:
    matches = list(output_dir.glob("*-domain-context.yaml"))
    if matches:
        return matches[0].name.replace("-domain-context.yaml", "")
    return "dataset"


@app.command()
def emit(
    output_dir: Path = typer.Argument(..., help="Directory from a prior 'refiner run --output'"),
    policies: Path = typer.Option(..., "--policies", help="Original policy JSON file"),
    samples_per_risk: int = typer.Option(10, "--samples-per-risk", help="Samples per risk (default: 10)"),
    seed: int = typer.Option(None, "--seed", help="Random seed for reproducible sampling"),
    output: Path = typer.Option(None, "--output", "-o", help="Output JSONL path (default: <output-dir>/<slug>-dataset.jsonl)"),
    technique_weights: str = typer.Option(
        None, "--technique-weights",
        help="JSON string with technique weight overrides, e.g. '{\"pretexting\": 2, \"analytical_reframing\": 1}'",
    ),
    axes_per_prompt: int = typer.Option(None, "--axes-per-prompt", help="Number of axes per prompt (default: 3)"),
    mode: str = typer.Option("redteam", "--mode", help="Generation mode: redteam, utility, or paired"),
    benign_weights: str = typer.Option(
        None, "--benign-weights",
        help="JSON string with benign frame weight overrides, e.g. '{\"routine_practice\": 2}'",
    ),
):
    """Emit an sdg_hub-ready JSONL dataset from domain context profiles."""
    if not output_dir.is_dir():
        typer.echo(f"Error: {output_dir} is not a directory", err=True)
        raise typer.Exit(1)
    if not policies.exists():
        typer.echo(f"Error: {policies} does not exist", err=True)
        raise typer.Exit(1)
    if mode not in ("redteam", "utility", "paired"):
        typer.echo(f"Error: --mode must be redteam, utility, or paired (got '{mode}')", err=True)
        raise typer.Exit(1)

    if output:
        out_path = output
    else:
        slug = _discover_slug(output_dir)
        if mode == "paired":
            out_path = output_dir / f"{slug}-dataset-redteam.jsonl"
        elif mode == "utility":
            out_path = output_dir / f"{slug}-dataset-utility.jsonl"
        else:
            out_path = output_dir / f"{slug}-dataset.jsonl"

    parsed_weights = None
    if technique_weights:
        try:
            parsed_weights = json.loads(technique_weights)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: invalid JSON for --technique-weights: {e}", err=True)
            raise typer.Exit(1)

    parsed_benign_weights = None
    if benign_weights:
        try:
            parsed_benign_weights = json.loads(benign_weights)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: invalid JSON for --benign-weights: {e}", err=True)
            raise typer.Exit(1)

    from refiner.emit import emit as do_emit
    do_emit(output_dir, policies, samples_per_risk, out_path, seed=seed,
            technique_weights=parsed_weights, axes_per_prompt=axes_per_prompt,
            mode=mode, benign_weights=parsed_benign_weights)
    typer.echo(f"Dataset written to {out_path}")

    # Build dataset HTML report
    rows = [json.loads(line) for line in out_path.read_text().strip().split("\n") if line.strip()]
    from refiner.artifact_reports import build_dataset_report
    build_dataset_report(rows, out_path.with_suffix(".html"))
    typer.echo(f"Dataset report written to {out_path.with_suffix('.html')}")


@app.command()
def evaluate(
    output_dir: Path = typer.Argument(..., help="Directory from a prior 'refiner run --output'"),
    emit_path: Path = typer.Option(None, "--emit", help="Path to emit dataset JSONL"),
    adversarial_path: Path = typer.Option(None, "--adversarial", help="Path to adversarial prompts JSONL"),
    policies_path: Path = typer.Option(None, "--policies", help="Original policy JSON (for zero-match detection)"),
    judge: bool = typer.Option(False, "--judge", help="Run judge-model evaluation"),
    judge_model: str = typer.Option(None, "--judge-model", help="Judge model name"),
    judge_base_url: str = typer.Option(None, "--judge-base-url", help="Judge model API base URL"),
    judge_api_key: str = typer.Option(None, "--judge-api-key", help="Judge model API key"),
    judge_sample: int = typer.Option(None, "--judge-sample", help="Score only N random prompts"),
    output: Path = typer.Option(None, "--output", "-o", help="Output evaluation JSON path"),
    track: bool = typer.Option(False, "--track", help="Log evaluation to MLflow"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
    tags: list[str] = typer.Option([], "--tag", help="MLflow tags as key=value (repeatable)"),
):
    """Evaluate pipeline outputs with metrics and optional judge scoring."""
    if not output_dir.is_dir():
        typer.echo(f"Error: {output_dir} is not a directory", err=True)
        raise typer.Exit(1)

    from refiner.evaluate import run_evaluation, format_summary
    evaluation = run_evaluation(
        output_dir, emit_path=emit_path, adversarial_path=adversarial_path,
        policies_path=policies_path,
    )

    if judge and adversarial_path:
        import json as json_mod
        import random
        from collections import defaultdict as dd
        from refiner.judge import judge_prompt as jp, aggregate_judge_results, compute_score_distribution
        from refiner.evaluate import risk_id_to_framework
        from refiner.llm import LLMConfig, create_client

        j_base = judge_base_url or os.environ.get("REFINER_BASE_URL", "")
        j_model = judge_model or os.environ.get("REFINER_MODEL", "")
        j_key = judge_api_key or os.environ.get("REFINER_API_KEY", "none")
        j_config = LLMConfig(base_url=j_base, model=j_model, api_key=j_key)
        j_client = create_client(j_config)

        adv_rows = [json_mod.loads(line) for line in adversarial_path.read_text().strip().split("\n") if line]
        if judge_sample and judge_sample < len(adv_rows):
            adv_rows = random.sample(adv_rows, judge_sample)

        scores = []
        scores_by_policy: dict[str, list] = dd(list)
        scores_by_risk: dict[str, list] = dd(list)
        scores_by_technique: dict[str, list] = dd(list)
        scores_by_framework: dict[str, list] = dd(list)
        for row in adv_rows:
            s = jp(
                j_client, j_config,
                prompt_text=row.get("prompt", ""),
                policy_concept=row.get("policy_concept", ""),
                concept_definition=row.get("concept_definition", ""),
                risk_name=row.get("risk_name", ""),
                sampled_axes=row.get("sampled_axes", []),
            )
            score_dict = {
                "subtlety": s.subtlety, "plausibility": s.plausibility,
                "domain_grounding": s.domain_grounding, "policy_relevance": s.policy_relevance,
            }
            scores.append(score_dict)
            scores_by_policy[row.get("policy_concept", "unknown")].append(score_dict)
            scores_by_risk[row.get("risk_id", "unknown")].append(score_dict)
            scores_by_technique[row.get("technique", "unknown")].append(score_dict)
            scores_by_framework[risk_id_to_framework(row.get("risk_id", ""))].append(score_dict)

        evaluation["judge_evaluation"] = {
            "model": j_model,
            "prompts_scored": len(scores),
            "aggregates": aggregate_judge_results(scores),
            "score_distribution": compute_score_distribution(scores),
            "by_policy_concept": {
                pc: aggregate_judge_results(pc_scores)
                for pc, pc_scores in sorted(scores_by_policy.items())
            },
            "by_risk": {
                rid: aggregate_judge_results(risk_scores)
                for rid, risk_scores in sorted(scores_by_risk.items())
            },
            "by_technique": {
                tech: aggregate_judge_results(tech_scores)
                for tech, tech_scores in sorted(scores_by_technique.items())
            },
            "by_risk_framework": {
                fw: aggregate_judge_results(fw_scores)
                for fw, fw_scores in sorted(scores_by_framework.items())
            },
        }

    summary = format_summary(evaluation)
    typer.echo(summary)

    out_path = output
    if out_path is None:
        slug = evaluation.get("run", {}).get("policy_set", "eval").replace(".json", "")
        for _sfx in ("-policy-profile", "-policy-document", "-enriched"):
            if slug.endswith(_sfx):
                slug = slug[:-len(_sfx)]
                break
        out_path = output_dir / f"{slug}-evaluation.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evaluation, indent=2))
    typer.echo(f"Written to {out_path}")

    from refiner.evaluate import build_html_report
    html_path = out_path.with_suffix(".html")
    build_html_report(evaluation, html_path)
    typer.echo(f"HTML report written to {html_path}")

    if track:
        try:
            from refiner.tracking import log_run_to_mlflow, read_run_id, write_run_id
        except ImportError:
            typer.echo("Error: MLflow is required for --track. Install with: uv sync --extra tracking", err=True)
            raise typer.Exit(1)

        if not tracking_uri:
            typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required for --track", err=True)
            raise typer.Exit(1)

        existing_run_id = read_run_id(output_dir)
        run_id = log_run_to_mlflow(
            evaluation, output_dir, tracking_uri,
            description=description, run_id=existing_run_id,
            extra_tags=_parse_tags(tags),
        )
        if not existing_run_id:
            write_run_id(output_dir, run_id)
        typer.echo(f"Logged to MLflow: run {run_id}")


@app.command()
def track(
    output_dir: Path = typer.Argument(..., help="Directory with evaluation outputs to track"),
    tracking_uri: str = typer.Option(None, "--tracking-uri", envvar="MLFLOW_TRACKING_URI", help="MLflow tracking server URI"),
    description: str = typer.Option(None, "--description", help="Human-readable description for this run"),
    tags: list[str] = typer.Option([], "--tag", help="MLflow tags as key=value (repeatable)"),
):
    """Retroactively log an existing evaluation to MLflow."""
    if not output_dir.is_dir():
        typer.echo(f"Error: {output_dir} is not a directory", err=True)
        raise typer.Exit(1)

    try:
        from refiner.tracking import log_run_to_mlflow, read_run_id, write_run_id
    except ImportError:
        typer.echo("Error: MLflow is required. Install with: uv sync --extra tracking", err=True)
        raise typer.Exit(1)

    if not tracking_uri:
        typer.echo("Error: --tracking-uri or MLFLOW_TRACKING_URI is required", err=True)
        raise typer.Exit(1)

    from refiner.evaluate import _discover_file
    eval_path = _discover_file(output_dir, "*-evaluation.json")
    if not eval_path:
        typer.echo(f"Error: no *-evaluation.json found in {output_dir}", err=True)
        raise typer.Exit(1)

    evaluation = json.loads(eval_path.read_text())
    existing_run_id = read_run_id(output_dir)

    run_id = log_run_to_mlflow(
        evaluation, output_dir, tracking_uri,
        description=description, run_id=existing_run_id,
        extra_tags=_parse_tags(tags),
    )
    if not existing_run_id:
        write_run_id(output_dir, run_id)
    typer.echo(f"Logged to MLflow: run {run_id}")


if __name__ == "__main__":
    app()
