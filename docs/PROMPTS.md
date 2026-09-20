# Prompts, JSON enforcement, and the HF support matrix

Owner: Person 2 (Agent & LLM). Companion to ARCHITECTURE_AND_PLAN.md §7.

## 1. The ladder, as implemented

| Layer | Module | What it does | Exercised by |
|---|---|---|---|
| gate | `agent/gate.py` | ~75 logistics keywords, word-boundary regex; drops irrelevant docs before any token is spent | `tests/unit/test_gate.py` (12/12 irrelevant headlines dropped = 100 %, bar is ≥ 80 %) |
| ① schema-constrained decoding | `agent/providers/hf_inference.py` + `agent/schema.py` (HF) · `agent/providers/local_hf.py` (local, prompt-only + `{` prefill) · `agent/providers/failover.py` (hf → local) | `response_format = json_schema` built from `DisruptionEvent.model_json_schema()`; on a 400/422 rejection downgrades to `json_object`, then to bare prompt; records `last_mode` and flips `supports_structured` | `tests/unit/test_hf_provider.py` (respx-mocked, no network) |
| ② prompt | `agent/prompts.py` | versioned system prompt with the schema inlined, 3 few-shot pairs, body truncated to 1 200 chars, `temperature = 0` | `tests/unit/test_extractor.py::test_prompt_sent_to_provider_*` |
| ③ hygiene | `agent/parser.py::extract_json_blob` | strips ``` fences and prose, keeps the outermost `{…}` | `tests/unit/test_parser.py` |
| ④ repair | `agent/parser.py::load_json_lenient` | `json.loads`, then `json_repair` on failure (trailing commas, single quotes, `None`) | `tests/unit/test_parser.py` |
| validate | `agent/parser.py::parse_event` | `DisruptionEvent.model_validate`; raises `ValidationError` / `JSONDecodeError`, never returns a wrong shape | `tests/unit/test_parser.py` |
| retry | `agent/extractor.py` | up to 3 attempts; the exact error text is fed back as a repair turn | `test_retry_after_*` |
| fallback | `agent/extractor.py::_fallback_extract` | keyword heuristic, `confidence = 0.25`, `extractor_version = "fallback-heuristic-v1"`; never raises | `test_fallback_*` |
| ⑤ resolution | `agent/resolver.py` + `agent/aliases.yaml` | exact alias → `difflib` close match (cutoff 0.85) → `None` | `tests/unit/test_resolver.py` |

Person 3's orchestrator sets `SimulationResult.degraded = True` when
`event.extractor_version.startswith("fallback")`. No new contract field.

## 2. Prompt versions

| Version | Status | System prompt | Few-shot | Golden-set score |
|---|---|---|---|---|
| `v1` | current | `SYSTEM_V1` — single job, JSON-only rule, enum listed verbatim, severity/confidence rubric, schema inlined | 3 pairs: single-location strike (Hamburg); multi-location conflict (Red Sea / Suez / Bab el-Mandeb); `affected_goods = []` fog closure (Constanta) | not yet scored — `tests/eval/test_extraction_quality.py` is P2.5 and `golden_events.json` is still empty |

Rule: never edit a version in place once it has a recorded score. Add
`SYSTEM_V2` / `FEW_SHOT_V2`, register them in `prompts.py`, bump
`PROMPT_VERSION`, and add a row here.

Successful extractions carry `extractor_version = "<provider>-<prompt version>"`
(e.g. `hf-v1`, `stub-v1`), so a scored run can always be traced to its prompt.

## 3. HF Inference support matrix (P2.2)

Measured 2026-09-20 with a free (non-PRO) account, `HF_INFERENCE_PROVIDER=auto`,
`huggingface_hub 1.32.0`, the real `SYSTEM_V1` + few-shot prompt (~1.5 k input
tokens), 2 repeats per cell. ✓ = HTTP 200 **and** `parse_event` accepted the
output; ~ = accepted but invalid; ✗ = rejected.

| Model | Provider | `json_schema` | `json_object` | Latency (p50) | Notes |
|---|---|---|---|---|---|
| `openai/gpt-oss-20b` | auto | ✗ HTTP 400 | **✓** | **0.57 s** | fastest working combination → new `HF_MODEL` default. `json_schema` rejected by the routed provider; ladder auto-downgrades to `json_object` and remembers it |
| `meta-llama/Llama-3.1-8B-Instruct` | auto | ✗ HTTP 405 | ✓ | 3.59 s (json_object), 3.08 s (bare) | works, 6× slower than gpt-oss-20b; gated model |
| `Qwen/Qwen2.5-7B-Instruct` | auto | ✗ | ✗ | — | HTTP 400 `model_not_supported`: only on `featherless-ai` / `together`, which are not enabled for this account |
| `mistralai/Mistral-7B-Instruct-v0.3` | auto | ✗ | ✗ | — | same: only on `novita`, not enabled |
| `Qwen/Qwen2.5-1.5B-Instruct` | auto | ✗ | ✗ | — | same: only on `featherless-ai`. Irrelevant for P2.8, which runs it locally |
| `openai/gpt-oss-120b`, `Llama-3.3-70B`, `Qwen3-32B`, `Qwen2.5-72B` | auto | ? | ? | — | not measured: HTTP 402 **credits depleted** before these rows ran |

**No model/provider pair accepted `json_schema` on this account.** Layer ① in
practice means `json_object` (syntactic JSON guaranteed, schema conformance
not) plus layers ②–④ and Pydantic. Both working models produced a valid
`DisruptionEvent` on the first attempt in that mode.

### Two findings that change the plan

1. **Free credits are tiny.** The whole monthly included quota was gone after
   roughly six successful ~1.5 k-token calls (some may have been used earlier).
   Every further call returns HTTP 402 *"You have depleted your monthly
   included credits"*. For the demo we need one of: a few dollars of pre-paid
   credits on the demo account, a PRO subscription (20× quota), or the P2.8
   local `Qwen2.5-1.5B` fallback. P2.8 is therefore not optional.
2. **"auto" only sees the providers enabled on the account.** Check
   hf.co/settings/inference-providers; enabling `together` / `featherless-ai`
   / `novita` would make the original Qwen/Mistral candidates callable.

Re-run when credits exist (`HF_MATRIX_MODELS` overrides the candidate list):

```bash
export HF_TOKEN=hf_xxx
unset HF_HUB_OFFLINE
HF_MATRIX_MODELS="openai/gpt-oss-20b,meta-llama/Llama-3.1-8B-Instruct" \
  uv run pytest tests/live/test_hf_support_matrix.py -m live -s
```

### What we do know without a token (verified against `huggingface_hub 1.32.0`)

The client does **not** send our `json_schema` request verbatim. It rewrites
it into each provider's native dialect before the HTTP call:

| Route | Wire format the provider actually receives |
|---|---|
| `hf-inference` / any `base_url` (TGI, vLLM) | `{"type": "json_object", "value": <schema>}` — TGI grammar mode |
| `fireworks-ai`, `cohere` | `{"type": "json_object", "schema": <schema>}` |
| `together` | `{"type": "json_schema", "schema": <schema>}` |
| other providers | passed through as OpenAI-style `json_schema` |

Consequences:

* A provider that "rejects `json_schema`" will do so with a 400/422 on the
  rewritten body, which is exactly what the downgrade ladder catches.
* The unit tests classify a request as schema-constrained by *whether a schema
  travelled with it*, not by the `type` label.
* `strict: true` is forwarded but only OpenAI-style routes honour it. The
  Pydantic schema is not strict-mode compliant anyway (optional fields, no
  `additionalProperties: false`); the parser + validator are the real guarantee.

## 4. Which ladder layer real HF traffic has exercised

Real traffic (matrix run above) exercised layer ① in `json_object` mode on
`gpt-oss-20b` and `Llama-3.1-8B`, the `json_schema → json_object` downgrade on
a real 400/405, layer ② (the v1 prompt), and layers ③–④ + validation on the
returned text (both parsed first try). Layer ⑤, the retry loop, and the
fallback have only been driven by `StubLLMProvider` fixtures and respx mocks.

## 5. Manual sanity check (once a token exists)

```bash
export HF_TOKEN=hf_xxx; unset HF_HUB_OFFLINE
uv run python -c "
from chokepoint.agent.providers.hf_inference import HFInferenceProvider
from chokepoint.agent.prompts import build_messages
p = HFInferenceProvider(model='openai/gpt-oss-20b', token='$HF_TOKEN')
print(p.chat(build_messages('Strike halts operations at Hamburg Port', 'Dockworkers walked out today...')))
print('mode:', p.last_mode)
"
```

Expected: a single JSON object matching `DisruptionEvent`, and `mode: json_object`.

## 6. Local CPU fallback (P2.8) — measured

`LocalHFProvider` (`agent/providers/local_hf.py`) runs `Qwen/Qwen2.5-1.5B-Instruct`
through `transformers` with greedy decoding and a `{` assistant prefill.
Dependencies live in the `local` dependency group, so CI and the Docker image
never install torch:

```bash
uv sync --group local                       # torch + transformers (~1 GB)
HF_HUB_OFFLINE=0 uv run hf download Qwen/Qwen2.5-1.5B-Instruct   # ~3 GB, once
HF_HUB_OFFLINE=1 uv run pytest tests/local -m local -s              # proves it works offline
```

Measured 2026-09-20 on an Apple M-series laptop (10 cores, 16 GB), fp32,
**with `HF_HUB_OFFLINE=1`** (no network at all), real `SYSTEM_V1` prompt:

| Device | Weight load | Extraction latency | Result |
|---|---|---|---|
| `cpu` (default) | 19.5 s | 15.5 s / 17.0 s / 21.2 s | 3/3 articles → valid `DisruptionEvent` on attempt 1, `extractor_version = local-v1`, all locations resolved (`port_hamburg`, `chokepoint_red_sea` + `chokepoint_suez`, `port_constanta`) |
| `mps` (Apple GPU) | 9.4 s | 13.3 s / 17.5 s | same output; only marginally faster, so `cpu` stays the default (`LOCAL_DEVICE=mps` to opt in) |

Latency is dominated by prefill of the ~1.5 k-token prompt (schema + 3
few-shot pairs), not by generation. A smaller `SYSTEM_V2` without the inlined
schema would roughly halve it on the local path; measure before switching.

Quality note: the 1.5B model labelled the Red Sea attacks `accident` where
`conflict` is right. Types, severities and locations were otherwise sensible.
That is a P2.5 (golden-set) concern, not a reliability one.

### Automatic failover

`FailoverProvider` (`agent/providers/failover.py`) wraps HF → local. Any
`HfHubHTTPError` (402 credits depleted, 429, 5xx) or transport error on the
primary switches to the local model for the rest of the process and records
`failover_reason`. `name` follows the active provider, so events carry
`hf-v1` or `local-v1` accordingly. Programming errors still propagate.

### Wiring (Integration Day)

`agent/providers/factory.py::build_provider(settings)` maps `LLM_PROVIDER`:

| `LLM_PROVIDER` | Provider |
|---|---|
| `hf` | `FailoverProvider(HFInferenceProvider, LocalHFProvider)` — local weights load lazily, only if HF fails. `LLM_FAILOVER_TO_LOCAL=false` for bare HF |
| `local` | `LocalHFProvider` |
| `stub` | `StubLLMProvider` replaying a canned Hamburg strike (no fixtures dir needed) |

`Settings` now carries `hf_token`, `hf_model`, `hf_inference_provider`,
`llm_temperature`, `llm_max_tokens`, `llm_max_retries`, `llm_failover_to_local`,
`local_model`, `local_device` (§16.1 variables owned by P2).
