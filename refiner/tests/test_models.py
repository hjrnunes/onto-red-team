import pytest
from refiner.models import (
    Policy, RiskMatch, PolicyRiskMapping,
    VariationAxis, RiskVariationAxes, AxisEnumeration, DomainContextAxis,
    VocabularyContext, PolicySourceRef, PipelineConfig, RiskSummary,
    RiskGrounding, PolicyDomainContext, DomainContext,
)

def test_policy_creation():
    p = Policy(policy_concept="Fraud", concept_definition="Prompts about fraud")
    assert p.policy_concept == "Fraud"

def test_risk_match_valid_relevance():
    for r in ("primary", "supporting", "tangential"):
        rm = RiskMatch(risk_id="r1", risk_name="Risk", relevance=r, justification="j")
        assert rm.relevance == r

def test_policy_risk_mapping():
    prm = PolicyRiskMapping(policy_concept="Fraud", matched_risks=[])
    assert prm.matched_risks == []

def test_variation_axis():
    va = VariationAxis(cco_class_uri="http://example.org/Person", cco_class_label="Person", roles=["agent"], rationale="Actors who commit fraud")
    assert va.roles == ["agent"]

def test_risk_variation_axes():
    rva = RiskVariationAxes(risk_id="r1", risk_name="Fraud", policy_concept="Fraud", axes=[])
    assert rva.axes == []

def test_axis_enumeration_valid_relevance():
    for r in ("high", "medium", "low"):
        ae = AxisEnumeration(class_uri="http://example.org/C", class_label="Class", source_ontology="CCO", relevance=r)
        assert ae.relevance == r

def test_sampled_axis_creation():
    from refiner.models import SampledAxis
    sa = SampledAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        roles=["agent"],
        sampled_uri="http://example.org/Manager",
        sampled_label="Manager",
        source_ontology="FIBO",
        relevance="high",
    )
    assert sa.sampled_label == "Manager"
    assert sa.roles == ["agent"]


def test_sampled_axis_rejects_invalid_relevance():
    from refiner.models import SampledAxis
    import pytest
    with pytest.raises(Exception):
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            roles=["agent"],
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="critical",
        )


def test_run_report_creation():
    from refiner.models import RunReport
    report = RunReport(model="test-model", policy_set="test.json", timestamp="2026-04-01T00:00:00Z")
    assert report.model == "test-model"
    assert report.stages_completed == []
    assert report.events == []


def test_run_report_append_event():
    from refiner.models import RunReport
    report = RunReport(model="m", policy_set="p", timestamp="t")
    report.events.append({"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO"]})
    assert len(report.events) == 1
    assert report.events[0]["stage"] == "identify_domains"


def test_run_report_to_dict():
    from refiner.models import RunReport
    report = RunReport(model="m", policy_set="p.json", timestamp="t")
    report.stages_completed.append("identify_domains")
    report.events.append({"stage": "identify_domains", "event": "selected_domains", "domains": ["CCO"]})
    d = report.to_dict()
    assert d["model"] == "m"
    assert d["policy_set"] == "p.json"
    assert d["stages_completed"] == ["identify_domains"]
    assert len(d["events"]) == 1


# --- VocabularyContext ---


def test_vocabulary_context_defaults():
    vc = VocabularyContext()
    assert vc.stakeholders == []
    assert vc.data_sensitivity == []
    assert vc.rights == []
    assert vc.justifications == []
    assert vc.sector_purposes == []
    assert vc.risk_concepts == []
    assert vc.prohibited_practices == []


def test_vocabulary_context_with_data():
    vc = VocabularyContext(
        stakeholders=[{"uri": "http://example.org/Patient", "label": "Patient"}],
        risk_concepts=[{"uri": "http://example.org/Bias", "label": "Bias"}],
    )
    assert len(vc.stakeholders) == 1
    assert vc.stakeholders[0]["label"] == "Patient"
    assert len(vc.risk_concepts) == 1


# --- PolicySourceRef ---


def test_policy_source_ref_defaults():
    ps = PolicySourceRef()
    assert ps.organization is None
    assert ps.domain is None
    assert ps.policy_count == 0


def test_policy_source_ref_with_values():
    ps = PolicySourceRef(organization="Acme Corp", domain="healthcare", policy_count=5)
    assert ps.organization == "Acme Corp"
    assert ps.domain == "healthcare"
    assert ps.policy_count == 5


# --- PipelineConfig ---


def test_pipeline_config_defaults():
    pc = PipelineConfig()
    assert pc.weak_match_threshold == 0.4
    assert pc.max_axes_per_risk == 8
    assert pc.enumerations_per_axis == 8
    assert pc.axes_per_prompt == 3


def test_pipeline_config_custom():
    pc = PipelineConfig(weak_match_threshold=0.5, max_axes_per_risk=5, enumerations_per_axis=12)
    assert pc.weak_match_threshold == 0.5
    assert pc.max_axes_per_risk == 5
    assert pc.enumerations_per_axis == 12


# --- RiskSummary ---


def test_risk_summary_minimal():
    rs = RiskSummary(risk_id="r1", risk_name="Bias Risk")
    assert rs.risk_id == "r1"
    assert rs.risk_name == "Bias Risk"
    assert rs.risk_description == ""
    assert rs.risk_concern == ""
    assert rs.risk_framework == ""
    assert rs.cross_mappings == []


def test_risk_summary_full():
    rs = RiskSummary(
        risk_id="r1", risk_name="Bias Risk",
        risk_description="Systematic bias", risk_concern="Fairness",
        risk_framework="NIST", cross_mappings=[{"id": "m1", "name": "Mapped"}],
    )
    assert rs.risk_description == "Systematic bias"
    assert len(rs.cross_mappings) == 1


# --- DomainContextAxis with typed vocabulary_context ---


def test_domain_context_axis_typed_vocabulary_context():
    dca = DomainContextAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        vocabulary_context=VocabularyContext(
            stakeholders=[{"uri": "http://example.org/Patient", "label": "Patient"}],
        ),
        enumerations=[],
    )
    assert isinstance(dca.vocabulary_context, VocabularyContext)
    assert len(dca.vocabulary_context.stakeholders) == 1


def test_domain_context_axis_coerces_dict_to_vocabulary_context():
    dca = DomainContextAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        vocabulary_context={"stakeholders": [{"uri": "http://example.org/Patient", "label": "Patient"}]},
        enumerations=[],
    )
    assert isinstance(dca.vocabulary_context, VocabularyContext)
    assert len(dca.vocabulary_context.stakeholders) == 1


def test_domain_context_axis_empty_dict_coerces_to_default_vocabulary_context():
    dca = DomainContextAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        vocabulary_context={},
        enumerations=[],
    )
    assert isinstance(dca.vocabulary_context, VocabularyContext)
    assert dca.vocabulary_context.stakeholders == []


def test_domain_context_axis_default_vocabulary_context():
    dca = DomainContextAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        enumerations=[],
    )
    assert isinstance(dca.vocabulary_context, VocabularyContext)


# --- RiskGrounding ---


def test_risk_grounding():
    axis = DomainContextAxis(
        cco_class_uri="http://example.org/Person",
        cco_class_label="Person",
        enumerations=[],
    )
    rg = RiskGrounding(risk_id="r1", axes=[axis])
    assert rg.risk_id == "r1"
    assert len(rg.axes) == 1


# --- PolicyDomainContext ---


def test_policy_domain_context():
    rg = RiskGrounding(risk_id="r1", axes=[])
    pdc = PolicyDomainContext(policy_concept="Fraud Prevention", risk_groundings=[rg])
    assert pdc.policy_concept == "Fraud Prevention"
    assert len(pdc.risk_groundings) == 1


# --- DomainContext ---


def test_domain_context_document_defaults():
    doc = DomainContext()
    assert doc.version == "0.1"
    assert doc.model == ""
    assert doc.timestamp == ""
    assert doc.run_slug == ""
    assert doc.selected_domains == []
    assert doc.policy_source is None
    assert doc.config is None
    assert doc.risks == []
    assert doc.policy_contexts == []


def test_domain_context_document_full():
    doc = DomainContext(
        version="0.1",
        model="phi-4",
        timestamp="2026-04-14T00:00:00Z",
        run_slug="test-run",
        selected_domains=["CCO", "FIBO"],
        policy_source=PolicySourceRef(organization="Acme", domain="finance", policy_count=3),
        config=PipelineConfig(weak_match_threshold=0.3),
        risks=[RiskSummary(risk_id="r1", risk_name="Bias")],
        policy_contexts=[
            PolicyDomainContext(
                policy_concept="Fair Lending",
                risk_groundings=[
                    RiskGrounding(risk_id="r1", axes=[]),
                ],
            ),
        ],
    )
    assert doc.model == "phi-4"
    assert doc.policy_source.organization == "Acme"
    assert doc.config.weak_match_threshold == 0.3
    assert len(doc.risks) == 1
    assert len(doc.policy_contexts) == 1
    assert doc.policy_contexts[0].risk_groundings[0].risk_id == "r1"


def test_domain_context_document_roundtrip_json():
    doc = DomainContext(
        version="0.1",
        model="phi-4",
        timestamp="2026-04-14T00:00:00Z",
        run_slug="test-run",
        selected_domains=["CCO"],
        policy_source=PolicySourceRef(organization="Acme"),
        config=PipelineConfig(),
        risks=[RiskSummary(risk_id="r1", risk_name="Bias")],
        policy_contexts=[],
    )
    json_str = doc.model_dump_json()
    restored = DomainContext.model_validate_json(json_str)
    assert restored.model == "phi-4"
    assert restored.policy_source.organization == "Acme"
    assert isinstance(restored.config, PipelineConfig)
    assert len(restored.risks) == 1


def test_domain_context_document_has_knowledge_base():
    from refiner.models import KnowledgeBaseRef
    dcd = DomainContext(
        knowledge_base=KnowledgeBaseRef(nexus_commit="abc123"),
    )
    d = dcd.model_dump()
    assert d["knowledge_base"]["nexus_commit"] == "abc123"
    dcd2 = DomainContext(**d)
    assert dcd2.knowledge_base.nexus_commit == "abc123"


def test_domain_context_document_knowledge_base_defaults_none():
    dcd = DomainContext()
    assert dcd.knowledge_base is None


# --- KnowledgeBaseRef ---


def test_knowledge_base_ref_round_trip():
    from refiner.models import KnowledgeBaseRef
    ref = KnowledgeBaseRef(
        nexus_commit="abc1234",
        nexus_risk_count=612,
        ontology_index_hash="sha256:deadbeef",
        ontology_domains={"CCO": 5000, "FIBO": 1500, "OBO": 95000},
        indexed_at="2026-04-14T12:00:00Z",
    )
    d = ref.model_dump()
    assert d["nexus_commit"] == "abc1234"
    assert d["nexus_risk_count"] == 612
    assert d["ontology_domains"]["CCO"] == 5000
    ref2 = KnowledgeBaseRef(**d)
    assert ref2 == ref


def test_knowledge_base_ref_defaults():
    from refiner.models import KnowledgeBaseRef
    ref = KnowledgeBaseRef()
    assert ref.nexus_commit == ""
    assert ref.nexus_risk_count == 0
    assert ref.ontology_domains == {}


# --- RiskDetail ---


def test_risk_detail_round_trip():
    from refiner.models import RiskDetail
    detail = RiskDetail(
        risk_id="atlas-personal-information-in-prompt",
        risk_name="Personal information",
        risk_description="Personal information or sensitive personal information...",
        risk_concern="If personal information is included in the prompt...",
        risk_framework="ibm-risk-atlas",
        cross_mappings=[{"id": "nist-data-privacy", "mapping_type": "broad"}],
        related_actions=["Minimize personal data in prompts"],
    )
    d = detail.model_dump()
    assert d["risk_id"] == "atlas-personal-information-in-prompt"
    assert d["related_actions"] == ["Minimize personal data in prompts"]
    detail2 = RiskDetail(**d)
    assert detail2 == detail


def test_risk_detail_defaults():
    from refiner.models import RiskDetail
    detail = RiskDetail(risk_id="test", risk_name="Test")
    assert detail.risk_description == ""
    assert detail.cross_mappings == []
    assert detail.related_actions == []


def test_risk_landscape_round_trip():
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
        KnowledgeBaseRef, PolicySourceRef,
    )
    landscape = RiskLandscape(
        model="gemma-3-12b-it",
        timestamp="2026-04-14T12:00:00Z",
        run_slug="swb-enriched",
        selected_domains=["CCO", "Commons", "FIBO", "D3FEND", "CSO", "LKIF"],
        policy_source=PolicySourceRef(organization="South West Bank", domain="banking", policy_count=6),
        knowledge_base=KnowledgeBaseRef(nexus_commit="abc1234", nexus_risk_count=612),
        risks=[
            RiskDetail(
                risk_id="atlas-personal-information-in-prompt",
                risk_name="Personal information",
                risk_description="Personal information...",
                cross_mappings=[{"id": "nist-data-privacy", "mapping_type": "broad"}],
                related_actions=["Minimize personal data"],
            ),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Executive Compensation",
                matched_risks=[
                    RiskMatch(
                        risk_id="atlas-personal-information-in-prompt",
                        risk_name="Personal information",
                        relevance="primary",
                        justification="Directly addresses PII concerns",
                        match_distance=0.234,
                    ),
                ],
            ),
        ],
        framework_coverage={"ibm-risk-atlas": 1},
        weak_matches=[],
    )
    d = landscape.model_dump()
    assert d["version"] == "0.1"
    assert d["selected_domains"][2] == "FIBO"
    assert len(d["risks"]) == 1
    assert d["risks"][0]["related_actions"] == ["Minimize personal data"]
    assert len(d["policy_mappings"]) == 1
    landscape2 = RiskLandscape(**d)
    assert landscape2.risks[0].risk_id == "atlas-personal-information-in-prompt"
    assert landscape2.policy_mappings[0].matched_risks[0].match_distance == 0.234


def test_risk_landscape_yaml_round_trip(tmp_path):
    import yaml
    from refiner.models import (
        RiskLandscape, RiskDetail, PolicyRiskMapping, RiskMatch,
    )
    landscape = RiskLandscape(
        model="test-model",
        timestamp="2026-04-14T12:00:00Z",
        run_slug="test",
        risks=[
            RiskDetail(risk_id="r1", risk_name="Risk One"),
        ],
        policy_mappings=[
            PolicyRiskMapping(
                policy_concept="Policy A",
                matched_risks=[
                    RiskMatch(risk_id="r1", risk_name="Risk One",
                              relevance="primary", justification="test"),
                ],
            ),
        ],
    )
    path = tmp_path / "risk-landscape.yaml"
    path.write_text(yaml.dump(landscape.model_dump(), default_flow_style=False, sort_keys=False))
    loaded = yaml.safe_load(path.read_text())
    landscape2 = RiskLandscape(**loaded)
    assert landscape2.risks[0].risk_id == "r1"
    assert landscape2.policy_mappings[0].policy_concept == "Policy A"


def test_risk_landscape_defaults():
    from refiner.models import RiskLandscape
    landscape = RiskLandscape()
    assert landscape.version == "0.1"
    assert landscape.risks == []
    assert landscape.policy_mappings == []
    assert landscape.framework_coverage == {}
    assert landscape.weak_matches == []
    assert landscape.selected_domains == []
    assert landscape.knowledge_base is None
