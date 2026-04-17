from refiner.evaluate import (
    compute_pair_completeness,
    compute_frame_correspondence,
    compute_lexical_overlap,
)


def test_pair_completeness_perfect():
    rt_rows = [{"pair_id": "r1:0"}, {"pair_id": "r1:1"}]
    ut_rows = [{"pair_id": "r1:0"}, {"pair_id": "r1:1"}]
    result = compute_pair_completeness(rt_rows, ut_rows)
    assert result["completeness"] == 1.0
    assert result["total_pairs"] == 2
    assert result["missing_in_redteam"] == 0
    assert result["missing_in_utility"] == 0


def test_pair_completeness_missing_utility():
    rt_rows = [{"pair_id": "r1:0"}, {"pair_id": "r1:1"}]
    ut_rows = [{"pair_id": "r1:0"}]
    result = compute_pair_completeness(rt_rows, ut_rows)
    assert result["completeness"] == 0.5
    assert result["missing_in_utility"] == 1


def test_pair_completeness_empty():
    result = compute_pair_completeness([], [])
    assert result["completeness"] == 1.0
    assert result["total_pairs"] == 0


def test_frame_correspondence():
    rt_rows = [
        {"pair_id": "r1:0", "technique": "pretexting"},
        {"pair_id": "r1:1", "technique": "delegated_authority"},
    ]
    ut_rows = [
        {"pair_id": "r1:0", "technique": "routine_practice"},
        {"pair_id": "r1:1", "technique": "compliance_documentation"},
    ]
    result = compute_frame_correspondence(rt_rows, ut_rows)
    assert ("pretexting", "routine_practice") in result
    assert result[("pretexting", "routine_practice")] == 1
    assert result[("delegated_authority", "compliance_documentation")] == 1


def test_lexical_overlap():
    rt_rows = [
        {"pair_id": "r1:0", "generation_prompt": [{"role": "user", "content": "the cat sat on the mat"}]},
    ]
    ut_rows = [
        {"pair_id": "r1:0", "generation_prompt": [{"role": "user", "content": "the cat ran to the mat"}]},
    ]
    result = compute_lexical_overlap(rt_rows, ut_rows)
    assert 0.0 < result["mean_jaccard"] < 1.0
    assert len(result["per_pair"]) == 1


def test_lexical_overlap_empty():
    result = compute_lexical_overlap([], [])
    assert result["mean_jaccard"] == 0.0
    assert result["per_pair"] == []
