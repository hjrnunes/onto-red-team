"""Evaluation metrics for the refiner pipeline."""

import math
import re
from collections import defaultdict


def aggregate_stage_quality(events: list[dict]) -> dict:
    """Aggregate raw pipeline events into per-stage quality summaries."""
    if not events:
        return {}

    result = {}
    for event in events:
        stage = event["stage"]
        etype = event["event"]

        if stage not in result:
            result[stage] = {}
        s = result[stage]

        if etype == "type_distribution":
            s["type_distribution"] = event["distribution"]
        elif etype == "selected_domains":
            s["selected_domains"] = event["domains"]
        elif etype == "invalid_domain_key":
            s["invalid_domain_keys"] = s.get("invalid_domain_keys", 0) + 1
        elif etype == "weak_match":
            s.setdefault("weak_matches", []).append(
                {"risk_id": event["risk_id"], "distance": event["distance"]}
            )
        elif etype == "invalid_risk_index":
            s["invalid_risk_indices"] = s.get("invalid_risk_indices", 0) + 1
        elif etype == "match_count":
            s.setdefault("match_counts", []).append(
                {"policy_concept": event["policy_concept"], "count": event["count"]}
            )
        elif etype == "domain_filtered":
            existing = s.get("domain_filtered", {"total_filtered": 0, "total_kept": 0})
            existing["total_filtered"] += event["filtered_count"]
            existing["total_kept"] += event["kept_count"]
            s["domain_filtered"] = existing
        elif etype == "cache_hit":
            s["cache_hits"] = s.get("cache_hits", 0) + 1
        elif etype == "empty_axes":
            s["empty_axes"] = s.get("empty_axes", 0) + 1
        elif etype == "role_derivation":
            rd = s.setdefault("role_derivation", {"derived": 0, "llm_fallback": 0})
            rd[event["method"]] += 1
        elif etype == "sibling_fallback":
            s["sibling_fallbacks"] = s.get("sibling_fallbacks", 0) + 1
        elif etype == "empty_enumerations":
            s["empty_enumerations"] = s.get("empty_enumerations", 0) + 1
        elif etype == "self_reference_filtered":
            s["self_references_filtered"] = s.get("self_references_filtered", 0) + 1
        elif etype == "cross_mapping_filtered":
            s["cross_mappings_filtered"] = s.get("cross_mappings_filtered", 0) + 1

    return result


def compute_risk_framework_coverage(matched_risk_ids: list[str]) -> dict:
    KNOWN_PREFIXES = {
        "ibm-risk-atlas": "ibm_risk_atlas",
        "owasp-llm": "owasp_llm_top10",
        "nist-ai-rmf": "nist_ai_rmf",
        "air-2024": "air_2024",
        "mit-ai-risk": "mit_ai_risk_repository",
        "ailuminate": "ailuminate",
        "credo": "credo",
        "aiuc": "aiuc1",
        "csiro": "csiro",
    }
    by_framework: dict[str, int] = defaultdict(int)
    for rid in matched_risk_ids:
        matched_prefix = None
        for prefix, framework in KNOWN_PREFIXES.items():
            if rid.startswith(prefix):
                matched_prefix = framework
                break
        if matched_prefix:
            by_framework[matched_prefix] += 1
        else:
            by_framework["unknown"] += 1
    return {
        "total_matched": len(matched_risk_ids),
        "by_framework": dict(by_framework),
    }


def compute_policy_coverage(
    profiles: list[dict],
    emit_data: list[dict] | None = None,
    all_policies: dict[str, str] | None = None,
) -> list[dict]:
    by_policy: dict[str, dict] = {}
    if all_policies:
        for pc in all_policies:
            by_policy[pc] = {"policy_concept": pc, "risks_matched": 0, "total_axes": 0,
                             "axes_with_enumerations": 0, "total_enumerations": 0}
    for p in profiles:
        pc = p["policy_concept"]
        if pc not in by_policy:
            by_policy[pc] = {"policy_concept": pc, "risks_matched": 0, "total_axes": 0,
                             "axes_with_enumerations": 0, "total_enumerations": 0}
        entry = by_policy[pc]
        entry["risks_matched"] += 1
        for axis in p.get("axes", []):
            entry["total_axes"] += 1
            enums = axis.get("enumerations", [])
            entry["total_enumerations"] += len(enums)
            if enums:
                entry["axes_with_enumerations"] += 1
    if emit_data:
        prompt_counts: dict[str, int] = defaultdict(int)
        for row in emit_data:
            prompt_counts[row["policy_concept"]] += 1
        for entry in by_policy.values():
            entry["prompts_generated"] = prompt_counts.get(entry["policy_concept"], 0)
    return list(by_policy.values())


def compute_ontological_coverage(profiles: list[dict]) -> dict:
    axis_uris: set[str] = set()
    enum_uris: set[str] = set()
    by_ontology: dict[str, dict] = {}
    for p in profiles:
        for axis in p.get("axes", []):
            axis_uris.add(axis["cco_class_uri"])
            for enum in axis.get("enumerations", []):
                enum_uris.add(enum["class_uri"])
                ont = enum.get("source_ontology", "unknown")
                if ont not in by_ontology:
                    by_ontology[ont] = {"unique_classes": set(), "axes_using": set()}
                by_ontology[ont]["unique_classes"].add(enum["class_uri"])
                by_ontology[ont]["axes_using"].add(axis["cco_class_uri"])
    return {
        "unique_axis_classes": len(axis_uris),
        "unique_enumeration_uris": len(enum_uris),
        "by_source_ontology": {
            ont: {"unique_classes": len(data["unique_classes"]), "axes_using": len(data["axes_using"])}
            for ont, data in sorted(by_ontology.items())
        },
    }


MAPPING_TYPES = ("exact", "close", "broad", "narrow", "related")


def compute_cross_mapping_coverage(taxonomy: dict, filtered_count: int = 0) -> dict:
    with_mappings = 0
    without_mappings = 0
    total_used = 0
    by_type: dict[str, int] = {t: 0 for t in MAPPING_TYPES}
    for entry in taxonomy.get("entries", []):
        has_any = False
        for mt in MAPPING_TYPES:
            key = f"{mt}_mappings"
            mappings = entry.get(key, [])
            count = len(mappings)
            by_type[mt] += count
            total_used += count
            if count > 0:
                has_any = True
        if has_any:
            with_mappings += 1
        else:
            without_mappings += 1
    return {
        "risks_with_cross_mappings": with_mappings,
        "risks_without": without_mappings,
        "total_cross_mappings_used": total_used,
        "filtered_unknown_targets": filtered_count,
        "by_mapping_type": by_type,
    }


RED_FLAG_PATTERNS = [
    r"\bhypothetically\b", r"\bin theory\b", r"\btheoretically\b",
    r"\bfor educational purposes\b", r"\bfor research purposes\b", r"\bfor academic purposes\b",
    r"\bas a test\b", r"\bjust testing\b", r"\bthis is a test\b",
    r"\bI want to hack\b", r"\bhelp me attack\b", r"\bhow to exploit\b",
    r"\bpretend you are\b", r"\bignore previous instructions\b", r"\bjailbreak\b",
    r"\bwhat if someone wanted to\b", r"\basking for a friend\b",
]
_RED_FLAG_RE = re.compile("|".join(RED_FLAG_PATTERNS), re.IGNORECASE)


def compute_generation_metrics(emit_rows: list[dict], dc_profiles: list[dict]) -> dict:
    role_counts: dict[str, int] = defaultdict(int)
    relevance_counts: dict[str, int] = defaultdict(int)
    diversity_data: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    samples_per_risk: dict[str, int] = defaultdict(int)

    for row in emit_rows:
        risk_id = row["risk_id"]
        samples_per_risk[risk_id] += 1
        for sa in row.get("sampled_axes", []):
            for role in sa.get("roles", []):
                role_counts[role] += 1
            relevance_counts[sa.get("relevance", "unknown")] += 1
            diversity_data[risk_id][sa.get("cco_class_uri", "")].add(sa.get("sampled_uri", ""))

    enum_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for p in dc_profiles:
        for axis in p.get("axes", []):
            enum_counts[p["risk_id"]][axis["cco_class_uri"]] = len(axis.get("enumerations", []))

    diversity_per_risk = {}
    for risk_id, axes in diversity_data.items():
        axis_diversities = []
        for axis_uri, sampled_set in axes.items():
            total_enums = enum_counts.get(risk_id, {}).get(axis_uri, len(sampled_set))
            if total_enums > 0:
                axis_diversities.append(len(sampled_set) / total_enums)
        if axis_diversities:
            diversity_per_risk[risk_id] = sum(axis_diversities) / len(axis_diversities)

    overall_diversity = (
        sum(diversity_per_risk.values()) / len(diversity_per_risk)
        if diversity_per_risk else 0
    )

    dedup_per_risk = {}
    for p in dc_profiles:
        axes = p.get("axes", [])
        usable = [a for a in axes if a.get("enumerations")]
        if usable:
            space = math.prod(len(a["enumerations"]) for a in usable)
            n_samples = samples_per_risk.get(p["risk_id"], 0)
            dedup_per_risk[p["risk_id"]] = {
                "combinatorial_space": space,
                "samples": n_samples,
                "saturation": n_samples / space if space > 0 else 0,
            }

    return {
        "axis_diversity": {"per_risk": diversity_per_risk, "overall_mean": round(overall_diversity, 3)},
        "role_distribution": dict(role_counts),
        "relevance_distribution": dict(relevance_counts),
        "dedup_saturation": dedup_per_risk,
    }


def compute_adversarial_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {
            "lexical_diversity": 0, "mean_prompt_length": 0,
            "domain_term_hit_rate": 0, "red_flag_count": 0, "per_policy": [],
        }

    all_tokens = []
    prompt_lengths = []
    term_hits = 0
    term_total = 0
    red_flag_count = 0
    per_policy: dict[str, int] = defaultdict(int)

    for row in rows:
        prompt = row.get("prompt", "")
        tokens = prompt.lower().split()
        all_tokens.extend(tokens)
        prompt_lengths.append(len(tokens))
        per_policy[row.get("policy_concept", "unknown")] += 1
        if _RED_FLAG_RE.search(prompt):
            red_flag_count += 1
        prompt_lower = prompt.lower()
        for sa in row.get("sampled_axes", []):
            label = sa.get("sampled_label", "")
            if label:
                term_total += 1
                if label.lower() in prompt_lower:
                    term_hits += 1

    ttr = len(set(all_tokens)) / len(all_tokens) if all_tokens else 0

    return {
        "lexical_diversity": round(ttr, 3),
        "mean_prompt_length": round(sum(prompt_lengths) / len(prompt_lengths), 1),
        "domain_term_hit_rate": round(term_hits / term_total, 3) if term_total > 0 else 0,
        "red_flag_count": red_flag_count,
        "per_policy": [{"policy_concept": pc, "count": c} for pc, c in sorted(per_policy.items())],
    }
