import random

from refiner.benign_frames import (
    BENIGN_FRAMES,
    DEFAULT_BENIGN_WEIGHTS,
    BenignFrame,
    select_benign_frame,
    resolve_slot_label,
)


def test_frame_registry_has_five_frames():
    assert len(BENIGN_FRAMES) == 5
    expected = {"routine_practice", "training_education", "compliance_documentation",
                "applied_research", "client_service"}
    assert set(BENIGN_FRAMES.keys()) == expected


def test_all_frames_have_required_fields():
    for name, frame in BENIGN_FRAMES.items():
        assert frame.name == name
        assert len(frame.description) > 50, f"{name} description too short"
        assert len(frame.examples) >= 1, f"{name} needs at least one example"
        assert len(frame.slot_labels) >= 3, f"{name} needs slot labels"


def test_default_weights_match_registry():
    assert set(DEFAULT_BENIGN_WEIGHTS.keys()) == set(BENIGN_FRAMES.keys())
    for w in DEFAULT_BENIGN_WEIGHTS.values():
        assert w > 0


def test_select_benign_frame_returns_valid_frame():
    random.seed(42)
    frame = select_benign_frame(DEFAULT_BENIGN_WEIGHTS)
    assert isinstance(frame, BenignFrame)
    assert frame.name in BENIGN_FRAMES


def test_select_benign_frame_respects_extreme_weights():
    random.seed(42)
    weights = {name: 0.0 for name in BENIGN_FRAMES}
    weights["client_service"] = 1.0
    for _ in range(20):
        frame = select_benign_frame(weights)
        assert frame.name == "client_service"


def test_select_benign_frame_falls_back_on_all_zero():
    frame = select_benign_frame({name: 0.0 for name in BENIGN_FRAMES})
    assert frame.name == "routine_practice"


def test_select_benign_frame_with_affinity_boosts():
    random.seed(1)
    weights = {name: 1.0 for name in BENIGN_FRAMES}
    counts = {name: 0 for name in BENIGN_FRAMES}
    for _ in range(500):
        frame = select_benign_frame(weights, risk_name="Patient Privacy Clinical")
        counts[frame.name] += 1
    # compliance_documentation mirrors delegated_authority affinities (privacy, medical, patient, clinical)
    assert counts["compliance_documentation"] > 130


def test_select_benign_frame_without_affinity_is_roughly_uniform():
    random.seed(42)
    counts = {name: 0 for name in BENIGN_FRAMES}
    for _ in range(1000):
        frame = select_benign_frame(DEFAULT_BENIGN_WEIGHTS, risk_name="generic risk")
        counts[frame.name] += 1
    for name, count in counts.items():
        assert 100 < count < 300, f"{name}: {count} not roughly uniform"


def test_resolve_slot_label_known_category():
    frame = BENIGN_FRAMES["routine_practice"]
    assert resolve_slot_label(frame, "Role") == "practitioner"
    assert resolve_slot_label(frame, "Process") == "routine task"


def test_resolve_slot_label_unknown_category():
    frame = BENIGN_FRAMES["routine_practice"]
    assert resolve_slot_label(frame, "UnknownCategory") is None


def test_resolve_slot_label_empty_category():
    frame = BENIGN_FRAMES["routine_practice"]
    assert resolve_slot_label(frame, "") is None


def test_resolve_slot_label_varies_by_frame():
    label_routine = resolve_slot_label(BENIGN_FRAMES["routine_practice"], "Agent")
    label_research = resolve_slot_label(BENIGN_FRAMES["applied_research"], "Agent")
    assert label_routine != label_research
    assert label_routine == "practitioner"
    assert label_research == "researcher"


def test_frame_examples_are_not_empty_strings():
    for name, frame in BENIGN_FRAMES.items():
        for i, ex in enumerate(frame.examples):
            assert len(ex) > 20, f"{name} example {i} too short"
