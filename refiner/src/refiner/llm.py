import threading
from dataclasses import dataclass, field

import instructor
from openai import OpenAI


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "none"
    temperature: float = 0.3
    max_retries: int = 3
    max_tokens: int = 8192
    max_concurrent: int = 1


@dataclass
class TokenTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    per_stage: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, usage, stage: str | None = None) -> None:
        if usage is None:
            return
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        tt = getattr(usage, "total_tokens", 0) or 0
        with self._lock:
            self.prompt_tokens += pt
            self.completion_tokens += ct
            self.total_tokens += tt
            self.calls += 1
            if stage:
                s = self.per_stage.setdefault(stage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0})
                s["prompt_tokens"] += pt
                s["completion_tokens"] += ct
                s["total_tokens"] += tt
                s["calls"] += 1

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "per_stage": dict(self.per_stage),
        }


def create_client(
    config: LLMConfig,
    tracker: TokenTracker | None = None,
) -> instructor.Instructor:
    client = instructor.from_openai(
        OpenAI(base_url=config.base_url, api_key=config.api_key),
        mode=instructor.Mode.JSON,
    )
    if tracker is not None:
        _wrap_with_tracking(client, tracker)
    return client


def _wrap_with_tracking(client: instructor.Instructor, tracker: TokenTracker) -> None:
    original_create = client.chat.completions.create

    def tracked_create(**kwargs):
        result, completion = client.chat.completions.create_with_completion(**kwargs)
        tracker.add(getattr(completion, "usage", None))
        return result

    client.chat.completions.create = tracked_create
