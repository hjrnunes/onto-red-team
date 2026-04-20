import json
from pathlib import Path
import typer
from ontoquery.graph import find_ontology_files
from ontoquery.backend import create_index_backend, load_backend
from ontoquery.index import OntologyIndex

app = typer.Typer()


@app.command()
def index(
    directories: list[Path] = typer.Argument(..., help="Directories or files containing ontology data"),
    chroma_dir: Path = typer.Option(Path(".chroma"), "--chroma-dir", envvar="ONTOQUERY_CHROMA_DIR", help="ChromaDB directory"),
):
    """Index all ontology files from one or more directories (or individual files) into ChromaDB."""
    for d in directories:
        if not d.exists():
            typer.echo(f"Error: path {d} does not exist", err=True)
            raise typer.Exit(1)

    files = []
    for d in directories:
        files.extend(find_ontology_files(d))
    typer.echo(f"Found {len(files)} ontology files across {len(directories)} source path{'s' if len(directories) != 1 else ''}")

    chroma = chroma_dir
    chroma.mkdir(parents=True, exist_ok=True)

    # Parse all files into a backend (persists graph for runtime queries)
    backend = create_index_backend(files, chroma)

    # Extract classes and index into ChromaDB
    all_classes = {c["uri"]: c for c in backend.extract_classes()}
    classes = list(all_classes.values())

    # Project ontology structure for context-augmented embeddings
    from ontoquery.owl2vec import project_ontology
    from ontoquery.index import build_structural_context
    from ontoquery.bfo import classify_bfo_categories
    projected = project_ontology(backend, bidirectional_taxonomy=True, include_literals=True)

    bfo_categories = classify_bfo_categories(projected)
    typer.echo(f"Classified {len(bfo_categories)} classes into BFO categories")

    structural_context = build_structural_context(projected, bfo_categories=bfo_categories)
    typer.echo(
        f"Projected {projected.edge_count()} structural + "
        f"{projected.literal_edge_count()} literal edges, "
        f"context for {len(structural_context)} classes"
    )

    source_dirs = [str(d.resolve()) for d in directories]
    idx = OntologyIndex(chroma)
    idx.index_classes(classes, source_dir=json.dumps(source_dirs), structural_context=structural_context)

    # Per-domain collections for domain-aware search
    domain_counts = idx.index_domain_classes(classes, source_dir=json.dumps(source_dirs), structural_context=structural_context)

    typer.echo(f"{len(files)} files parsed, {len(classes)} classes indexed")
    for domain, count in sorted(domain_counts.items()):
        typer.echo(f"  {domain}: {count} classes")

    # Report axiom index stats
    from ontoquery.axioms import load_axioms
    axioms = load_axioms(chroma / "axioms.json")
    if axioms:
        n_restrictions = sum(len(v) for v in axioms["restrictions"].values())
        n_disjoint = sum(len(v) for v in axioms["disjointness"].values()) // 2
        n_equivalences = sum(len(v) for v in axioms["equivalences"].values())
        typer.echo(f"Axiom index: {n_restrictions} restrictions, {n_disjoint} disjoint pairs, {n_equivalences} equivalences")

    # Save BFO categories sidecar for downstream consumers
    sidecar_path = chroma / "bfo_categories.json"
    sidecar_path.write_text(json.dumps(bfo_categories))
    typer.echo(f"BFO categories sidecar saved to {sidecar_path}")


@app.command()
def search(
        concept: str = typer.Argument(..., help="Concept name"),
        description: str = typer.Argument(..., help="Concept description"),
        top_k: int = typer.Option(10, "--top-k", help="Number of results to return"),
        chroma_dir: Path = typer.Option(Path(".chroma"), "--chroma-dir", envvar="ONTOQUERY_CHROMA_DIR", help="ChromaDB directory"),
):
    """Search indexed ontology classes for a policy concept."""
    try:
        idx = OntologyIndex(chroma_dir)
        results = idx.search(concept, description, top_k=top_k)
    except (ValueError, Exception) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(results, indent=2))


@app.command()
def navigate(
        class_uri: str = typer.Argument(..., help="Ontology class URI"),
        direction: str = typer.Option("both", "--direction", help="up, down, or both"),
        chroma_dir: Path = typer.Option(Path(".chroma"), "--chroma-dir", envvar="ONTOQUERY_CHROMA_DIR", help="ChromaDB directory"),
):
    """Navigate the class hierarchy for a given ontology class URI."""
    try:
        idx = OntologyIndex(chroma_dir)
        source_dir = idx.get_source_dir()
    except (ValueError, Exception) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    try:
        dirs = [Path(d) for d in json.loads(source_dir)]
    except (json.JSONDecodeError, TypeError):
        dirs = [Path(source_dir)]
    backend = load_backend(chroma_dir, source_dirs=dirs)

    if not backend.is_class(class_uri):
        typer.echo(f"Error: {class_uri} not found as owl:Class in graph", err=True)
        raise typer.Exit(1)

    label = backend.get_label(class_uri)
    result = {"uri": class_uri, "label": label}

    if direction in ("up", "both"):
        result["superclasses"] = backend.get_superclasses(class_uri)
    if direction in ("down", "both"):
        result["subclasses"] = backend.get_subclasses(class_uri)

    result["properties"] = backend.get_properties(class_uri)

    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
