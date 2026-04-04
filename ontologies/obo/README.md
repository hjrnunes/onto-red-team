# OBO Foundry Ontologies

Downloaded from OBO Foundry PURLs. Originally on 2026-03-31 (healthcare),
extended 2026-04-03 (protected characteristics, social entities).

Large ontologies use `-base` versions (`http://purl.obolibrary.org/obo/{id}/id-base.owl`)
which exclude imported axioms, reducing file size significantly.
Smaller ontologies use full versions (`http://purl.obolibrary.org/obo/{id}.owl`).

All are BFO-aligned, OWL format, and open-licensed (except GSSO — see note).

## Healthcare

| File | Name | Classes | License | Source |
|---|---|---|---|---|
| ogms.owl | Ontology for General Medical Science | ~130 | CC BY 4.0 | https://github.com/OGMS/ogms |
| mondo-base.owl | MONDO Disease Ontology | ~30,000 | CC BY 4.0 | https://github.com/monarch-initiative/mondo |
| hp-base.owl | Human Phenotype Ontology | ~18,000 | Open | https://github.com/obophenotype/human-phenotype-ontology |
| uberon-base.owl | Uberon Anatomy Ontology | ~16,000 | CC BY 3.0 | https://github.com/obophenotype/uberon |
| maxo.owl | Medical Action Ontology | ~1,700 | Open | https://github.com/monarch-initiative/MAxO |
| *(excluded)* dron-base.owl | Drug Ontology | ~770,000 | CC BY 3.0 | https://github.com/mcwdsi/dron |
| oae.owl | Ontology of Adverse Events | ~5,000 | CC BY 3.0 | https://github.com/OAE-ontology/OAE |

## Protected Characteristics / Demographics (cross-domain)

| File | Name | Classes | License | Source |
|---|---|---|---|---|
| gsso.owl | Gender, Sex, and Sexual Orientation | ~13,000 | CC BY-NC-ND 4.0 | https://github.com/Superraptor/GSSO |
| hancestro.owl | Human Ancestry Ontology | ~1,300 | CC BY 4.0 | https://github.com/EBISPOT/hancestro |

## Social Entities / Insurance Roles

| File | Name | Classes | License | Source |
|---|---|---|---|---|
| omrse.owl | Ontology for Modeling and Representation of Social Entities | ~600 | CC BY 4.0 | https://github.com/mcwdsi/OMRSE |

## Data Use / Privacy Governance

| File | Name | Classes | License | Source |
|---|---|---|---|---|
| duo.owl | Data Use Ontology | ~45 | CC BY 4.0 | https://github.com/EBISPOT/DUO |

## Purpose

Domain ontology layer for red-team prompt generation across multiple verticals:

- **Healthcare**: OGMS bridges CCO to the medical domain (MONDO, HPO, UBERON, MAXO, OAE)
- **Protected characteristics**: GSSO + HANCESTRO provide variation axes for discrimination/bias
  testing across all domains (banking, insurance, telecom, government)
- **Social entities**: OMRSE provides insurance roles (`InsurancePolicy`, `InsuredPartyRole`,
  `PolicyHolderRole`, `PayerRole`), healthcare roles (`PatientRole`, `PhysicianRole`),
  and legal/contractual concepts (`Contract`, `IndemnityContract`)
- **Data use**: DUO provides data use conditions for privacy/governance risk scenarios

All ontologies share BFO as upper ontology — no bridge mapping needed.

## Notes

- **DRON-base excluded**: Moved to `../dron-base.owl`. The base version is still 644MB
  with ~770k classes (mostly individual drug products like "albendazole tablet"),
  only 72 of which have definitions. Too large for practical ChromaDB embedding.
  OAE, MAXO, and MONDO provide sufficient drug-related coverage for prompt generation.
- **GSSO lang tag fix**: The fetch script (`scripts/fetch_ontologies.sh`) patches two
  triples with invalid `xml:lang="e"` → `xml:lang="en"` after download. Without this,
  oxigraph's strict BCP47 parser rejects the entire file. Rdflib is lenient and accepts it.
- **GSSO license**: CC BY-NC-ND 4.0 is restrictive (no commercial, no derivatives).
  We index for search only, not redistributing or modifying the ontology content.
- Indexed OBO total (without DRON): **~94,600 classes**. Full index: **~100,560 classes** (with DUO + LKIF).
