"""Old contextualize tests -- replaced by test_contextualize_v2.py."""
from refiner.stages.contextualize import contextualize, _ContextResponse, _Variation


def test_contextualize_module_loads():
    """Verify the contextualize module loads with new types."""
    assert callable(contextualize)
    assert hasattr(_ContextResponse, "model_fields")
    assert hasattr(_Variation, "model_fields")
