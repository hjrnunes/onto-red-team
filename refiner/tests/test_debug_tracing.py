from unittest.mock import MagicMock, patch
from refiner.debug import configure, log_call


def test_log_call_creates_span_when_mlflow_active(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    mock_mlflow.start_span.assert_called_once_with(name="classify")
    mock_span.set_inputs.assert_called_once()
    mock_span.set_outputs.assert_called_once()
    mock_span.end.assert_called_once()


def test_log_call_span_name_includes_slug(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call(
            "map_risks", [{"role": "user", "content": "test"}], "response",
            context={"policy_concept": "Illegal Activity"},
        )

    mock_mlflow.start_span.assert_called_once_with(name="map_risks-illegal-activity")


def test_log_call_sets_attributes_from_context(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_span = MagicMock()
    mock_mlflow.start_span.return_value = mock_span
    ctx = {"policy_concept": "Fraud", "num_candidates": 5}

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("anchor", [{"role": "user", "content": "test"}], "response", context=ctx)

    mock_span.set_attributes.assert_called_once_with(ctx)


def test_log_call_no_span_when_mlflow_inactive(tmp_path):
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = None

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    mock_mlflow.start_span.assert_not_called()


def test_log_call_no_span_when_mlflow_not_installed(tmp_path):
    configure(tmp_path)
    # Ensure mlflow is not importable
    with patch.dict("sys.modules", {"mlflow": None}):
        # Should not raise — graceful fallback
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    # Verify JSON file was still written
    files = list(tmp_path.glob("*.json"))
    assert len(files) >= 1


def test_log_call_json_still_written_with_mlflow(tmp_path):
    """Dual-write: JSON file AND span both created."""
    configure(tmp_path)
    mock_mlflow = MagicMock()
    mock_mlflow.active_run.return_value = MagicMock()
    mock_mlflow.start_span.return_value = MagicMock()

    with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
        log_call("classify", [{"role": "user", "content": "test"}], "response")

    files = list(tmp_path.glob("*.json"))
    assert len(files) >= 1
