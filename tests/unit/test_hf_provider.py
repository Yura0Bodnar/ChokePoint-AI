"""HFInferenceProvider's response_format downgrade ladder, mocked with respx.

No network: respx intercepts the httpx transport that huggingface_hub uses.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.providers.base import LLMProvider
from chokepoint.agent.providers.hf_inference import HFInferenceProvider

MODEL = "Qwen/Qwen2.5-7B-Instruct"
MESSAGES = [{"role": "user", "content": "hi"}]
BASE_URL = "https://llm.test/v1"


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


def _sent_formats(route: respx.Route) -> list[str | None]:
    """Classify each request's response_format by *what it enforces*, not its label.

    huggingface_hub rewrites the OpenAI-style ``json_schema`` request into the
    provider's native dialect: TGI / hf-inference gets
    ``{"type": "json_object", "value": <schema>}``, Fireworks/Cohere get
    ``{"type": "json_object", "schema": ...}``, Together keeps ``json_schema``.
    Any of those carries our schema and counts as "json_schema" here.
    """
    out: list[str | None] = []
    for call in route.calls:
        body = json.loads(call.request.content)
        fmt = body.get("response_format")
        if not fmt:
            out.append(None)
        elif fmt.get("type") == "json_schema" or any(k in fmt for k in ("value", "schema")):
            out.append("json_schema")
        else:
            out.append(fmt["type"])
    return out


def _sent_schema(route: respx.Route, index: int = 0) -> dict[str, object]:
    fmt = json.loads(route.calls[index].request.content)["response_format"]
    if "json_schema" in fmt:
        return fmt["json_schema"]["schema"]  # type: ignore[no-any-return]
    return fmt.get("value") or fmt["schema"]  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _allow_mocked_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Developers often export HF_HUB_OFFLINE=1; the library then refuses even
    # respx-intercepted requests. Every request in this module is mocked, so
    # the guard is safe to lift here and only here.
    import huggingface_hub.constants as constants

    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", False)


def test_satisfies_protocol() -> None:
    assert isinstance(_provider(), LLMProvider)


@respx.mock
def test_json_schema_accepted_first_try() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(return_value=_ok('{"a": 1}'))
    p = _provider()
    assert p.chat(MESSAGES) == '{"a": 1}'
    assert _sent_formats(route) == ["json_schema"]
    assert p.last_mode == "json_schema"
    assert p.supports_structured is True

    body = json.loads(route.calls[0].request.content)
    assert "event_type" in _sent_schema(route)["properties"]  # type: ignore[index]
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 512


@respx.mock
def test_downgrades_to_json_object_on_400() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(
        side_effect=[
            httpx.Response(400, json={"error": "response_format not supported"}),
            _ok("{}"),
        ]
    )
    p = _provider()
    assert p.chat(MESSAGES) == "{}"
    assert _sent_formats(route) == ["json_schema", "json_object"]
    assert p.last_mode == "json_object"
    assert p.supports_structured is False  # remembered: next call skips json_schema


@respx.mock
def test_downgrades_all_the_way_to_bare_prompt() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(
        side_effect=[httpx.Response(422), httpx.Response(400), _ok("bare")]
    )
    p = _provider()
    assert p.chat(MESSAGES) == "bare"
    assert _sent_formats(route) == ["json_schema", "json_object", None]
    assert p.last_mode == "none"


@respx.mock
def test_remembers_unsupported_schema_across_calls() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(
        side_effect=[httpx.Response(400), _ok("1"), _ok("2")]
    )
    p = _provider()
    p.chat(MESSAGES)
    p.chat(MESSAGES)
    assert _sent_formats(route) == ["json_schema", "json_object", "json_object"]


@respx.mock
def test_supports_structured_false_skips_json_schema() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(return_value=_ok("x"))
    p = _provider(supports_structured=False)
    p.chat(MESSAGES)
    assert _sent_formats(route) == ["json_object"]


@respx.mock
def test_structured_false_sends_no_response_format() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(return_value=_ok("x"))
    _provider().chat(MESSAGES, structured=False)
    assert _sent_formats(route) == [None]


@pytest.mark.parametrize("status", [401, 402, 403, 404, 429, 500, 503])
@respx.mock
def test_non_downgradable_errors_propagate(status: int) -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(return_value=httpx.Response(status))
    with pytest.raises(HfHubHTTPError) as info:
        _provider().chat(MESSAGES)
    assert info.value.response.status_code == status
    assert len(route.calls) == 1  # no silent retry on auth/quota/server errors


@respx.mock
def test_400_on_bare_prompt_propagates() -> None:
    route = respx.post(url__regex=r".*/chat/completions$").mock(return_value=httpx.Response(400))
    with pytest.raises(HfHubHTTPError):
        _provider().chat(MESSAGES)
    assert _sent_formats(route) == ["json_schema", "json_object", None]


@respx.mock
def test_network_errors_propagate() -> None:
    respx.post(url__regex=r".*/chat/completions$").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(httpx.ConnectError):
        _provider().chat(MESSAGES)


@respx.mock
def test_null_content_becomes_empty_string() -> None:
    respx.post(url__regex=r".*/chat/completions$").mock(return_value=_ok(None))  # type: ignore[arg-type]
    assert _provider().chat(MESSAGES) == ""
