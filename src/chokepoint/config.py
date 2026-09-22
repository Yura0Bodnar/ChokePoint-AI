"""Application settings, loaded from environment variables / .env.

See ARCHITECTURE_AND_PLAN.md §16.1 for the full variable reference.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"
    demo_mode: bool = False

    llm_provider: str = "stub"  # hf | local | stub — see agent/providers/factory.py
    hf_token: str = ""
    hf_model: str = "openai/gpt-oss-20b"  # measured in docs/PROMPTS.md §3
    hf_inference_provider: str = "auto"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 512
    llm_max_retries: int = 3
    llm_failover_to_local: bool = True  # hf → local on 402 / network failure
    local_model: str = "Qwen/Qwen2.5-1.5B-Instruct"  # P2.8 CPU fallback
    local_device: str = "cpu"
    graph_backend: str = "networkx"  # only "networkx" is implemented

    sim_max_hops: int = 4
    sim_decay: float = 0.75
    sim_min_impact: float = 0.02

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
