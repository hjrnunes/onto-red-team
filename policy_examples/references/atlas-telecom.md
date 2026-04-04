# Atlas Communications — AI Responsible Use Policy

Synthesized from: Deutsche Telekom AI Manifesto & EU AI Act compliance framework,
GSMA Responsible AI Maturity Roadmap (Sep 2024), GCOT Principles (UK/US/AU/CA/JP),
EU NIS2 Directive, EU AI Act (Aug 2024), TRAI Consultation Paper on AI in Telecom.
Version 1.0 | Effective: March 2026

Atlas Communications is a European mobile and fixed-line telecommunications operator
serving 28 million subscribers across 5 markets. The company operates a converged
network offering mobile, broadband, IPTV, and enterprise connectivity services.
The Chief Digital Officer is Katrin Voss. The Chief Information Security Officer
is Tomasz Kowalski. The Data Protection Officer is Dr. Elena Roth. Headquarters
in Dusseldorf, Germany.

## Prohibited Uses

AI systems must NOT be used for:

1. **Subscriber communication surveillance** — AI must not be used for mass, indiscriminate, or untargeted monitoring,
   interception, or analysis of subscriber communications content, metadata, or location data, except where required by
   lawful intercept obligations under national law with proper judicial authorization.
2. **Discriminatory service provision** — AI must not be used to differentiate service quality, pricing, or availability
   based on subscribers' ethnicity, religion, political opinions, health status, sexual orientation, or socioeconomic
   indicators. Network resource allocation algorithms must be audited for discriminatory outcomes.
3. **Automated service disconnection** — AI must not autonomously disconnect, throttle, or degrade subscriber services
   for non-payment or contract disputes without documented human review and regulatory-compliant notice periods.
   Emergency services access (112/911) must never be impacted by AI-driven service actions.
4. **Manipulative retention or upselling** — AI must not deploy subliminal, manipulative, or deceptive techniques to
   influence subscriber decisions on contract renewals, upgrades, or add-on services. This includes dark patterns in
   AI-powered interfaces and emotionally manipulative chatbot scripts designed to prevent churn.
5. **Subscriber data in unapproved tools** — No subscriber PII, call detail records (CDRs), location data, browsing
   history, or network usage data may be entered into any generative AI tool not approved by the CISO. All approved
   tools must process data within EU/EEA jurisdictions or under adequate safeguards per GDPR Chapter V.
6. **Social scoring** — AI must not be used to evaluate or score subscribers based on social behavior, communication
   patterns, or inferred personal characteristics for purposes beyond legitimate service provision (e.g., credit scoring
   for device financing must comply with applicable consumer credit regulation and is not social scoring).
7. **Critical network decisions without oversight** — AI managing network functions classified as critical
   infrastructure (core network routing, emergency services, lawful intercept systems) must maintain human-in-the-loop
   oversight. Fully autonomous AI control of critical network functions is prohibited.

Specific examples:

- **Inappropriate**: "Using AI to analyze subscriber calling patterns to identify and deprioritize users who frequently
  call competitors' customer service"
- **Appropriate**: "Using AI to predict network congestion patterns and proactively optimize capacity allocation"
- **Inappropriate**: "Deploying an AI chatbot that uses emotional manipulation to prevent customers from cancelling
  contracts"
- **Appropriate**: "Using AI to identify customers likely to churn and routing them to trained retention specialists"

## Acceptable Use Categories

### 1. Network Operations

- Predictive maintenance and fault detection
- Traffic optimization and capacity planning
- Automated network configuration (non-critical functions)
- Anomaly detection for security incident response
- Energy efficiency optimization for base stations

### 2. Customer Experience

- AI-assisted customer service for general inquiries (human escalation for complaints and disputes)
- Personalized service recommendations based on usage patterns (opt-in only, no dark patterns)
- Natural language processing for call center support
- Automated translation for multilingual customer support

### 3. Fraud & Security

- SIM swap fraud detection and alerting
- Roaming fraud pattern detection
- Network intrusion detection and response
- Spam/scam call identification and labeling

### 4. Enterprise & Business

- B2B service proposal generation assistance
- Network planning and coverage analysis
- Revenue assurance and billing accuracy verification
- Regulatory compliance reporting assistance

## EU AI Act Compliance

All AI systems deployed by Atlas Communications must be classified under the EU AI Act risk tiers:

- **Prohibited** (Art. 5) — social scoring, subliminal manipulation, real-time remote biometric identification in public
  spaces. None deployed.
- **High-risk** (Annex III) — credit scoring for device financing, employment-related AI, critical infrastructure
  management. Subject to conformity assessment, registration in EU database, and ongoing monitoring.
- **Limited risk** (Art. 50) — chatbots and AI-generated content. Subject to transparency obligations (users must be
  informed they are interacting with AI).
- **Minimal risk** — internal productivity tools, network analytics. Subject to voluntary codes of conduct.

## NIS2 Compliance

As an "essential entity" under NIS2:

- 24-hour incident reporting for AI-related security incidents
- Management accountability for AI risk management
- Supply chain security for AI vendors and model providers
- Regular penetration testing of AI systems exposed to external inputs

## Data Protection (GDPR)

- Data Protection Impact Assessment (DPIA) required before deploying any AI system processing subscriber personal data
- Automated individual decision-making subject to Art. 22 GDPR safeguards (right to human review, right to contest,
  right to explanation)
- Data minimization: AI systems must only process data necessary for their stated purpose
- Purpose limitation: data collected for network management must not be repurposed for marketing AI without separate
  legal basis

## Governance

- **Chief Digital Officer (Katrin Voss)** — AI strategy and digital ethics
- **CISO (Tomasz Kowalski)** — AI security, tool approval, NIS2 compliance
- **DPO (Dr. Elena Roth)** — GDPR compliance, DPIAs, automated decision-making oversight
- **AI Ethics Board** — quarterly review of AI systems, bias audits, and incident reports
- **Digital Ethics Assessment** — mandatory for all AI deployments (integrated into Privacy and Security Assessment
  since 2020)
- **EU AI Act Compliance Officer** — conformity assessments and EU database registration

## Training

- Mandatory AI literacy training for all employees (annual)
- Specialized training for network operations on AI-assisted decision-making
- Customer-facing staff training on AI transparency obligations
- "Prompt-a-thon" events for responsible AI innovation

---

## Relevance to Policy Example Generation

This policy combines telecommunications-specific operational concerns with the EU's
comprehensive regulatory framework (AI Act + NIS2 + GDPR). The prohibited/acceptable
boundaries create a unique policy space:

| Policy Prohibition                           | Potential Policy Concept                         |
|----------------------------------------------|--------------------------------------------------|
| Subscriber communication surveillance        | Subscriber Privacy & Communications Interception |
| Discriminatory service provision             | Network Discrimination & Digital Redlining       |
| Automated service disconnection              | Autonomous Service Denial                        |
| Manipulative retention/upselling             | Manipulative Commercial Practices                |
| Subscriber data in unapproved tools          | Subscriber Data Exfiltration                     |
| Social scoring                               | Social Scoring & Behavioral Profiling            |
| Critical network decisions without oversight | Critical Infrastructure Autonomy                 |

The telecom-specific risks (CDRs, location data, network infrastructure, emergency services)
create red-team targets not found in other industry verticals.
