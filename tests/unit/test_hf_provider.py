"""HFInferenceProvider is prompt-only: it never sends ``response_format``. Mocked with respx.

The free HF tier rejects ``response_format`` with an immediate HTTP 400, so the payload must
carry only model / messages / max_tokens / temperature, and every HTTP failure must reach
the caller after exactly one attempt. No network: respx intercepts the httpx transport.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.prompts import PROMPT_VERSION
from chokepoint.agent.providers.base import LLMProvider
from chokepoint.agent.providers.hf_inference import HFInferenceProvider

MODEL = "Qwen/Qwen2.5-7B-Instruct"
MESSAGES = [{"role": "user", "content": "hi"}]
BASE_URL = "https://llm.test/v1"
CHAT_URL = r".*/chat/completions$"


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": MODEL,
            "system_fingerprint": "",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def _provider(**kw: object) -> HFInferenceProvider:
    # An explicit base_url skips the hub's model→provider lookup, so the only
    # HTTP traffic is the chat/completions call that respx intercepts.
    return HFInferenceProvider(model=MODEL, token="hf_test", base_url=BASE_URL, **kw)  # type: ignore[arg-type]


def _payload(route: respx.Route, index: int = 0) -> dict[str, object]:
    return json.loads(route.calls[index].request.content)  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _allow_mocked_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Developers often export HF_HUB_OFFLINE=1; the library then refuses even
    # respx-intercepted requests. Every request in this module is mocked, so
    # the guard is safe to lift here and only here.
    import huggingface_hub.constants as constants

    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False)


def test_satisfies_protocol() -> None:
    assert isinstance(_provider(), LLMProvider)


def test_does_not_claim_decode_time_schema_enforcement() -> None:
    assert _provider().supports_structured is False


@respx.mock
def test_payload_is_prompt_only_with_no_response_format() -> None:
    route = respx.post(url__regex=CHAT_URL).mock(return_value=_ok('{"a": 1}'))
    assert _provider().chat(MESSAGES) == '{"a": 1}'

    assert len(route.calls) == 1
    body = _payload(route)
    assert "response_format" not in body
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 512


@pytest.mark.parametrize("structured", [True, False])
@respx.mock
def test_structured_flag_never_adds_response_format(structured: bool) -> None:
    route = respx.post(url__regex=CHAT_URL).mock(return_value=_ok("x"))
    _provider().chat(MESSAGES, structured=structured)
    assert "response_format" not in _payload(route)


@respx.mock
def test_generation_params_come_from_the_constructor() -> None:
    route = respx.post(url__regex=CHAT_URL).mock(return_value=_ok("x"))
    _provider(max_tokens=64, temperature=0.3).chat(MESSAGES)
    body = _payload(route)
    assert (body["max_tokens"], body["temperature"]) == (64, 0.3)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 405, 422, 429, 500, 503])
@respx.mock
def test_http_errors_propagate_after_a_single_call(status: int) -> None:
    route = respx.post(url__regex=CHAT_URL).mock(return_value=httpx.Response(status))
    with pytest.raises(HfHubHTTPError) as info:
        _provider().chat(MESSAGES)
    assert info.value.response.status_code == status
    assert len(route.calls) == 1  # a 400 is never "downgraded" and retried; nothing is swallowed


@respx.mock
def test_network_errors_propagate() -> None:
    respx.post(url__regex=CHAT_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(httpx.ConnectError):
        _provider().chat(MESSAGES)


@respx.mock
def test_null_content_becomes_empty_string() -> None:
    respx.post(url__regex=CHAT_URL).mock(return_value=_ok(None))  # type: ignore[arg-type]
    assert _provider().chat(MESSAGES) == ""


@respx.mock
def test_agent_end_to_end_sends_prompt_only_request_and_parses_a_fenced_reply(
    alias_index: dict[str, str],
) -> None:
    reply = (
        "Sure! Here is the event you asked for:\n"
        "```json\n"
        '{"event_type": "strike", "locations": [{"raw": "Hamburg Port", "country_iso2": "DE"}], '
        '"affected_goods": ["auto parts"], "severity": 3, "confidence": 0.9, '
        '"summary": "Dockworkers strike at Hamburg Port."}\n'
        "```\n"
        "Let me know if you need anything else."
    )
    route = respx.post(url__regex=CHAT_URL).mock(return_value=_ok(reply))

    event = ExtractionAgent(_provider(), alias_index).extract_text("Strike at Hamburg Port")

    assert len(route.calls) == 1
    body = _payload(route)
    assert "response_format" not in body
    system = body["messages"][0]["content"]  # type: ignore[index]
    assert "You must return ONLY valid JSON inside a ```json code block." in system
    assert event.locations[0].node_id == "port_hamburg"
    assert event.extractor_version == f"hf-{PROMPT_VERSION}"
