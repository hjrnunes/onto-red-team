# Pipeline Quality Issues — Post Live Testing

**Date:** 2026-04-01
**Model:** Gemma 2 9B IT Abliterated (vLLM, 8K context)
**Policy set:** South West Bank (`swb.json`, 6 policies)
**Run output:** `/tmp/refiner-output-11/`

## Issue 1: Semantic Role Assignment

**Stage:** Anchor (Stage 4)
**Severity:** Medium — affects downstream prompt generation quality

The 9B model frequently misassigns semantic roles (agent, object, instrument, location, temporal) to variation axes. These roles determine how the ontology class is used in prompt templates.

**Examples from this run:**
- `DisclosureProvision` assigned [agent] — provisions don't act, they constrain. Should be [instrument].
- `Act of Deceptive Communication` assigned [agent] — acts/processes aren't agents. Should be [object].
- Same risk matched from different policies gets inconsistent role assignments across runs.

**Root cause:** Semantic roles follow BFO/CCO distinctions (Continuant vs Occurrent, Agent vs Process vs Object) that require nuanced ontological understanding. A 9B parameter model doesn't reliably grasp these.

**Possible approaches:**
- A. Add role examples to the system prompt showing correct assignments for each BFO category
- B. Simplify the role taxonomy (fewer options = fewer mistakes)
- C. Post-processing: derive roles from the class's BFO category (if it's a subclass of `obo:BFO_0000015` Process, it can't be an agent)
- D. Accept the noise — roles are advisory for prompt generation, not structural

## Issue 2: Risk ID Truncation

**Stage:** Map Risks (Stage 3)
**Severity:** Medium — causes valid risk matches to be filtered as hallucinated

The model truncates long nexus risk IDs that contain slashes. The post-processing validation then filters them out because they don't match the exact ID in the cache.

**Examples from this run:**
- Model produced `ai-risk-taxonomy-financing-eligibility` — actual ID is `ai-risk-taxonomy-financing-eligibility/creditworthiness`
- Previous runs showed similar truncation patterns with long IDs

**Root cause:** The model sees IDs like `ai-risk-taxonomy-financing-eligibility/creditworthiness` in the candidate list and reproduces a shortened version. Slash characters may confuse the model's tokenization or it may interpret the slash as a separator.

**Possible approaches:**
- A. Prefix-match validation: if a cached ID starts with the model's output, accept it
- B. Shorten the IDs shown to the model (use a sequential index, map back after)
- C. Use the `tag` field instead of `id` (tags are typically shorter and cleaner)
- D. Fuzzy matching with a similarity threshold

## Issue 3: Slug Sanitization

**Stage:** Structure (Stage 6)
**Severity:** Low — cosmetic, but produces ugly IDs

The slug generation doesn't collapse consecutive dashes, producing IDs like `client-swb-disclosure---financial` from risk names containing punctuation ("Disclosure - Financial").

**Root cause:** The slugify function replaces non-alphanumeric characters with dashes but doesn't collapse runs of multiple dashes.

**Fix:** Add `.replace('---', '-').replace('--', '-')` or use a regex `re.sub(r'-+', '-', slug)` in the `_slugify()` function. Trivial fix.

## Issue 4: Money Laundering Coverage Gap

**Stage:** Map Risks (Stage 3)
**Severity:** Low-Medium — affects one policy in this run, likely affects other financial/regulatory policies

The "Money Laundering" policy was matched to "Fraud, scams" [primary] and "Drugs" [supporting]. Neither is a strong match — there's no dedicated AML (Anti-Money Laundering) risk entry in the AI Atlas Nexus knowledge graph.

**Root cause:** Data gap in the nexus, not a pipeline issue. The 10 integrated risk frameworks don't have granular AML-specific risk entries. The semantic search returns the closest available risks, which happen to be fraud and drugs.

**Possible approaches:**
- A. Add AML-specific risk entries to the AI Atlas Nexus knowledge graph
- B. Accept the best-available match — the pipeline correctly surfaces that the coverage is thin
- C. Use the gap_analysis tool to explicitly flag policies with weak matches (distance threshold)
- D. Lower the match threshold and allow "no strong match" as a valid outcome

## Issue 5: Duplicate Risk Entries Across Policies

**Stage:** Map Risks (Stage 3) + Structure (Stage 6)
**Severity:** Low — structure stage deduplicates, but the anchor/contextualize stages do redundant work

The same risk (e.g., `ai-risk-taxonomy-financial` "Financial Advice") is matched by multiple policies (Debt Repayment Negotiation + Investment Advice). The anchor and contextualize stages process it independently for each policy, doing duplicate LLM calls with slightly different results.

**Examples from this run:**
- `ai-risk-taxonomy-financial` anchored twice (files 11 and 12) — same axes selected but in different order
- `ai-risk-taxonomy-scams` anchored from both Suspicious Activity Reporting and Fraud
- `mit-ai-risk-subdomain-4.3` anchored from both Fraud and Money Laundering

**Root cause:** The pipeline iterates per-policy, per-risk. A risk matched by multiple policies gets processed multiple times.

**Possible approaches:**
- A. Deduplicate at the anchor stage input: collect unique risk IDs across all policies, anchor each once, then fan results back to policies
- B. Cache anchor results by risk_id: if already processed, reuse
- C. Accept the duplication — the structure stage deduplicates entries, and the contextualize results may legitimately differ by policy context

## Issue 6: Self-Reference in Sibling Enumerations

**Stage:** Contextualize (Stage 5)
**Severity:** Low — noise, not harmful

When the sibling fallback triggers, the LLM sometimes selects the axis class itself as an enumeration (e.g., `FinancialRecord` axis produces `FinancialRecord` as an enumeration, `Deception Artifact Function` axis produces `Deception Artifact Function` as an enumeration).

**Examples from this run:**
- `FinancialRecord` [object] → enumeration includes `FinancialRecord` itself (relevance: high)
- `Deception Artifact Function` [instrument] → enumeration includes `Deception Artifact Function` itself (relevance: high)

**Root cause:** The siblings list includes classes at the same level under the parent. When the self-exclusion filter runs (`if s.get("uri") != axis.cco_class_uri`), it correctly removes the axis from the candidate list. But the LLM is asked to filter/annotate the candidates, and if the axis class has no subclasses AND no siblings (after exclusion), the list is empty. In some cases the LLM produces the axis class URI as an enumeration from its own knowledge.

Actually, looking more carefully: the self-exclusion works at the candidate-gathering level, but some of these may be cases where `get_siblings()` returns the class itself in the list and the URI comparison doesn't match due to trailing characters or normalization differences. Need to verify.

**Possible approaches:**
- A. Post-processing: filter out enumerations whose URI matches the axis URI
- B. Add "Do not include the axis class itself as an enumeration" to the system prompt
- C. Accept — self-reference as an enumeration is harmless for prompt generation (it just means "use this class directly")
