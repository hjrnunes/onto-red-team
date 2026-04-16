"""Evaluation metrics for the refiner pipeline."""

import json
import math
import re
from collections import defaultdict
from pathlib import Path

import yaml


def _flatten_to_profiles(dc_data: dict) -> list[dict]:
    """Flatten DomainContext dict into profile-like dicts for metrics."""
    risk_by_id = {r["risk_id"]: r for r in dc_data.get("risks", [])}
    profiles = []
    for pc in dc_data.get("policy_contexts", []):
        for rg in pc.get("risk_groundings", []):
            risk = risk_by_id.get(rg.get("risk_id", ""), {})
            profiles.append({
                "risk_id": rg.get("risk_id", ""),
                "risk_name": risk.get("risk_name", ""),
                "policy_concept": pc.get("policy_concept", ""),
                "axes": rg.get("axes", []),
                "risk_description": risk.get("risk_description", ""),
                "risk_concern": risk.get("risk_concern", ""),
                "risk_framework": risk.get("risk_framework", ""),
                "cross_mappings": risk.get("cross_mappings", []),
            })
    return profiles


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

        if etype == "selected_domains":
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
        elif etype == "candidate_expansion":
            expansions = s.setdefault("candidate_expansions", [])
            expansions.append({
                "risk_id": event["risk_id"],
                "queries_run": event["queries_run"],
                "raw_total": event["raw_total"],
                "unique_after_dedup": event["unique_after_dedup"],
                "kept_after_filter": event["kept_after_filter"],
            })
        elif etype == "multi_query_hit":
            hits = s.setdefault("multi_query_hits", [])
            hits.append({
                "risk_id": event["risk_id"],
                "uri": event["uri"],
                "hit_count": event["hit_count"],
                "best_distance": event["best_distance"],
                "query_sources": event["query_sources"],
            })
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
        elif etype == "disjoint_filtered":
            s.setdefault("disjoint_filtered", []).append({
                "risk_id": event["risk_id"],
                "axis_uri": event["axis_uri"],
                "kept": event["kept"],
                "filtered": event["filtered"],
            })
        elif etype == "restriction_expansion":
            s.setdefault("restriction_expansions", []).append({
                "risk_id": event["risk_id"],
                "source_uri": event["source_uri"],
                "candidates_added": event["candidates_added"],
                "source_type": event["source_type"],
            })
        elif etype == "restriction_context_added":
            s["restriction_contexts_added"] = s.get("restriction_contexts_added", 0) + 1
        elif etype == "variations_generated":
            s["variations_generated"] = s.get("variations_generated", 0) + event.get("count", 0)

    return result


def compute_risk_framework_coverage(matched_risk_ids: list[str]) -> dict:
    KNOWN_PREFIXES = {
        "atlas-": "ibm_risk_atlas",
        "owasp-": "owasp_llm_top10",
        "llm0": "owasp_llm_top10",
        "nist-": "nist_ai_rmf",
        "ai-risk-taxonomy-": "air_2024",
        "air-": "air_2024",
        "mit-ai-risk": "mit_ai_risk_repository",
        "ail-": "ailuminate",
        "credo-": "credo",
        "aiuc-": "aiuc1",
        "csiro-": "csiro",
        "shieldgemma-": "shieldgemma",
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


HARD_RED_FLAG_PATTERNS = [
    r"\bI want to hack\b", r"\bhelp me attack\b", r"\bhow to exploit\b",
    r"\bpretend you are\b", r"\bignore previous instructions\b", r"\bjailbreak\b",
    r"\bwhat if someone wanted to\b", r"\basking for a friend\b",
]

SOFT_RED_FLAG_PATTERNS = [
    r"\bhypothetically\b", r"\bin theory\b", r"\btheoretically\b",
    r"\bfor educational purposes\b", r"\bfor research purposes\b", r"\bfor academic purposes\b",
    r"\bas a test\b", r"\bjust testing\b", r"\bthis is a test\b",
]

# Combined for backward compat
RED_FLAG_PATTERNS = HARD_RED_FLAG_PATTERNS + SOFT_RED_FLAG_PATTERNS
_RED_FLAG_RE = re.compile("|".join(RED_FLAG_PATTERNS), re.IGNORECASE)
_HARD_RED_FLAG_RE = re.compile("|".join(HARD_RED_FLAG_PATTERNS), re.IGNORECASE)
_SOFT_RED_FLAG_RE = re.compile("|".join(SOFT_RED_FLAG_PATTERNS), re.IGNORECASE)


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

    technique_counts: dict[str, int] = defaultdict(int)
    for row in emit_rows:
        technique_counts[row.get("technique", "pretexting")] += 1

    return {
        "axis_diversity": {"per_risk": diversity_per_risk, "overall_mean": round(overall_diversity, 3)},
        "role_distribution": dict(role_counts),
        "relevance_distribution": dict(relevance_counts),
        "technique_distribution": dict(technique_counts),
        "dedup_saturation": dedup_per_risk,
    }


def compute_technique_diversity(rows: list[dict]) -> dict:
    """Compute technique distribution and diversity metrics."""
    technique_counts: dict[str, int] = defaultdict(int)
    per_risk: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        tech = row.get("technique", "pretexting")
        technique_counts[tech] += 1
        risk_id = row.get("risk_id", "unknown")
        per_risk[risk_id].add(tech)

    total = sum(technique_counts.values())
    if total == 0:
        return {
            "technique_counts": {},
            "technique_entropy": 0.0,
            "technique_normalized_entropy": 0.0,
            "per_risk_technique_count": {},
        }

    # Shannon entropy
    entropy = 0.0
    for count in technique_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    n_techniques = len(technique_counts)
    max_entropy = math.log2(n_techniques) if n_techniques > 1 else 1.0
    normalized = round(entropy / max_entropy, 3) if max_entropy > 0 else 0.0

    return {
        "technique_counts": dict(technique_counts),
        "technique_entropy": round(entropy, 3),
        "technique_normalized_entropy": normalized,
        "per_risk_technique_count": {
            rid: len(techs) for rid, techs in per_risk.items()
        },
    }


def compute_bfo_diversity(rows: list[dict]) -> dict:
    """Compute BFO category diversity across prompts."""
    per_prompt_counts: list[int] = []
    category_prompts: dict[str, int] = defaultdict(int)

    for row in rows:
        categories = set()
        for sa in row.get("sampled_axes", []):
            cat = sa.get("bfo_category", "")
            if cat:
                categories.add(cat)
        per_prompt_counts.append(len(categories))
        for cat in categories:
            category_prompts[cat] += 1

    mean = sum(per_prompt_counts) / len(per_prompt_counts) if per_prompt_counts else 0.0

    return {
        "per_prompt_counts": per_prompt_counts,
        "mean_distinct_categories": round(mean, 2),
        "category_distribution": dict(sorted(category_prompts.items())),
    }


def compute_single_value_axis_dominance(profiles: list[dict]) -> dict:
    total = 0
    single = 0
    for p in profiles:
        for axis in p.get("axes", []):
            total += 1
            if len(axis.get("enumerations", [])) <= 1:
                single += 1
    return {
        "total_axes": total,
        "single_value_axes": single,
        "single_value_rate": round(single / total, 3) if total > 0 else 0,
    }


def compute_enumeration_domain_mismatch(
    profiles: list[dict], selected_domains: list[str],
) -> dict:
    allowed = set(selected_domains) | {"CCO"}
    total = 0
    mismatched = 0
    by_ont: dict[str, int] = defaultdict(int)
    for p in profiles:
        for axis in p.get("axes", []):
            for enum in axis.get("enumerations", []):
                total += 1
                ont = enum.get("source_ontology", "unknown")
                if ont not in allowed:
                    mismatched += 1
                    by_ont[ont] += 1
    return {
        "total_enumerations": total,
        "mismatched": mismatched,
        "mismatch_rate": round(mismatched / total, 3) if total > 0 else 0,
        "by_mismatched_ontology": dict(by_ont),
    }


def compute_policy_coverage_balance(per_policy: list[dict]) -> dict:
    counts = [p["count"] for p in per_policy if p.get("count", 0) > 0]
    if len(counts) <= 1:
        return {"entropy": 0, "normalized_entropy": 0}
    total = sum(counts)
    entropy = -sum((c / total) * math.log2(c / total) for c in counts)
    max_entropy = math.log2(len(counts))
    return {
        "entropy": round(entropy, 3),
        "normalized_entropy": round(entropy / max_entropy, 3) if max_entropy > 0 else 0,
    }


def compute_enumeration_concentration(
    rows: list[dict], top_k: int = 5,
) -> dict:
    uri_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for sa in row.get("sampled_axes", []):
            uri = sa.get("sampled_uri", "")
            if uri:
                uri_counts[uri] += 1
    total = sum(uri_counts.values())
    if total == 0:
        return {"total_samples": 0, "top_k": top_k, "top_k_share": 0, "top_values": []}
    sorted_uris = sorted(uri_counts.items(), key=lambda x: x[1], reverse=True)
    top = sorted_uris[:top_k]
    top_sum = sum(c for _, c in top)
    return {
        "total_samples": total,
        "top_k": top_k,
        "top_k_share": round(top_sum / total, 3),
        "top_values": [{"uri": uri, "count": c} for uri, c in top],
    }


JARGON_PATTERNS = [
    r"\bAct of [A-Z]\w+\b",
    r"\b\w+ Artifact Function\b",
    r"\b[A-Z][a-z]+(?:[A-Z][a-z]+){2,}\b",  # CamelCase with 3+ parts
    r"\bAE\b(?!\s+suffix)",  # bare "AE" from OBO
    r" - ATLAS\b",  # D3FEND ATLAS framework suffix
    r" - ATTACK\b",  # D3FEND ATT&CK framework suffix
    r" - SPARTA\b",  # D3FEND SPARTA framework suffix
    r"\bD3FEND\b",  # D3FEND literal
    r"\bATLAS\b(?! [a-z])",  # bare ATLAS not followed by lowercase (natural text)
]
_JARGON_RE = re.compile("|".join(JARGON_PATTERNS))


def compute_jargon_leak_rate(rows: list[dict]) -> dict:
    if not rows:
        return {"total_prompts": 0, "jargon_prompts": 0, "jargon_rate": 0}
    jargon_count = 0
    for row in rows:
        prompt = row.get("prompt") or ""
        if _JARGON_RE.search(prompt):
            jargon_count += 1
    return {
        "total_prompts": len(rows),
        "jargon_prompts": jargon_count,
        "jargon_rate": round(jargon_count / len(rows), 3),
    }


_AXIS_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is", "by",
    "act", "function",  # too generic in ontology labels
})


def _axis_words(label: str) -> set[str]:
    return {w.lower() for w in label.split() if len(w) > 2 and w.lower() not in _AXIS_STOPWORDS}


def compute_axis_fidelity(rows: list[dict]) -> dict:
    full = 0
    partial = 0
    improvised = 0
    fidelities = []
    for row in rows:
        axes = row.get("sampled_axes", [])
        if not axes:
            continue
        matched = 0
        for sa in axes:
            label = sa.get("sampled_label", "")
            words = _axis_words(label)
            if not words:
                matched += 1
                continue
            prompt_lower = (row.get("prompt") or "").lower()
            if any(w in prompt_lower for w in words):
                matched += 1
        fidelity = matched / len(axes)
        fidelities.append(fidelity)
        if fidelity == 1.0:
            full += 1
        elif fidelity == 0:
            improvised += 1
        else:
            partial += 1
    return {
        "total_prompts": len(fidelities),
        "full_fidelity": full,
        "partial": partial,
        "improvised": improvised,
        "mean_fidelity": round(sum(fidelities) / len(fidelities), 3) if fidelities else 0,
    }


_NAMED_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_CAMELCASE_RE = re.compile(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]*\b")
_COMMON_PHRASES = frozenset({
    "The", "This", "These", "Those", "That", "Also", "Include",
})


def _extract_named_entities(text: str) -> set[str]:
    entities = set()
    for m in _NAMED_ENTITY_RE.finditer(text):
        phrase = m.group()
        words = phrase.split()
        if words[0] not in _COMMON_PHRASES:
            entities.add(phrase)
    for m in _CAMELCASE_RE.finditer(text):
        entities.add(m.group())
    return entities


def compute_named_entity_utilization(
    rows: list[dict], policies: dict[str, str],
) -> dict:
    if not rows:
        return {"total_prompts": 0, "prompts_with_entities": 0, "utilization_rate": 0}
    entities_by_policy: dict[str, set[str]] = {}
    for pc, defn in policies.items():
        entities_by_policy[pc] = _extract_named_entities(defn)
    hits = 0
    for row in rows:
        pc = row.get("policy_concept", "")
        entities = entities_by_policy.get(pc, set())
        if not entities:
            continue
        prompt_lower = (row.get("prompt") or "").lower()
        if any(e.lower() in prompt_lower for e in entities):
            hits += 1
    return {
        "total_prompts": len(rows),
        "prompts_with_entities": hits,
        "utilization_rate": round(hits / len(rows), 3),
        "entities_by_policy": {pc: sorted(ents) for pc, ents in entities_by_policy.items() if ents},
    }


def compute_weak_match_impact(
    weak_matches: list[dict], prompt_rows: list[dict],
) -> dict:
    weak_ids = {wm["risk_id"] for wm in weak_matches}
    distances = [wm["distance"] for wm in weak_matches]

    weak_prompts = [r for r in prompt_rows if r.get("risk_id") in weak_ids]
    strong_prompts = [r for r in prompt_rows if r.get("risk_id") not in weak_ids]

    result: dict = {
        "weak_match_risks": len(weak_ids),
        "weak_match_prompts": len(weak_prompts),
        "strong_match_prompts": len(strong_prompts),
        "mean_weak_distance": round(sum(distances) / len(distances), 3) if distances else 0,
    }

    weak_scores = [r["judge_score"] for r in weak_prompts if "judge_score" in r]
    strong_scores = [r["judge_score"] for r in strong_prompts if "judge_score" in r]
    if weak_scores:
        result["weak_match_mean_score"] = round(sum(weak_scores) / len(weak_scores), 3)
    if strong_scores:
        result["strong_match_mean_score"] = round(sum(strong_scores) / len(strong_scores), 3)

    return result


def _tfidf_vectors(docs: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    df: dict[str, int] = defaultdict(int)
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    n = len(docs)
    idf = {term: math.log(n / count) for term, count in df.items() if count < n}
    vectors = []
    for doc in docs:
        tf: dict[str, int] = defaultdict(int)
        for term in doc:
            tf[term] += 1
        vec = {}
        for term, count in tf.items():
            if term in idf:
                vec[term] = count * idf[term]
        vectors.append(vec)
    return vectors, idf


def _cosine_distance(a: dict[str, float], b: dict[str, float]) -> float:
    if not a and not b:
        return 0.0  # both empty = identical (no distinguishing features)
    keys = set(a) & set(b)
    if not keys:
        return 1.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 1.0
    return 1.0 - (dot / (mag_a * mag_b))


def compute_semantic_diversity(rows: list[dict], max_pairs: int = 5000) -> dict:
    if len(rows) <= 1:
        return {"mean_pairwise_distance": 0, "total_prompts": len(rows)}

    docs = [(row.get("prompt") or "").lower().split() for row in rows]
    vectors, _ = _tfidf_vectors(docs)

    # Compute pairwise distances (sample if too many pairs)
    import random
    n = len(vectors)
    total_pairs = n * (n - 1) // 2
    if total_pairs <= max_pairs:
        distances = []
        for i in range(n):
            for j in range(i + 1, n):
                distances.append(_cosine_distance(vectors[i], vectors[j]))
    else:
        distances = []
        rng = random.Random(42)
        for _ in range(max_pairs):
            i, j = rng.sample(range(n), 2)
            distances.append(_cosine_distance(vectors[i], vectors[j]))

    mean_dist = sum(distances) / len(distances) if distances else 0

    # Per-policy diversity
    by_policy: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        by_policy[row.get("policy_concept", "unknown")].append(idx)

    per_policy = {}
    for pc, indices in sorted(by_policy.items()):
        if len(indices) <= 1:
            per_policy[pc] = 0
            continue
        pc_distances = []
        for ii in range(len(indices)):
            for jj in range(ii + 1, len(indices)):
                pc_distances.append(_cosine_distance(vectors[indices[ii]], vectors[indices[jj]]))
        per_policy[pc] = round(sum(pc_distances) / len(pc_distances), 3) if pc_distances else 0

    return {
        "mean_pairwise_distance": round(mean_dist, 3),
        "total_prompts": len(rows),
        "per_policy": per_policy,
    }


def compute_similarity_edges(
    rows: list[dict],
    threshold: float = 0.5,
    max_edges: int = 500,
    max_nodes: int = 200,
) -> dict:
    """Pre-compute similarity edges between prompts for the similarity network visualization."""
    import random as _random

    prompts_with_text = [
        (i, r) for i, r in enumerate(rows) if (r.get("prompt") or "").strip()
    ]
    if len(prompts_with_text) <= 1:
        return {
            "nodes": [],
            "edges": [],
            "threshold_used": threshold,
            "total_prompts": len(rows),
            "sampled": False,
        }

    sampled = False
    if len(prompts_with_text) > max_nodes:
        sampled = True
        rng = _random.Random(42)
        by_policy: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        for item in prompts_with_text:
            by_policy[item[1].get("policy_concept", "unknown")].append(item)
        selected: list[tuple[int, dict]] = []
        per_group = max(1, max_nodes // len(by_policy))
        for pc in sorted(by_policy):
            group = by_policy[pc]
            k = min(len(group), per_group)
            selected.extend(rng.sample(group, k))
        # Fill remaining slots if under budget
        remaining = [item for item in prompts_with_text if item not in selected]
        deficit = max_nodes - len(selected)
        if deficit > 0 and remaining:
            selected.extend(rng.sample(remaining, min(deficit, len(remaining))))
        prompts_with_text = selected

    docs = [(r.get("prompt") or "").lower().split() for _, r in prompts_with_text]
    vectors, _ = _tfidf_vectors(docs)

    edges = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            sim = 1.0 - _cosine_distance(vectors[i], vectors[j])
            if sim >= threshold:
                edges.append({"source": i, "target": j, "similarity": round(sim, 3)})

    if len(edges) > max_edges:
        edges.sort(key=lambda e: e["similarity"], reverse=True)
        edges = edges[:max_edges]

    nodes = []
    for idx, (orig_index, r) in enumerate(prompts_with_text):
        nodes.append({
            "id": idx,
            "prompt_index": orig_index,
            "policy_concept": r.get("policy_concept", ""),
            "technique": r.get("technique", ""),
            "risk_name": r.get("risk_name", ""),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "threshold_used": threshold,
        "total_prompts": len(rows),
        "sampled": sampled,
    }


_RELEVANCE_SCORES = {"high": 3, "medium": 2, "low": 1}


def compute_sibling_relevance(profiles: list[dict]) -> dict:
    sub_relevance: dict[str, int] = defaultdict(int)
    sib_relevance: dict[str, int] = defaultdict(int)
    sub_scores: list[int] = []
    sib_scores: list[int] = []

    for p in profiles:
        for axis in p.get("axes", []):
            for enum in axis.get("enumerations", []):
                prov = enum.get("provenance", "subclass")
                rel = enum.get("relevance", "low")
                score = _RELEVANCE_SCORES.get(rel, 1)
                if prov == "sibling":
                    sib_relevance[rel] += 1
                    sib_scores.append(score)
                else:
                    sub_relevance[rel] += 1
                    sub_scores.append(score)

    return {
        "subclass_count": sum(sub_relevance.values()),
        "sibling_count": sum(sib_relevance.values()),
        "subclass_relevance": dict(sub_relevance),
        "sibling_relevance": dict(sib_relevance),
        "subclass_mean_score": round(sum(sub_scores) / len(sub_scores), 3) if sub_scores else 0,
        "sibling_mean_score": round(sum(sib_scores) / len(sib_scores), 3) if sib_scores else 0,
    }


def compute_adversarial_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {
            "lexical_diversity": 0, "mean_prompt_length": 0,
            "domain_term_hit_rate": 0, "red_flag_count": 0,
            "red_flag_hard": 0, "red_flag_soft": 0, "per_policy": [],
        }

    all_tokens = []
    prompt_lengths = []
    term_hits = 0
    term_total = 0
    red_flag_count = 0
    red_flag_hard = 0
    red_flag_soft = 0
    per_policy: dict[str, int] = defaultdict(int)

    for row in rows:
        prompt = row.get("prompt") or ""
        tokens = prompt.lower().split()
        all_tokens.extend(tokens)
        prompt_lengths.append(len(tokens))
        per_policy[row.get("policy_concept") or "unknown"] += 1
        has_hard = bool(_HARD_RED_FLAG_RE.search(prompt))
        has_soft = bool(_SOFT_RED_FLAG_RE.search(prompt))
        if has_hard or has_soft:
            red_flag_count += 1
        if has_hard:
            red_flag_hard += 1
        if has_soft:
            red_flag_soft += 1
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
        "red_flag_hard": red_flag_hard,
        "red_flag_soft": red_flag_soft,
        "per_policy": [{"policy_concept": pc, "count": c} for pc, c in sorted(per_policy.items())],
    }


def compute_candidate_expansion_effectiveness(events: list[dict]) -> dict:
    expansion_events = [e for e in events if e.get("event") == "candidate_expansion"]
    hit_events = [e for e in events if e.get("event") == "multi_query_hit"]

    if not expansion_events:
        return {"mean_queries_run": 0, "mean_unique_candidates": 0, "multi_hit_fraction": 0}

    mean_queries = sum(e["queries_run"] for e in expansion_events) / len(expansion_events)
    mean_unique = sum(e["unique_after_dedup"] for e in expansion_events) / len(expansion_events)

    multi_hit_count = sum(1 for e in hit_events if e.get("hit_count", 1) > 1)
    multi_hit_fraction = multi_hit_count / len(hit_events) if hit_events else 0

    return {
        "mean_queries_run": mean_queries,
        "mean_unique_candidates": mean_unique,
        "multi_hit_fraction": multi_hit_fraction,
    }


def compute_query_source_contribution(events: list[dict]) -> dict:
    hit_events = [e for e in events if e.get("event") == "multi_query_hit"]
    if not hit_events:
        return {}

    counts: dict[str, int] = {}
    for e in hit_events:
        for source in e.get("query_sources", []):
            counts[source] = counts.get(source, 0) + 1
    return counts


def compute_disjoint_filter_rate(events: list[dict], total_risks: int) -> dict:
    """Fraction of risks where disjointness filtering removed enumerations."""
    disjoint_events = [e for e in events if e.get("event") == "disjoint_filtered"]
    risk_ids = {e["risk_id"] for e in disjoint_events}
    return {
        "risks_with_disjoint_filtering": len(risk_ids),
        "total_risks": total_risks,
        "disjoint_filter_rate": round(len(risk_ids) / total_risks, 3) if total_risks > 0 else 0,
    }


def compute_restriction_discovery_rate(events: list[dict], total_risks: int) -> dict:
    """Fraction of risks where restriction/equivalence expansion added candidates."""
    expansion_events = [e for e in events if e.get("event") == "restriction_expansion"]
    risk_ids = {e["risk_id"] for e in expansion_events}
    total_added = sum(e.get("candidates_added", 0) for e in expansion_events)
    return {
        "risks_with_restriction_expansion": len(risk_ids),
        "total_risks": total_risks,
        "total_candidates_from_axioms": total_added,
        "restriction_discovery_rate": round(len(risk_ids) / total_risks, 3) if total_risks > 0 else 0,
    }


def _discover_file(output_dir: Path, pattern: str) -> Path | None:
    matches = list(output_dir.glob(pattern))
    if len(matches) > 1:
        raise SystemExit(f"Error: multiple {pattern} found in {output_dir}: {matches}")
    return matches[0] if matches else None


def run_evaluation(
    output_dir: Path,
    emit_path: Path | None = None,
    adversarial_path: Path | None = None,
    policies_path: Path | None = None,
) -> dict:
    report_path = _discover_file(output_dir, "*-run-report.yaml")
    taxonomy_path = _discover_file(output_dir, "*-taxonomy.yaml")
    dc_path = _discover_file(output_dir, "*-domain-context.yaml")

    report_data = yaml.safe_load(report_path.read_text()) if report_path else {}
    taxonomy_data = yaml.safe_load(taxonomy_path.read_text()) if taxonomy_path else {}
    dc_data = yaml.safe_load(dc_path.read_text()) if dc_path else {}

    result = {}

    result["run"] = {
        "model": report_data.get("model", "unknown"),
        "policy_set": report_data.get("policy_set", "unknown"),
        "timestamp": report_data.get("timestamp", "unknown"),
        "stages_completed": report_data.get("stages_completed", []),
    }

    events = report_data.get("events", [])
    if events:
        result["stage_quality"] = aggregate_stage_quality(events)
        result["stage_quality"]["candidate_expansion"] = compute_candidate_expansion_effectiveness(events)
        result["stage_quality"]["query_source_contribution"] = compute_query_source_contribution(events)

    all_policies = None
    if policies_path and policies_path.exists():
        raw_policies = json.loads(policies_path.read_text())
        if isinstance(raw_policies, list):
            all_policies = {p["policy_concept"]: p["concept_definition"] for p in raw_policies}
        else:
            all_policies = {
                p["policy_concept"]: p["concept_definition"]
                for p in raw_policies.get("policies", [])
            }

    profiles = _flatten_to_profiles(dc_data)
    if dc_data:
        result["envelope"] = {
            "version": dc_data.get("version", ""),
            "model": dc_data.get("model", ""),
            "selected_domains": dc_data.get("selected_domains", []),
        }
    emit_rows = None
    if emit_path and emit_path.exists():
        emit_rows = [json.loads(line) for line in emit_path.read_text().strip().split("\n") if line]

    coverage = {}
    if profiles:
        coverage["policy"] = compute_policy_coverage(profiles, emit_data=emit_rows, all_policies=all_policies)
        coverage["ontological"] = compute_ontological_coverage(profiles)
        coverage["single_value_axis_dominance"] = compute_single_value_axis_dominance(profiles)
        selected_domains = (
            result.get("stage_quality", {})
            .get("identify_domains", {})
            .get("selected_domains", [])
        )
        if selected_domains:
            coverage["enumeration_domain_mismatch"] = compute_enumeration_domain_mismatch(
                profiles, selected_domains
            )
        coverage["sibling_relevance"] = compute_sibling_relevance(profiles)
        if events:
            total_risks = len({p["risk_id"] for p in profiles})
            coverage["disjoint_filter_rate"] = compute_disjoint_filter_rate(events, total_risks)
            coverage["restriction_discovery_rate"] = compute_restriction_discovery_rate(events, total_risks)
    if taxonomy_data:
        if profiles:
            risk_ids = list({p["risk_id"] for p in profiles})
            coverage["risk_framework"] = compute_risk_framework_coverage(risk_ids)

        filtered_count = 0
        sq = result.get("stage_quality", {}).get("structure", {})
        filtered_count = sq.get("cross_mappings_filtered", 0)
        coverage["cross_mapping"] = compute_cross_mapping_coverage(taxonomy_data, filtered_count)
    if coverage:
        result["coverage"] = coverage

    if emit_rows and profiles:
        gen = compute_generation_metrics(emit_rows, profiles)
        gen["enumeration_concentration"] = compute_enumeration_concentration(emit_rows)
        gen["technique_diversity"] = compute_technique_diversity(emit_rows)
        gen["bfo_diversity"] = compute_bfo_diversity(emit_rows)
        result["generation_metrics"] = gen

    if adversarial_path and adversarial_path.exists():
        adv_rows = [json.loads(line) for line in adversarial_path.read_text().strip().split("\n") if line]
        pm = compute_adversarial_metrics(adv_rows)
        pm["policy_coverage_balance"] = compute_policy_coverage_balance(pm["per_policy"])
        pm["jargon_leak_rate"] = compute_jargon_leak_rate(adv_rows)
        pm["axis_fidelity"] = compute_axis_fidelity(adv_rows)
        if all_policies:
            pm["named_entity_utilization"] = compute_named_entity_utilization(adv_rows, all_policies)
        weak_matches = (
            result.get("stage_quality", {})
            .get("map_risks", {})
            .get("weak_matches", [])
        )
        pm["weak_match_impact"] = compute_weak_match_impact(weak_matches, adv_rows)
        pm["semantic_diversity"] = compute_semantic_diversity(adv_rows)
        pm["similarity_graph"] = compute_similarity_edges(adv_rows)
        result["prompt_metrics"] = pm

    return result


def build_html_report(evaluation: dict, output_path: Path) -> None:
    """Build a self-contained HTML report from evaluation data."""
    template_path = Path(__file__).parent / "evaluation_report_template.html"
    template = template_path.read_text()
    html = template.replace("__REPORT_DATA__", json.dumps(evaluation))
    output_path.write_text(html)


def format_summary(evaluation: dict) -> str:
    run = evaluation.get("run", {})
    lines = [f"Evaluation: {run.get('policy_set', '?')} / {run.get('model', '?')} / {run.get('timestamp', '?')}"]

    sq = evaluation.get("stage_quality", {})
    if sq:
        mr = sq.get("map_risks", {})
        ctx = sq.get("contextualize", {})
        lines.append(
            f"  Stage quality: {mr.get('invalid_risk_indices', 0)} invalid indices, "
            f"{len(mr.get('weak_matches', []))} weak match(es), "
            f"{ctx.get('sibling_fallbacks', 0)} sibling fallbacks"
        )

    cov = evaluation.get("coverage", {})
    if cov:
        policy = cov.get("policy", [])
        onto = cov.get("ontological", {})
        total_risks = sum(p.get("risks_matched", 0) for p in policy)
        svad = cov.get("single_value_axis_dominance", {})
        edm = cov.get("enumeration_domain_mismatch", {})
        cov_extra = ""
        if svad:
            cov_extra += f", {svad.get('single_value_rate', 0)} single-value axis rate"
        if edm:
            cov_extra += f", {edm.get('mismatched', 0)} enum domain mismatch(es)"
        sr = cov.get("sibling_relevance", {})
        if sr and sr.get("sibling_count", 0) > 0:
            cov_extra += (
                f", sibling enums {sr.get('sibling_count', 0)}"
                f" (mean score {sr.get('sibling_mean_score', 0)}"
                f" vs subclass {sr.get('subclass_mean_score', 0)})"
            )
        lines.append(
            f"  Coverage: {total_risks} risks, "
            f"{onto.get('unique_enumeration_uris', 0)} unique ontology classes"
            f"{cov_extra}"
        )

    gen = evaluation.get("generation_metrics", {})
    if gen:
        ec = gen.get("enumeration_concentration", {})
        conc_str = ""
        if ec:
            conc_str = f", top-{ec.get('top_k', 5)} concentration {ec.get('top_k_share', 0)}"
        sat = gen.get("dedup_saturation", {})
        saturated = {k: v for k, v in sat.items() if v.get("saturation", 0) >= 0.7}
        sat_str = f"dedup saturation {len(sat)} risks tracked"
        if saturated:
            sat_str += f" ({len(saturated)} near-exhausted)"
        lines.append(
            f"  Generation: axis diversity {gen.get('axis_diversity', {}).get('overall_mean', 0)}, "
            f"{sat_str}{conc_str}"
        )
        for risk_id, s in saturated.items():
            short_id = risk_id.split("/")[-1] if "/" in risk_id else risk_id
            lines.append(
                f"  WARNING: {short_id} saturation {s['saturation']:.0%} "
                f"({s['samples']}/{s['combinatorial_space']} combinations)"
            )

    pm = evaluation.get("prompt_metrics", {})
    if pm:
        pcb = pm.get("policy_coverage_balance", {})
        jlr = pm.get("jargon_leak_rate", {})
        extra = ""
        if pcb:
            extra += f", balance {pcb.get('normalized_entropy', 0)}"
        if jlr:
            extra += f", {jlr.get('jargon_prompts', 0)} jargon leak(s)"
        af = pm.get("axis_fidelity", {})
        if af:
            extra += f", fidelity {af.get('mean_fidelity', 0)} ({af.get('improvised', 0)} improvised)"
        neu = pm.get("named_entity_utilization", {})
        if neu:
            extra += f", entity utilization {neu.get('utilization_rate', 0)}"
        wmi = pm.get("weak_match_impact", {})
        if wmi and wmi.get("weak_match_prompts", 0) > 0:
            extra += f", {wmi.get('weak_match_prompts', 0)} weak-match prompts"
        sd = pm.get("semantic_diversity", {})
        if sd:
            extra += f", semantic diversity {sd.get('mean_pairwise_distance', 0)}"
        lines.append(
            f"  Prompts: TTR {pm.get('lexical_diversity', 0)}, "
            f"domain hit rate {pm.get('domain_term_hit_rate', 0)}, "
            f"{pm.get('red_flag_count', 0)} red flags ({pm.get('red_flag_hard', 0)} hard, {pm.get('red_flag_soft', 0)} soft)"
            f"{extra}"
        )

    je = evaluation.get("judge_evaluation", {})
    if je:
        agg = je.get("aggregates", {})
        lines.append(
            f"  Judge: subtlety {agg.get('subtlety', {}).get('mean', '?')}, "
            f"plausibility {agg.get('plausibility', {}).get('mean', '?')}, "
            f"grounding {agg.get('domain_grounding', {}).get('mean', '?')}, "
            f"relevance {agg.get('policy_relevance', {}).get('mean', '?')}"
        )

    return "\n".join(lines)
