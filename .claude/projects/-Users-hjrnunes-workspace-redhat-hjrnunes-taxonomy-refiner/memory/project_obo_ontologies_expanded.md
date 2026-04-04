---
name: OBO stack expanded with GSSO, HANCESTRO, OMRSE
description: Three new ontologies added to OBO domain — GSSO (gender/sex/orientation ~13k classes), HANCESTRO (ancestry ~1.3k), OMRSE (social entities/insurance/healthcare roles ~600)
type: project
---

Three new ontologies added to the OBO domain stack (April 2026):

- **GSSO** (~13k classes) — gender, sex, sexual orientation
- **HANCESTRO** (~1.3k classes) — human ancestry
- **OMRSE** (~600 classes) — social entities, insurance/healthcare roles

**Why:** Expands axis vocabulary for healthcare and social policy risks. OMRSE in particular may help address the gen5 issue of FIBO contamination in healthcare — it provides insurance/healthcare role classes that are OBO-native, reducing the need for FIBO to be selected for healthcare policies that mention insurance/billing.

**How to apply:** When assessing gen6+ runs, check whether OMRSE classes appear in healthcare runs as replacements for the FIBO contamination classes (borrower data protection, automated underwriting, etc.). GSSO and HANCESTRO add dimensions for bias/discrimination risk testing.
