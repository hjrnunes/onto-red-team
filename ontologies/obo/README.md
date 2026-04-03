# OBO Foundry Healthcare Ontologies

Downloaded from OBO Foundry PURLs on 2026-03-31.

Large ontologies use `-base` versions (`http://purl.obolibrary.org/obo/{id}/id-base.owl`)
which exclude imported axioms, reducing file size significantly.
Smaller ontologies use full versions (`http://purl.obolibrary.org/obo/{id}.owl`).

All are BFO-aligned, OWL format, and open-licensed.

## Ontologies

| File | Name | Classes | License | Source |
|---|---|---|---|---|
| ogms.owl | Ontology for General Medical Science | ~130 | CC BY 4.0 | https://github.com/OGMS/ogms |
| mondo-base.owl | MONDO Disease Ontology | ~30,000 | CC BY 4.0 | https://github.com/monarch-initiative/mondo |
| hp-base.owl | Human Phenotype Ontology | ~18,000 | Open | https://github.com/obophenotype/human-phenotype-ontology |
| uberon-base.owl | Uberon Anatomy Ontology | ~16,000 | CC BY 3.0 | https://github.com/obophenotype/uberon |
| maxo.owl | Medical Action Ontology | ~1,700 | Open | https://github.com/monarch-initiative/MAxO |
| *(excluded)* dron-base.owl | Drug Ontology | ~770,000 | CC BY 3.0 | https://github.com/mcwdsi/dron |
| oae.owl | Ontology of Adverse Events | ~5,000 | CC BY 3.0 | https://github.com/OAE-ontology/OAE |

## Purpose

Domain ontology layer for healthcare red-team prompt generation. OGMS bridges
CCO to the medical domain. All ontologies share BFO as upper ontology — no
bridge mapping needed.

## Notes

- **DRON-base excluded**: Moved to `../dron-base.owl`. The base version is still 644MB
  with ~770k classes (mostly individual drug products like "albendazole tablet"),
  only 72 of which have definitions. Too large for practical ChromaDB embedding.
  OAE, MAXO, and MONDO provide sufficient drug-related coverage for prompt generation.
- Indexed healthcare total (CCO + OBO without DRON): **82,526 classes**.
