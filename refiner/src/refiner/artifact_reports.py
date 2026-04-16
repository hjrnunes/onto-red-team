"""HTML report builders for pipeline artifacts."""

import json
from collections import Counter
from pathlib import Path


def _render(template_name: str, data: dict | list, output_path: Path) -> Path:
    """Load template, substitute __REPORT_DATA__, write HTML."""
    template_path = Path(__file__).parent / template_name
    html = template_path.read_text().replace(
        "__REPORT_DATA__", json.dumps(data, default=str)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path


def build_risk_landscape_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a RiskLandscape YAML artifact."""
    return _render("risk_landscape_report_template.html", data, output_path)


def build_domain_context_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a DomainContext YAML artifact."""
    return _render("domain_context_report_template.html", data, output_path)


def build_taxonomy_report(data: dict, output_path: Path) -> Path:
    """Build HTML report for a taxonomy YAML artifact."""
    return _render("taxonomy_report_template.html", data, output_path)


def build_run_report_html(data: dict, output_path: Path) -> Path:
    """Build HTML report for a run-report YAML artifact."""
    return _render("run_report_template.html", data, output_path)


def build_dataset_report(rows: list[dict], output_path: Path) -> Path:
    """Build HTML report for a dataset JSONL artifact.

    Computes summary statistics from the rows and embeds both
    the stats and the full row data into the template.
    """
    policies = Counter(r.get("policy_concept", "") for r in rows)
    techniques = Counter(r.get("technique", "") for r in rows)
    risks = Counter(r.get("risk_id", "") for r in rows)
    frameworks = Counter(r.get("risk_framework", "") for r in rows)

    all_axes = []
    for r in rows:
        for ax in r.get("sampled_axes", []):
            all_axes.append(ax)
    relevance = Counter(ax.get("relevance", "") for ax in all_axes)

    report_data = {
        "summary": {
            "total_rows": len(rows),
            "policies": dict(policies.most_common()),
            "techniques": dict(techniques.most_common()),
            "risks": dict(risks.most_common()),
            "frameworks": dict(frameworks.most_common()),
            "relevance": dict(relevance.most_common()),
        },
        "rows": rows,
    }
    return _render("dataset_report_template.html", report_data, output_path)
