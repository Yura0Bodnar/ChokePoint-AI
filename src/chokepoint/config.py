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

    llm_provider: str = "stub"  # hf | local | stub — real values arrive with P2's PR
    graph_backend: str = "networkx"  # networkx | kuzu — real values arrive with P1's PR

    sim_max_hops: int = 4
    sim_decay: float = 0.75
    sim_min_impact: float = 0.02

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
