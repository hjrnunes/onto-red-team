import json
import os
from pathlib import Path

import typer
import yaml

from refiner import debug
from refiner.llm import LLMConfig, create_client
from refiner.models import Policy
from refiner.pipeline import run_pipeline, STAGES
from refiner.stages.structure import structure

app = typer.Typer()


def _create_risk_handlers() -> dict:
    from nexus_mcp.server import create_tool_handlers
    from nexus_mcp.risk_index import RiskIndex
    nexus_base_dir = os.environ.get("NEXUS_BASE_DIR")
    if not nexus_base_dir:
        typer.echo("Error: NEXUS_BASE_DIR environment variable must be set", err=True)
        raise typer.Exit(1)
    from ai_atlas_nexus import AIAtlasNexus
    nexus = AIAtlasNexus(base_dir=nexus_base_dir)
    all_risks = nexus.get_all_risks()
    risks_by_id = {r.id: r for r in all_risks}
    all_actions = nexus.get_all_actions()
    actions_by_id = {a.id: a for a in all_actions}
    taxonomies = nexus.get_all_taxonomies()
    groups = nexus.get_all("groups")
    chroma_dir = Path(os.environ.get("NEXUS_CHROMA_DIR", ".chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    idx = RiskIndex(chroma_dir)
    if idx.needs_reindex(len(all_risks)):
        idx.index_risks(all_risks)
    return create_tool_handlers(
        risk_index=idx, risks_by_id=risks_by_id, actions_by_id=actions_by_id,
        taxonomies=taxonomies, groups=groups,
    )


def _create_onto_handlers() -> dict:
    from ontoquery.mcp_server import create_tool_handlers
    chroma_dir = Path(os.environ.get("ONTOQUERY_CHROMA_DIR", ".chroma"))
    return create_tool_handlers(chroma_dir)


@app.command()
def run(
    policy_json: Path = typer.Argument(..., help="Path to policy JSON file"),
    until: str = typer.Option(None, "--until", help=f"Run up to this stage: {', '.join(STAGES)}"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory (default: current dir)"),
    debug_dir: Path = typer.Option(None, "--debug", help="Directory for per-call debug logs (prompts + responses)"),
):
    """Run the refiner pipeline on a policy JSON file."""
    if not policy_json.exists():
        typer.echo(f"Error: {policy_json} does not exist", err=True)
        raise typer.Exit(1)

    if until and until not in STAGES:
        typer.echo(f"Error: --until must be one of: {', '.join(STAGES)}", err=True)
        raise typer.Exit(1)

    # Load policies
    raw = json.loads(policy_json.read_text())
    policies = [Policy(**p) for p in raw]
    typer.echo(f"Loaded {len(policies)} policies from {policy_json.name}")

    # Config from environment
    base_url = os.environ.get("REFINER_BASE_URL")
    model = os.environ.get("REFINER_MODEL")
    if not base_url or not model:
        typer.echo("Error: REFINER_BASE_URL and REFINER_MODEL must be set", err=True)
        raise typer.Exit(1)

    config = LLMConfig(base_url=base_url, model=model)
    client = create_client(config)
    debug.configure(debug_dir)

    # Create handlers — only load what's needed for the requested stages
    needs_risk = until not in ("classify", "identify_domains")
    needs_onto = until not in ("classify", "identify_domains", "map_risks")
    risk_handlers = _create_risk_handlers() if needs_risk else {}
    onto_handlers = _create_onto_handlers() if needs_onto else {}

    # Run pipeline
    typer.echo(f"Running pipeline{f' until {until}' if until else ''}...")
    state = run_pipeline(policies, client, config, risk_handlers, onto_handlers, until=until)

    # Output
    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)
    client_slug = policy_json.stem

    if state.domain_context is not None and state.classifications is not None and state.risk_mappings is not None:
        # Validate cross-mapping targets against all risk IDs shown to the model
        valid_ids = state.seen_risk_ids
        taxonomy, profiles = structure(
            client_slug, state.classifications, state.risk_mappings, state.domain_context,
            related_risks=state.related_risks,
            valid_risk_ids=valid_ids,
        )
        tax_path = out / f"{client_slug}-taxonomy.yaml"
        tax_path.write_text(yaml.dump(taxonomy, default_flow_style=False, sort_keys=False))
        typer.echo(f"Taxonomy written to {tax_path}")

        prof_path = out / f"{client_slug}-domain-context.yaml"
        prof_path.write_text(yaml.dump(profiles, default_flow_style=False, sort_keys=False))
        typer.echo(f"Domain context written to {prof_path}")
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


if __name__ == "__main__":
    app()
