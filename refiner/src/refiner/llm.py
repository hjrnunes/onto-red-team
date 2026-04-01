from dataclasses import dataclass

import instructor
from openai import OpenAI


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "none"
    temperature: float = 0.3
    max_retries: int = 3
    max_tokens: int = 2048


def create_client(config: LLMConfig) -> instructor.Instructor:
    return instructor.from_openai(
        OpenAI(base_url=config.base_url, api_key=config.api_key),
        mode=instructor.Mode.JSON,
    )
