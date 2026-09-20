from __future__ import annotations

import pytest

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.providers import factory
from chokepoint.agent.providers.factory import build_provider
from chokepoint.agent.providers.failover import FailoverProvider
from chokepoint.agent.providers.hf_inference import HFInferenceProvider
from chokepoint.agent.providers.local_hf import LocalHFProvider
from chokepoint.agent.providers.stub import StubLLMProvider
from chokepoint.config import Settings
from chokepoint.contracts import RawDocument


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_stub_default_and_end_to_end(alias_index: dict[str, str], hamburg_doc: RawDocument) -> None:
    provider = build_provider(_settings())
    assert isinstance(provider, StubLLMProvider)
    event = ExtractionAgent(provider, alias_index).extract(hamburg_doc)
    assert event.locations[0].node_id == "port_hamburg"
    assert event.extractor_version == "stub-v1"


def test_local() -> None:
    provider = build_provider(_settings(llm_provider="local", local_model="x/y"))
    assert isinstance(provider, LocalHFProvider)
    assert provider.model_id == "x/y"
    assert provider.load_seconds is None  # nothing loaded yet


def test_hf_wrapped_in_failover_when_local_stack_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory, "local_stack_available", lambda: True)
    provider = build_provider(_settings(llm_provider="hf", hf_token="hf_x", hf_model="m/n"))
    assert isinstance(provider, FailoverProvider)
    assert isinstance(provider.active, HFInferenceProvider)
    assert provider.name == "hf"


def test_hf_bare_with_warning_when_torch_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The Docker/CI image: failover requested, but the local group is not installed.
    monkeypatch.setattr(factory, "local_stack_available", lambda: False)
    with caplog.at_level("WARNING"):
        provider = build_provider(_settings(llm_provider="hf", hf_token="hf_x"))
    assert isinstance(provider, HFInferenceProvider)
    assert "without local failover" in caplog.text


def test_hf_bare_when_failover_disabled() -> None:
    provider = build_provider(
        _settings(llm_provider="hf", hf_token="hf_x", llm_failover_to_local=False)
    )
    assert isinstance(provider, HFInferenceProvider)


def test_hf_requires_token() -> None:
    with pytest.raises(ValueError, match="HF_TOKEN"):
        build_provider(_settings(llm_provider="hf", hf_token=""))


def test_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown LLM_PROVIDER"):
        build_provider(_settings(llm_provider="gpt"))


def test_case_insensitive() -> None:
    assert isinstance(build_provider(_settings(llm_provider="STUB")), StubLLMProvider)
