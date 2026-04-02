import json
import os
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml

from refiner import debug
from refiner.llm import LLMConfig, create_client
from refiner.models import Policy, PolicyDocument, RunReport
from refiner.pipeline import run_pipeline, STAGES
from refiner.stages.structure import structure

app = typer.Typer()

INGEST_PASSES = ("context", "policies", "enrichment")


@app.command()
def ingest(
    document: Path = typer.Argument(..., help="Policy document (.md/.txt) or flat JSON (.json)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path (default: <stem>-enriched.json)"),
    base_url: str = typer.Option(None, "--base-url", envvar="REFINER_BASE_URL", help="LLM API base URL"),
    model: str = typer.Option(None, "--model", envvar="REFINER_MODEL", help="LLM model name"),
    api_key: str = typer.Option("none", "--api-key", envvar="REFINER_API_KEY", help="LLM API key"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs"),
    skip_enrichment: bool = typer.Option(False, "--skip-enrichment", help="Skip boundary enrichment (Pass 3)"),
    domain: str = typer.Option(None, "--domain", help="Override inferred domain"),
    organization: str = typer.Option(None, "--organization", help="Override inferred organization"),
    until: str = typer.Option(None, "--until", help=f"Run up to this pass: {', '.join(INGEST_PASSES)}"),
):
    """Ingest a policy document or flat JSON into enriched PolicyDocument format."""
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
            typer.echo("Error: Already an enriched PolicyDocument — use 'refiner run' directly.", err=True)
            raise typer.Exit(1)
        input_format = "json_array"
    else:
        input_format = "markdown"

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    client = create_client(config)
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

    out_path = output or document.with_stem(f"{document.stem}-enriched").with_suffix(".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    typer.echo(f"Enriched PolicyDocument written to {out_path}")
    typer.echo(f"  Organization: {result.organization}")
    typer.echo(f"  Domain: {result.domain}")
    typer.echo(f"  Policies: {len(result.policies)}")


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
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)
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
):
    """Run the refiner pipeline on a policy JSON file."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in STAGES:
        typer.echo(f"Error: --until must be one of: {', '.join(STAGES)}", err=True)
        raise typer.Exit(1)

    # Load policies — detect flat array vs enriched PolicyDocument
    raw = json.loads(policy_json.read_text())
    if isinstance(raw, list):
        policies = [Policy(**p) for p in raw]
        doc_context = None
    else:
        doc = PolicyDocument(**raw)
        policies = doc.policies
        doc_context = doc
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")

    if not base_url or not model:
        typer.echo("Error: --base-url and --model are required (or set REFINER_BASE_URL / REFINER_MODEL)", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model, api_key=api_key)
    client = create_client(config)
    debug.configure(debug_dir)

    # Create report
    report = RunReport(
        model=config.model,
        policy_set=policy_json.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Create handlers — only load what's needed for the requested stages
    needs_risk = until not in ("classify", "identify_domains")
    needs_onto = until not in ("classify", "identify_domains", "map_risks")
    if needs_risk:
        if not nexus_base_dir:
            typer.echo("Error: --nexus-base-dir is required (or set NEXUS_BASE_DIR)", err=True)
            raise typer.Exit(1)
        risk_handlers = _create_risk_handlers(nexus_base_dir, nexus_chroma_dir)
    else:
        risk_handlers = {}
    onto_handlers = _create_onto_handlers(ontoquery_chroma_dir) if needs_onto else {}

    # Run pipeline
    typer.echo(f"Running pipeline{f' until {until}' if until else ''}...")
    state = run_pipeline(policies, client, config, risk_handlers, onto_handlers, until=until, report=report)
    # TODO: thread doc_context into pipeline stages (e.g. identify_domains domain hint)
    state.doc_context = doc_context

    # Output
    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = policy_json.stem

    if state.domain_context is not None and state.classifications is not None and state.risk_mappings is not None:
        # Enrich domain context profiles with risk details and cross-mappings
        from refiner.stages.identify_domains import derive_source_ontology
        FRAMEWORK_LABELS = {
            "ibm-risk-atlas": "IBM Risk Atlas",
            "owasp-llm": "OWASP LLM Top 10",
            "nist-ai-rmf": "NIST AI RMF",
            "air-2024": "AIR 2024",
            "mit-ai-risk": "MIT AI Risk Repository",
            "ailuminate": "AILuminate",
            "credo": "Credo",
            "aiuc": "AIUC-1",
            "csiro": "CSIRO",
        }
        for profile in state.domain_context:
            if state.risk_details:
                details = state.risk_details.get(profile.risk_id, {})
                profile.risk_description = details.get("description") or ""
                profile.risk_concern = details.get("concern") or ""
                taxonomy_id = details.get("taxonomy", "")
                profile.risk_framework = taxonomy_id
                for prefix, label in FRAMEWORK_LABELS.items():
                    if profile.risk_id.startswith(prefix):
                        profile.risk_framework = label
                        break
            if state.related_risks:
                profile.cross_mappings = state.related_risks.get(profile.risk_id, [])

        # Validate cross-mapping targets against all risk IDs shown to the model
        valid_ids = state.seen_risk_ids
        taxonomy, profiles = structure(
            client_slug, state.classifications, state.risk_mappings, state.domain_context,
            related_risks=state.related_risks,
            valid_risk_ids=valid_ids,
            report=report,
        )
        report.stages_completed.append("structure")

        tax_path = out / f"{client_slug}-taxonomy.yaml"
        tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
        typer.echo(f"Taxonomy written to {tax_path}")

        prof_path = out / f"{client_slug}-domain-context.yaml"
        prof_path.write_text(yaml.dump(profiles, default_flow_style=False, sort_keys=False))
        typer.echo(f"Domain context written to {prof_path}")

        report_path = out / f"{client_slug}-report.yaml"
        report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
        typer.echo(f"Report written to {report_path}")
    else:
        # Partial run — dump intermediate state as JSON
        state_path = out / f"{client_slug}-state.json"
        state_data = {
            "policies": [p.model_dump() for p in state.policies],
        }
        if state.classifications:
            state_data["classifications"] = [c.model_dump() for c in state.classifications]
        if state.selected_domains:
            state_data["selected_domains"] = state.selected_domains
        if state.risk_mappings:
            state_data["risk_mappings"] = [m.model_dump() for m in state.risk_mappings]
        if state.risk_details:
            state_data["risk_details"] = state.risk_details
        if state.variation_axes:
            state_data["variation_axes"] = [a.model_dump() for a in state.variation_axes]
        state_path.write_text(json.dumps(state_data, indent=2))
        typer.echo(f"Intermediate state written to {state_path}")

        if report.events:
            report_path = out / f"{client_slug}-report.yaml"
            report_path.write_text(yaml.dump(report.to_dict(), default_flow_style=False, sort_keys=False))
            typer.echo(f"Report written to {report_path}")


@app.command()
def emit(
    output_dir: Path = typer.Argument(..., help="Directory from a prior 'refiner run --output'"),
    policies: Path = typer.Option(..., "--policies", help="Original policy JSON file"),
    samples_per_risk: int = typer.Option(10, "--samples-per-risk", help="Samples per risk (default: 10)"),
    seed: int = typer.Option(None, "--seed", help="Random seed for reproducible sampling"),
    output: Path = typer.Option(None, "--output", "-o", help="Output JSONL path (default: <output-dir>/dataset.jsonl)"),
):
    """Emit an sdg_hub-ready JSONL dataset from domain context profiles."""
    if not output_dir.is_dir():
        typer.echo(f"Error: {output_dir} is not a directory", err=True)
        raise typer.Exit(1)
    if not policies.exists():
        typer.echo(f"Error: {policies} does not exist", err=True)
        raise typer.Exit(1)

    out_path = output or (output_dir / "dataset.jsonl")

    from refiner.emit import emit as do_emit
    do_emit(output_dir, policies, samples_per_risk, out_path, seed=seed)
    typer.echo(f"Dataset written to {out_path}")


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
        from refiner.judge import judge_prompt as jp, aggregate_judge_results
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

        evaluation["judge_evaluation"] = {
            "model": j_model,
            "prompts_scored": len(scores),
            "aggregates": aggregate_judge_results(scores),
            "by_policy_concept": {
                pc: aggregate_judge_results(pc_scores)
                for pc, pc_scores in sorted(scores_by_policy.items())
            },
        }

    summary = format_summary(evaluation)
    typer.echo(summary)

    out_path = output
    if out_path is None:
        slug = evaluation.get("run", {}).get("policy_set", "eval").replace(".json", "")
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
        )
        if not existing_run_id:
            write_run_id(output_dir, run_id)
        typer.echo(f"Logged to MLflow: run {run_id}")


if __name__ == "__main__":
    app()
