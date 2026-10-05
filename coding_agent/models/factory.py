"""Create a model adapter from session configuration without storing credentials."""

import os

from coding_agent.models.anthropic import AnthropicBackend
from coding_agent.models.base import ModelBackend
from coding_agent.models.openai_compatible import OpenAICompatibleBackend


def create_model(config: dict) -> ModelBackend:
    model = config["model"]
    backend = model["backend"]
    if backend == "anthropic":
        return AnthropicBackend(
            model["name"], model["base_url"],
            os.getenv(model.get("api_key_env", "ANTHROPIC_API_KEY")),
            max_output_tokens=model.get("max_output_tokens", 4096),
        )
    if backend == "openai_compatible":
        key_name = model.get("api_key_env", "DEEPSEEK_API_KEY")
        key = os.getenv(key_name)
        if key is None and key_name == "DEEPSEEK_API_KEY":
            key = os.getenv("OPENAI_API_KEY")
        return OpenAICompatibleBackend(
            model["name"], model["base_url"], key,
            max_output_tokens=model.get("max_output_tokens", 8192),
            reasoning_effort=model.get("reasoning_effort"),
        )
    raise ValueError(f"Unknown model backend: {backend}")
