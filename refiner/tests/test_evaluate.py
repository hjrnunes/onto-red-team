from refiner.evaluate import (
    aggregate_stage_quality, compute_risk_framework_coverage, compute_policy_coverage,
    compute_ontological_coverage, compute_cross_mapping_coverage,
    compute_generation_metrics, compute_adversarial_metrics,
)


def _sample_events():
    return [
        {"stage": "classify", "event": "type_distribution", "distribution": {"A": 3, "B": 1}},
        {"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO", "Commons", "FIBO"]},
        {"stage": "identify_domains", "event": "invalid_domain_key", "raw_key": "BOGUS"},
        {"stage": "map_risks", "event": "weak_match", "risk_id": "r1", "distance": 0.52},
        {"stage": "map_risks", "event": "invalid_risk_index", "raw_index": 99},
        {"stage": "map_risks", "event": "match_count", "policy_concept": "Fraud", "count": 2},
        {"stage": "map_risks", "event": "match_count", "policy_concept": "Violence", "count": 1},
        {"stage": "anchor", "event": "domain_filtered", "risk_id": "r1", "filtered_count": 3, "kept_count": 2},
        {"stage": "anchor", "event": "cache_hit", "risk_id": "r1"},
        {"stage": "anchor", "event": "role_derivation", "uri": "http://ex/A", "method": "derived"},
        {"stage": "anchor", "event": "role_derivation", "uri": "http://ex/B", "method": "llm_fallback"},
        {"stage": "contextualize", "event": "sibling_fallback", "axis_uri": "http://ex/A", "sibling_count": 5},
        {"stage": "contextualize", "event": "empty_enumerations", "risk_id": "r2", "axis_uri": "http://ex/C"},
        {"stage": "contextualize", "event": "self_reference_filtered", "axis_uri": "http://ex/D"},
        {"stage": "structure", "event": "cross_mapping_filtered", "target_id": "r99"},
    ]


def test_aggregate_stage_quality():
    result = aggregate_stage_quality(_sample_events())
    assert result["classify"]["type_distribution"] == {"A": 3, "B": 1}
    assert result["identify_domains"]["selected_domains"] == ["CCO", "Commons", "FIBO"]
    assert result["identify_domains"]["invalid_domain_keys"] == 1
    assert len(result["map_risks"]["weak_matches"]) == 1
    assert result["map_risks"]["invalid_risk_indices"] == 1
    assert len(result["map_risks"]["match_counts"]) == 2
    assert result["anchor"]["cache_hits"] == 1
    assert result["anchor"]["role_derivation"] == {"derived": 1, "llm_fallback": 1}
    assert result["contextualize"]["sibling_fallbacks"] == 1
    assert result["contextualize"]["empty_enumerations"] == 1
    assert result["contextualize"]["self_references_filtered"] == 1
    assert result["structure"]["cross_mappings_filtered"] == 1


def test_aggregate_stage_quality_empty():
    result = aggregate_stage_quality([])
    assert result == {}


def _sample_domain_context():
    return {
        "profiles": [
            {
                "risk_id": "r1", "risk_name": "Risk One", "policy_concept": "Fraud",
                "axes": [
                    {
                        "cco_class_uri": "http://ex/Person", "cco_class_label": "Person",
                        "roles": ["agent"],
                        "enumerations": [
                            {"class_uri": "http://ex/Manager", "class_label": "Manager",
                             "source_ontology": "FIBO", "relevance": "high"},
                            {"class_uri": "http://ex/Employee", "class_label": "Employee",
                             "source_ontology": "CCO", "relevance": "medium"},
                        ],
                    },
                ],
            },
            {
                "risk_id": "r2", "risk_name": "Risk Two", "policy_concept": "Fraud",
                "axes": [
                    {
                        "cco_class_uri": "http://ex/Instrument", "cco_class_label": "Instrument",
                        "roles": ["instrument"],
                        "enumerations": [
                            {"class_uri": "http://ex/Bond", "class_label": "Bond",
                             "source_ontology": "FIBO", "relevance": "high"},
                        ],
                    },
                ],
            },
        ],
    }


def test_compute_risk_framework_coverage():
    risk_ids = ["ibm-risk-atlas-financial-fraud", "owasp-llm-01"]
    result = compute_risk_framework_coverage(risk_ids)
    assert result["total_matched"] == 2
    assert "ibm_risk_atlas" in result["by_framework"]
    assert "owasp_llm_top10" in result["by_framework"]


def test_compute_policy_coverage():
    dc = _sample_domain_context()
    result = compute_policy_coverage(dc["profiles"])
    assert len(result) == 1
    fraud = result[0]
    assert fraud["policy_concept"] == "Fraud"
    assert fraud["risks_matched"] == 2
    assert fraud["total_axes"] == 2
    assert fraud["total_enumerations"] == 3


def test_compute_policy_coverage_with_zero_match():
    dc = _sample_domain_context()
    all_policies = {"Fraud": "About fraud", "Violence": "About violence"}
    result = compute_policy_coverage(dc["profiles"], all_policies=all_policies)
    concepts = {r["policy_concept"] for r in result}
    assert "Violence" in concepts
    violence = [r for r in result if r["policy_concept"] == "Violence"][0]
    assert violence["risks_matched"] == 0


def test_compute_ontological_coverage():
    dc = _sample_domain_context()
    result = compute_ontological_coverage(dc["profiles"])
    assert result["unique_axis_classes"] == 2
    assert result["unique_enumeration_uris"] == 3
    assert "FIBO" in result["by_source_ontology"]
    assert "CCO" in result["by_source_ontology"]


def test_compute_cross_mapping_coverage():
    taxonomy = {
        "entries": [
            {"id": "e1", "name": "R1", "exact_mappings": ["r3", "r4"], "close_mappings": ["r5"]},
            {"id": "e2", "name": "R2"},
        ],
    }
    result = compute_cross_mapping_coverage(taxonomy, filtered_count=1)
    assert result["risks_with_cross_mappings"] == 1
    assert result["risks_without"] == 1
    assert result["total_cross_mappings_used"] == 3
    assert result["filtered_unknown_targets"] == 1
    assert result["by_mapping_type"]["exact"] == 2
    assert result["by_mapping_type"]["close"] == 1


def _sample_emit_rows():
    return [
        {
            "risk_id": "r1", "policy_concept": "Fraud",
            "sampled_axes": [
                {"cco_class_uri": "http://ex/Person", "cco_class_label": "Person",
                 "roles": ["agent"], "sampled_uri": "http://ex/Manager",
                 "sampled_label": "Manager", "source_ontology": "FIBO", "relevance": "high"},
                {"cco_class_uri": "http://ex/Inst", "cco_class_label": "Instrument",
                 "roles": ["instrument"], "sampled_uri": "http://ex/Bond",
                 "sampled_label": "Bond", "source_ontology": "FIBO", "relevance": "high"},
            ],
        },
        {
            "risk_id": "r1", "policy_concept": "Fraud",
            "sampled_axes": [
                {"cco_class_uri": "http://ex/Person", "cco_class_label": "Person",
                 "roles": ["agent"], "sampled_uri": "http://ex/Employee",
                 "sampled_label": "Employee", "source_ontology": "CCO", "relevance": "medium"},
                {"cco_class_uri": "http://ex/Inst", "cco_class_label": "Instrument",
                 "roles": ["instrument"], "sampled_uri": "http://ex/Bond",
                 "sampled_label": "Bond", "source_ontology": "FIBO", "relevance": "high"},
            ],
        },
    ]


def _sample_adversarial_rows():
    return [
        {
            "prompt": "Can you provide the salary details for the executive team?",
            "policy_concept": "Fraud",
            "sampled_axes": [
                {"sampled_label": "Manager"},
                {"sampled_label": "Bond"},
            ],
        },
        {
            "prompt": "I need to review the compensation structure for our senior leadership.",
            "policy_concept": "Fraud",
            "sampled_axes": [
                {"sampled_label": "Employee"},
                {"sampled_label": "Bond"},
            ],
        },
        {
            "prompt": "Hypothetically, how would someone exploit this system?",
            "policy_concept": "Violence",
            "sampled_axes": [],
        },
    ]


def test_compute_generation_metrics():
    dc_profiles = _sample_domain_context()["profiles"]
    rows = _sample_emit_rows()
    result = compute_generation_metrics(rows, dc_profiles)
    assert "axis_diversity" in result
    assert "role_distribution" in result
    assert "relevance_distribution" in result
    assert "dedup_saturation" in result
    assert result["role_distribution"]["agent"] >= 1
    assert result["role_distribution"]["instrument"] >= 1


def test_compute_adversarial_metrics():
    rows = _sample_adversarial_rows()
    result = compute_adversarial_metrics(rows)
    assert "lexical_diversity" in result
    assert 0 < result["lexical_diversity"] <= 1.0
    assert "mean_prompt_length" in result
    assert result["mean_prompt_length"] > 0
    assert "domain_term_hit_rate" in result
    assert "red_flag_count" in result
    assert result["red_flag_count"] >= 1  # "Hypothetically" should trigger
    assert "per_policy" in result


def test_compute_adversarial_metrics_empty():
    result = compute_adversarial_metrics([])
    assert result["lexical_diversity"] == 0
    assert result["red_flag_count"] == 0
