import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_call_counter = 0
_debug_dir: Path | None = None


def configure(debug_dir: Path | None) -> None:
    global _debug_dir, _call_counter
    _debug_dir = debug_dir
    _call_counter = 0
    if _debug_dir:
        _debug_dir.mkdir(parents=True, exist_ok=True)


def log_call(
    stage: str,
    messages: list[dict],
    response,
    *,
    context: dict | None = None,
) -> None:
    global _call_counter
    _call_counter += 1

    # Build slug from context (reused for JSON filename and span name)
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-")[:40]
                break

    # Extract response data
    if hasattr(response, "model_dump"):
        response_data = response.model_dump()
    elif isinstance(response, list):
        response_data = [r.model_dump() if hasattr(r, "model_dump") else r for r in response]
    else:
        response_data = str(response)

    # JSON file (existing behavior)
    if _debug_dir is not None:
        entry = {
            "call_number": _call_counter,
            "stage": stage,
            "messages": messages,
            "response": response_data,
        }
        if context:
            entry["context"] = context

        filename = f"{_call_counter:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug log written to %s", path)

    # MLflow tracing (conditional)
    try:
        import mlflow
        if mlflow.active_run():
            span = mlflow.start_span(name=f"{stage}{slug}")
            span.set_inputs({"messages": messages})
            span.set_outputs({"response": response_data})
            if context:
                span.set_attributes(context)
            span.end()
    except ImportError:
        pass
    except Exception:
        logger.debug("MLflow span creation failed", exc_info=True)
