import json

import yaml

from refiner.models import AxisEnumeration, DomainContextProfile, DomainContextAxis, SampledAxis
from refiner.emit import relevance_weights, sample_axes, build_prompt


def _enum(relevance):
    return AxisEnumeration(
        class_uri="http://example.org/X",
        class_label="X",
        source_ontology="CCO",
        relevance=relevance,
    )


def test_relevance_weights_high_medium_low():
    enums = [_enum("high"), _enum("medium"), _enum("low")]
    weights = relevance_weights(enums)
    assert len(weights) == 3
    assert abs(sum(weights) - 1.0) < 1e-9
    # high=3, medium=2, low=1 → total=6
    assert abs(weights[0] - 0.5) < 1e-9
    assert abs(weights[1] - 1/3) < 1e-9
    assert abs(weights[2] - 1/6) < 1e-9


def test_relevance_weights_all_same():
    enums = [_enum("high"), _enum("high"), _enum("high")]
    weights = relevance_weights(enums)
    for w in weights:
        assert abs(w - 1/3) < 1e-9


def test_relevance_weights_single():
    enums = [_enum("low")]
    weights = relevance_weights(enums)
    assert weights == [1.0]


def _make_profile():
    return DomainContextProfile(
        risk_id="r1",
        risk_name="Risk One",
        policy_concept="Fraud",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/Person",
                cco_class_label="Person",
                role="agent",
                enumerations=[
                    _enum("high"),
                    AxisEnumeration(class_uri="http://example.org/Manager", class_label="Manager", source_ontology="FIBO", relevance="medium"),
                ],
            ),
            DomainContextAxis(
                cco_class_uri="http://example.org/Instrument",
                cco_class_label="Instrument",
                role="instrument",
                enumerations=[
                    AxisEnumeration(class_uri="http://example.org/Bond", class_label="Bond", source_ontology="FIBO", relevance="high"),
                ],
            ),
        ],
    )


def test_sample_axes_returns_sampled_axes():
    import random
    random.seed(42)
    profile = _make_profile()
    samples = sample_axes(profile, n=5)
    assert len(samples) > 0
    for sample in samples:
        assert len(sample) == 2  # two axes
        for sa in sample:
            assert isinstance(sa, SampledAxis)
            assert sa.role in ("agent", "instrument")


def test_sample_axes_deduplicates():
    # One enumeration per axis → only 1 unique combination possible
    profile = DomainContextProfile(
        risk_id="r1", risk_name="R", policy_concept="P",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/A",
                cco_class_label="A",
                role="agent",
                enumerations=[_enum("high")],
            ),
        ],
    )
    samples = sample_axes(profile, n=10)
    assert len(samples) == 1


def test_sample_axes_skips_empty_axes():
    profile = DomainContextProfile(
        risk_id="r1", risk_name="R", policy_concept="P",
        axes=[
            DomainContextAxis(
                cco_class_uri="http://example.org/A",
                cco_class_label="A",
                role="agent",
                enumerations=[_enum("high")],
            ),
            DomainContextAxis(
                cco_class_uri="http://example.org/B",
                cco_class_label="B",
                role="object",
                enumerations=[],  # empty — should be skipped
            ),
        ],
    )
    samples = sample_axes(profile, n=5)
    for sample in samples:
        assert len(sample) == 1  # only the non-empty axis
        assert sample[0].role == "agent"


def test_sample_axes_reproducible_with_seed():
    import random
    profile = _make_profile()
    random.seed(99)
    samples_a = sample_axes(profile, n=5)
    random.seed(99)
    samples_b = sample_axes(profile, n=5)
    assert samples_a == samples_b


def test_build_prompt_returns_messages():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            role="agent",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_build_prompt_system_message_content():
    messages = build_prompt("X", "Y", "Z", [])
    system = messages[0]["content"]
    assert "red-team scenario writer" in system
    assert "subtlety" in system.lower()


def test_build_prompt_user_message_has_policy():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            role="agent",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("Fraud", "About fraud", "Financial Fraud", axes)
    user = messages[1]["content"]
    assert "Fraud" in user
    assert "About fraud" in user
    assert "Financial Fraud" in user


def test_build_prompt_user_message_has_axes():
    axes = [
        SampledAxis(
            cco_class_uri="http://example.org/Person",
            cco_class_label="Person",
            role="agent",
            sampled_uri="http://example.org/Manager",
            sampled_label="Manager",
            source_ontology="FIBO",
            relevance="high",
        ),
        SampledAxis(
            cco_class_uri="http://example.org/Instrument",
            cco_class_label="Instrument",
            role="instrument",
            sampled_uri="http://example.org/Bond",
            sampled_label="Bond",
            source_ontology="FIBO",
            relevance="high",
        ),
    ]
    messages = build_prompt("X", "Y", "Z", axes)
    user = messages[1]["content"]
    assert "agent" in user
    assert "Manager" in user
    assert "Person" in user
    assert "instrument" in user
    assert "Bond" in user
