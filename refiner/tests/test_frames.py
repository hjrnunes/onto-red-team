import random

from refiner.frames import (
    FRAMES,
    DEFAULT_WEIGHTS,
    AdversarialFrame,
    select_frame,
    resolve_slot_label,
)


def test_frame_registry_has_five_frames():
    assert len(FRAMES) == 5
    expected = {"pretexting", "narrative_framing", "analytical_reframing",
                "delegated_authority", "comparative_benchmark"}
    assert set(FRAMES.keys()) == expected


def test_all_frames_have_required_fields():
    for name, frame in FRAMES.items():
        assert frame.name == name
        assert len(frame.description) > 50, f"{name} description too short"
        assert len(frame.examples) >= 1, f"{name} needs at least one example"
        assert len(frame.slot_labels) >= 3, f"{name} needs slot labels"


def test_default_weights_match_registry():
    assert set(DEFAULT_WEIGHTS.keys()) == set(FRAMES.keys())
    for w in DEFAULT_WEIGHTS.values():
        assert w > 0


def test_select_frame_returns_valid_frame():
    random.seed(42)
    frame = select_frame(DEFAULT_WEIGHTS)
    assert isinstance(frame, AdversarialFrame)
    assert frame.name in FRAMES


def test_select_frame_respects_extreme_weights():
    random.seed(42)
    weights = {name: 0.0 for name in FRAMES}
    weights["comparative_benchmark"] = 1.0
    for _ in range(20):
        frame = select_frame(weights)
        assert frame.name == "comparative_benchmark"


def test_select_frame_falls_back_on_all_zero():
    frame = select_frame({name: 0.0 for name in FRAMES})
    assert frame.name == "pretexting"


def test_select_frame_with_affinity_boosts():
    random.seed(1)
    # Run many selections with "fraud" in risk_name — pretexting has "fraud" affinity
    weights = {name: 1.0 for name in FRAMES}
    counts = {name: 0 for name in FRAMES}
    for _ in range(500):
        frame = select_frame(weights, risk_name="Financial Fraud Detection")
        counts[frame.name] += 1
    # pretexting should be selected more than uniform (100/500 = 20%)
    assert counts["pretexting"] > 130  # boosted well above uniform


def test_select_frame_without_affinity_is_roughly_uniform():
    random.seed(42)
    counts = {name: 0 for name in FRAMES}
    for _ in range(1000):
        frame = select_frame(DEFAULT_WEIGHTS, risk_name="generic risk")
        counts[frame.name] += 1
    # Each should be roughly 200 ± 50 with 5 frames
    for name, count in counts.items():
        assert 100 < count < 300, f"{name}: {count} not roughly uniform"


def test_resolve_slot_label_known_category():
    frame = FRAMES["pretexting"]
    assert resolve_slot_label(frame, "Role") == "professional role"
    assert resolve_slot_label(frame, "Agent") == "requesting party"


def test_resolve_slot_label_unknown_category():
    frame = FRAMES["pretexting"]
    assert resolve_slot_label(frame, "UnknownCategory") is None


def test_resolve_slot_label_empty_category():
    frame = FRAMES["pretexting"]
    assert resolve_slot_label(frame, "") is None


def test_resolve_slot_label_varies_by_frame():
    label_pretext = resolve_slot_label(FRAMES["pretexting"], "Agent")
    label_delegated = resolve_slot_label(FRAMES["delegated_authority"], "Agent")
    assert label_pretext != label_delegated
    assert label_pretext == "requesting party"
    assert label_delegated == "authority figure"


def test_frame_examples_are_not_empty_strings():
    for name, frame in FRAMES.items():
        for i, ex in enumerate(frame.examples):
            assert len(ex) > 20, f"{name} example {i} too short"
