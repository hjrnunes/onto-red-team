import json
from pathlib import Path

import yaml

from refiner.artifact_reports import (
    build_risk_landscape_report,
    build_domain_context_report,
    build_taxonomy_report,
    build_run_report_html,
    build_dataset_report,
)


def test_build_risk_landscape_report(tmp_path):
    data = {
        "version": "0.1",
        "model": "test-model",
        "run_slug": "swb",
        "selected_domains": ["CCO", "FIBO"],
        "risks": [
            {"risk_id": "atlas-r1", "risk_name": "R1", "risk_framework": "IBM Risk Atlas",
             "cross_mappings": [{"id": "nist-r1", "mapping_type": "broad"}],
             "related_actions": ["action1"]},
        ],
        "policy_mappings": [
            {"policy_concept": "Fraud", "matched_risks": [
                {"risk_id": "atlas-r1", "risk_name": "R1", "relevance": "primary",
                 "justification": "j", "match_distance": 0.3}
            ]},
        ],
        "framework_coverage": {"IBM Risk Atlas": 1},
        "weak_matches": [],
    }
    out = tmp_path / "swb-risk-landscape.html"
    build_risk_landscape_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Risk Landscape" in html
    assert "__REPORT_DATA__" not in html
    assert "atlas-r1" in html or "REPORT_DATA" not in html


def test_build_domain_context_report(tmp_path):
    data = {
        "version": "0.1",
        "model": "test-model",
        "run_slug": "swb",
        "selected_domains": ["CCO"],
        "risks": [
            {"risk_id": "atlas-r1", "risk_name": "R1", "risk_framework": "IBM Risk Atlas",
             "cross_mappings": []},
        ],
        "policy_contexts": [
            {"policy_concept": "Fraud", "risk_groundings": [
                {"risk_id": "atlas-r1", "axes": [
                    {"cco_class_label": "Person", "cco_class_uri": "http://ex/Person",
                     "bfo_category": "Object", "roles": ["agent"],
                     "enumerations": [
                         {"class_label": "Employee", "source_ontology": "CCO",
                          "relevance": "high", "provenance": "subclass"},
                     ]},
                ]},
            ]},
        ],
    }
    out = tmp_path / "swb-domain-context.html"
    build_domain_context_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Domain Context" in html
    assert "__REPORT_DATA__" not in html


def test_build_taxonomy_report(tmp_path):
    data = {
        "taxonomies": [{"id": "client-swb", "name": "Client SWB", "type": "RiskTaxonomy"}],
        "groups": [{"id": "g1", "name": "Fraud", "type": "RiskGroup", "isDefinedByTaxonomy": "client-swb"}],
        "entries": [
            {"id": "e1", "name": "Risk One", "type": "Risk", "isDefinedByTaxonomy": "client-swb",
             "broad_mappings": ["nist-r1"],
             "domain_context_summary": {"axis_count": 2, "enumeration_count": 5}},
        ],
        "curie_map": {"airo": "https://w3id.org/airo#"},
    }
    out = tmp_path / "swb-taxonomy.html"
    build_taxonomy_report(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Taxonomy" in html
    assert "__REPORT_DATA__" not in html


def test_build_run_report_html(tmp_path):
    data = {
        "model": "gemma-3-12b-it",
        "policy_set": "swb-policy-document.json",
        "timestamp": "2026-04-14T20:00:00Z",
        "stages_completed": ["identify_domains", "map_risks", "anchor", "contextualize", "structure"],
        "events": [
            {"stage": "map_risks", "event": "match_count", "policy_concept": "Fraud", "count": 3},
            {"stage": "map_risks", "event": "weak_match", "risk_id": "atlas-r1", "distance": 0.72},
        ],
        "token_usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500, "calls": 10},
    }
    out = tmp_path / "swb-run-report.html"
    build_run_report_html(data, out)
    assert out.exists()
    html = out.read_text()
    assert "Run Report" in html
    assert "__REPORT_DATA__" not in html


def test_build_dataset_report(tmp_path):
    rows = [
        {"policy_concept": "Fraud", "risk_id": "atlas-r1", "risk_name": "R1",
         "technique": "pretexting", "risk_framework": "IBM Risk Atlas",
         "sampled_axes": [
             {"cco_class_label": "Person", "sampled_label": "Employee",
              "source_ontology": "CCO", "relevance": "high", "roles": ["agent"]},
         ]},
        {"policy_concept": "Fraud", "risk_id": "atlas-r1", "risk_name": "R1",
         "technique": "analytical_reframing", "risk_framework": "IBM Risk Atlas",
         "sampled_axes": [
             {"cco_class_label": "Person", "sampled_label": "Manager",
              "source_ontology": "CCO", "relevance": "medium", "roles": ["agent"]},
         ]},
    ]
    out = tmp_path / "swb-dataset.html"
    build_dataset_report(rows, out)
    assert out.exists()
    html = out.read_text()
    assert "Dataset" in html
    assert "__REPORT_DATA__" not in html
