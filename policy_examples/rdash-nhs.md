# RDaSH NHS Foundation Trust — Artificial Intelligence Policy

Source: https://www.rdash.nhs.uk/policies/artificial-intelligence-ai-policy/
Approved: November 18, 2025 | Review: August 31, 2028 | Version 1.1

Rotherham Doncaster and South Humber NHS Foundation Trust (RDaSH).
Applies to all staff, volunteers, students, temporary workers, contractors, suppliers, and third parties.

## Prohibited Uses

AI systems must NOT be used for:
- Making clinical decisions or determining diagnoses/treatment
- Processing identifiable patient data
- Replacing professional judgment
- Generating clinical entries directly into patient records
- Creating individualised care plans for named patients

Specific example given:
- **Inappropriate**: "Using Copilot chat to create a care plan for John Smith"
- **Appropriate**: "Using Copilot chat to summarise NICE guidelines on diabetes management"

## Acceptable Use Categories

### 1. Publicly Available AI (ChatGPT, Copilot)
- Document drafting for non-clinical purposes
- Idea generation and information summarisation
- Administrative task automation
- Exploring general health concepts (not patient-specific)

### 2. Microsoft 365 Copilot
- Can be used for administrative and business support including clinical administration
- Explicitly prohibited: clinical decision-making or direct patient care

### 3. Research Applications
- Requires Health Research Authority approval
- Requires Research Ethics Committee review

## Data Protection Requirements

- No person-identifiable data input to public AI tools
- No business-sensitive information sharing
- No confidential data processing
- Data Protection Impact Assessment (DPIA) required before implementation
- Legal basis must be established before processing personal data
- Note: "Combined details of a local area, a rare disease and a very young age may enable a patient to be identified" — careful anonymisation assessment required

## Clinical Practice Guardrails (GMC Framework)

- Clinicians remain personally accountable for all decisions regarding patient care
- AI outputs require validation before use
- Final responsibility for diagnosis, treatment, and patient care rests with the clinician
- Over-reliance on AI without oversight may compromise patient safety

## Patient Consent

- For AI use during consultations or information recording: patients must be fully informed
- Explicit consent obtained prior to any processing

## Training

- Annual data security awareness training required (1.5 hours)
- Records maintained in electronic staff record (ESR)

## Governance

- Chief Executive: overall policy responsibility
- Data Protection Officer: data protection compliance
- Caldicott Guardian: patient information processing oversight
- SIRO: information risk governance
- Clinical Safety Officer: clinical IT system safety assessment

---

## Relevance to Policy Example Generation

This policy is notable for its specificity compared to other frameworks. The prohibited/acceptable
use boundaries map well to content policy concepts:

| RDaSH Prohibition | Potential Policy Concept |
|---|---|
| Making clinical decisions or diagnoses | Clinical Diagnosis & Treatment |
| Processing identifiable patient data | Protected Health Information |
| Creating care plans for named patients | Clinical Diagnosis & Treatment |
| Generating clinical record entries | Medical Professional Impersonation |
| Replacing professional judgment | Medical Professional Impersonation |

The "inappropriate vs appropriate" examples pattern is particularly useful for
understanding the boundary the refiner pipeline needs to test.
