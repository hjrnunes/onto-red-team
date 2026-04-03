#!/usr/bin/env python3
"""Extract assessment data from a pipeline run directory.

Reads pipeline outputs (taxonomy, domain context, report, evaluation,
adversarial prompts) and prints structured data for writing an assessment.

Usage:
    cd refiner
    uv run python tools/assess_run.py ../runs/swb-non-truncated
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def load_jsonl(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def discover_file(run_dir: Path, suffix: str) -> Path | None:
    matches = list(run_dir.glob(f"*{suffix}"))
    return matches[0] if matches else None


def print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def assess_run(run_dir: Path):
    # Discover files
    report_path = discover_file(run_dir, "-report.yaml")
    taxonomy_path = discover_file(run_dir, "-taxonomy.yaml")
    domain_ctx_path = discover_file(run_dir, "-domain-context.yaml")
    eval_path = discover_file(run_dir, "-evaluation.json")
    adversarial_path = run_dir / "adversarial_prompts.jsonl"
    dataset_path = run_dir / "dataset.jsonl"
    debug_dir = run_dir / "debug"

    report = load_yaml(report_path) if report_path else None
    taxonomy = load_yaml(taxonomy_path) if taxonomy_path else None
    domain_ctx = load_yaml(domain_ctx_path) if domain_ctx_path else None
    evaluation = load_json(eval_path) if eval_path else None
    adversarial = load_jsonl(adversarial_path)
    dataset = load_jsonl(dataset_path)

    # --- Run metadata ---
    print_section("RUN METADATA")
    if report:
        print(f"Model: {report.get('model', '?')}")
        print(f"Policy set: {report.get('policy_set', '?')}")
        print(f"Timestamp: {report.get('timestamp', '?')}")
        print(f"Stages completed: {report.get('stages_completed', [])}")

    # --- Taxonomy summary ---
    print_section("TAXONOMY")
    if taxonomy:
        groups = taxonomy.get("groups", [])
        entries = taxonomy.get("entries", [])
        print(f"Risk groups: {len(groups)}")
        for g in groups:
            print(f"  - {g['id']}: {g['name']}")
        print(f"\nRisk entries: {len(entries)}")
        for e in entries:
            cross = []
            for mt in ("exact_mappings", "close_mappings", "broad_mappings", "narrow_mappings", "related_mappings"):
                cross.extend(e.get(mt, []))
            print(f"  - {e['id']}: {e['name']} (group: {e.get('isPartOf', '?')}, cross-mappings: {len(cross)})")

    # --- Report events summary ---
    print_section("PIPELINE EVENTS")
    if report:
        events = report.get("events", [])
        type_dist = [e for e in events if e.get("event") == "type_distribution"]
        if type_dist:
            print(f"Type distribution: {type_dist[0].get('distribution', {})}")

        domains = [e for e in events if e.get("event") == "selected_domains"]
        if domains:
            print(f"Selected domains: {domains[0].get('domains', [])}")

        match_counts = [e for e in events if e.get("event") == "match_count"]
        if match_counts:
            print(f"\nMatch counts:")
            for mc in match_counts:
                print(f"  {mc['policy_concept']}: {mc['count']} risks")

        weak = [e for e in events if e.get("event") == "weak_match"]
        if weak:
            print(f"\nWeak matches: {len(weak)}")
            for w in weak:
                print(f"  {w['risk_id']}: distance={w['distance']:.3f}")

        empty = [e for e in events if e.get("event") == "empty_axes"]
        if empty:
            print(f"\nEmpty axes (no anchor candidates after filtering):")
            for ea in empty:
                print(f"  {ea['risk_id']}")

        empty_enum = [e for e in events if e.get("event") == "empty_enumerations"]
        if empty_enum:
            print(f"\nEmpty enumerations:")
            for ee in empty_enum:
                print(f"  {ee['risk_id']} / {ee.get('axis_uri', '?').split('/')[-1]}")

    # --- Domain context profiles ---
    print_section("DOMAIN CONTEXT PROFILES")
    if domain_ctx:
        profiles = domain_ctx.get("profiles", [])
        print(f"Total profiles: {len(profiles)}")
        total_axes = 0
        total_enums = 0
        empty_axes_list = []
        empty_enum_axes = []
        for p in profiles:
            axes = p.get("axes", [])
            total_axes += len(axes)
            if not axes:
                empty_axes_list.append(f"{p['risk_id']} / {p['policy_concept']}")
            for a in axes:
                enums = a.get("enumerations", [])
                total_enums += len(enums)
                if not enums:
                    empty_enum_axes.append(
                        f"{a['cco_class_label']} ({p['risk_id']})"
                    )
        print(f"Total axes: {total_axes}")
        print(f"Total enumerations: {total_enums}")
        if empty_axes_list:
            print(f"\nProfiles with zero axes:")
            for e in empty_axes_list:
                print(f"  - {e}")
        if empty_enum_axes:
            print(f"\nAxes with zero enumerations:")
            for e in empty_enum_axes:
                print(f"  - {e}")

        # Enumeration relevance distribution
        relevances = Counter()
        for p in profiles:
            for a in p.get("axes", []):
                for e in a.get("enumerations", []):
                    relevances[e.get("relevance", "?")] += 1
        if relevances:
            print(f"\nEnumeration relevance: {dict(relevances.most_common())}")

        # Source ontology distribution (axes level)
        axis_onts = Counter()
        for p in profiles:
            for a in p.get("axes", []):
                uri = a.get("cco_class_uri", "")
                if "commoncoreontologies" in uri:
                    axis_onts["CCO"] += 1
                elif "edmcouncil.org/fibo" in uri:
                    axis_onts["FIBO"] += 1
                elif "omg.org/spec/Commons" in uri:
                    axis_onts["Commons"] += 1
                else:
                    axis_onts["other"] += 1
        print(f"Axis source ontologies: {dict(axis_onts.most_common())}")

    # --- Adversarial prompts ---
    print_section("ADVERSARIAL PROMPTS")
    if adversarial:
        print(f"Total prompts: {len(adversarial)}")

        policies = Counter(p["policy_concept"] for p in adversarial)
        risks = Counter(p["risk_name"] for p in adversarial)
        source_onts = Counter()
        roles_seen = Counter()
        sampled_values = Counter()
        lengths = []

        for p in adversarial:
            prompt_text = p.get("prompt") or ""
            lengths.append(len(prompt_text))
            for a in p.get("sampled_axes", []):
                source_onts[a.get("source_ontology", "?")] += 1
                for r in a.get("roles", []):
                    roles_seen[r] += 1
                sampled_values[a.get("sampled_label", "?")] += 1

        print(f"Unique risks: {len(risks)}")
        print(f"Prompt lengths: {min(lengths)}-{max(lengths)} chars, avg {sum(lengths) // len(lengths)}")

        print(f"\nPolicy coverage:")
        for pc, c in policies.most_common():
            print(f"  {pc}: {c}")

        print(f"\nRisk coverage:")
        for rn, c in risks.most_common():
            print(f"  {rn}: {c}")

        total_axes = sum(source_onts.values())
        print(f"\nSource ontology ({total_axes} axis samples):")
        for so, c in source_onts.most_common():
            print(f"  {so}: {c} ({c / total_axes * 100:.0f}%)")

        print(f"\nRole distribution:")
        for r, c in roles_seen.most_common():
            print(f"  {r}: {c}")

        print(f"\nSampled values ({len(sampled_values)} unique):")
        for s, count in sampled_values.most_common():
            print(f"  {s}: {count}")

        # Print each prompt
        print_section("ALL PROMPTS")
        for i, p in enumerate(adversarial, 1):
            pc = p.get("policy_concept", "?")
            rn = p.get("risk_name", "?")
            text = p.get("prompt") or "?"
            axes = p.get("sampled_axes", [])
            axis_desc = ", ".join(
                f"{a.get('sampled_label', '?')} ({a.get('roles', ['?'])})"
                for a in axes
            )
            print(f"### #{i} — {pc} / {rn}")
            print(f"> \"{text}\"")
            print(f"**Axes:** {axis_desc}")
            print()

    # --- Evaluation metrics ---
    print_section("EVALUATION METRICS")
    if evaluation:
        pm = evaluation.get("prompt_metrics", {})
        print(f"Lexical diversity (TTR): {pm.get('lexical_diversity', '?')}")
        print(f"Mean prompt length: {pm.get('mean_prompt_length', '?')}")
        print(f"Domain term hit rate: {pm.get('domain_term_hit_rate', '?')}")
        print(f"Red flag count: {pm.get('red_flag_count', '?')}")

        gm = evaluation.get("generation_metrics", {})
        print(f"\nAxis diversity mean: {gm.get('axis_diversity', {}).get('overall_mean', '?')}")
        print(f"Role distribution: {gm.get('role_distribution', {})}")
        print(f"Relevance distribution: {gm.get('relevance_distribution', {})}")

        cov = evaluation.get("coverage", {})
        ont = cov.get("ontological", {})
        print(f"\nUnique axis classes: {ont.get('unique_axis_classes', '?')}")
        print(f"Unique enumeration URIs: {ont.get('unique_enumeration_uris', '?')}")
        print(f"By source ontology: {ont.get('by_source_ontology', {})}")

        xm = cov.get("cross_mapping", {})
        print(f"\nCross-mappings: {xm.get('total_cross_mappings_used', '?')} used")
        print(f"  with: {xm.get('risks_with_cross_mappings', '?')}, without: {xm.get('risks_without', '?')}")
        print(f"  by type: {xm.get('by_mapping_type', {})}")

        sat = gm.get("dedup_saturation", {})
        if sat:
            print(f"\nDedup saturation:")
            for risk_id, s in sat.items():
                short_id = risk_id.split("/")[-1] if "/" in risk_id else risk_id
                print(f"  {short_id}: {s['samples']}/{s['combinatorial_space']} = {s['saturation']:.2f}")

    # --- Debug log analysis ---
    print_section("DEBUG LOG ANALYSIS")
    if debug_dir.exists():
        debug_files = sorted(debug_dir.glob("*.json"))
        print(f"Debug files: {len(debug_files)}")

        map_risks_files = [f for f in debug_files if "map_risks" in f.name]
        if map_risks_files:
            print(f"\nmap_risks prompts ({len(map_risks_files)} calls):")
            for f in map_risks_files:
                with open(f) as fh:
                    data = json.load(fh)
                user_msg = next(
                    (m["content"] for m in data.get("messages", []) if m["role"] == "user"),
                    "",
                )
                print(f"  {f.name}: {len(user_msg)} chars (~{len(user_msg) // 4} tokens)")
    else:
        print("No debug directory found.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run_dir>")
        sys.exit(1)
    run_dir = Path(sys.argv[1]).resolve()
    if not run_dir.is_dir():
        print(f"Error: {run_dir} is not a directory")
        sys.exit(1)
    assess_run(run_dir)
