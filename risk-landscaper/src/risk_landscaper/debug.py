import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_call_counter = 0
_counter_lock = threading.Lock()
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
    with _counter_lock:
        _call_counter += 1
        call_num = _call_counter

    # Build slug from context
    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    # Extract response data
    if hasattr(response, "model_dump"):
        response_data = response.model_dump()
    elif isinstance(response, list):
        response_data = [r.model_dump() if hasattr(r, "model_dump") else r for r in response]
    else:
        response_data = str(response)

    # JSON file
    if _debug_dir is not None:
        entry = {
            "call_number": call_num,
            "stage": stage,
            "messages": messages,
            "response": response_data,
        }
        if context:
            entry["context"] = context

        filename = f"{call_num:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug log written to %s", path)


def log_event(
    stage: str,
    data: dict,
    *,
    context: dict | None = None,
) -> None:
    """Log a non-LLM pipeline event (e.g. candidate tier reporting)."""
    global _call_counter
    with _counter_lock:
        _call_counter += 1
        call_num = _call_counter

    slug = ""
    if context:
        for key in ("policy_concept", "risk_name", "risk_id"):
            if key in context:
                slug = "-" + context[key].lower().replace(" ", "-").replace("/", "-")[:40]
                break

    if _debug_dir is not None:
        entry = {
            "call_number": call_num,
            "stage": stage,
            "messages": [],
            "response": data,
        }
        if context:
            entry["context"] = context

        filename = f"{call_num:02d}-{stage}{slug}.json"
        path = _debug_dir / filename
        path.write_text(json.dumps(entry, indent=2, default=str))
        logger.debug("Debug event written to %s", path)
