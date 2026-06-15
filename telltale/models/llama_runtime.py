from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Callable
from urllib import error, request


DEFAULT_NEMOTRON_MODEL_NAME = "NVIDIA Nemotron 3 Nano 4B GGUF"
DEFAULT_NEMOTRON_GGUF_REPO = "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF"
DEFAULT_NEMOTRON_GGUF_FILE = "NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf"
DEFAULT_ZERO_GPU_MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16"
DEFAULT_LLAMA_SERVER_URL = "http://127.0.0.1:8080"

try:
    import spaces
except ImportError:  # pragma: no cover - local dev and tests usually do not install spaces
    spaces = None


class RuntimeConfigurationError(RuntimeError):
    """Raised when a local model runtime is requested without required config."""


@dataclass(frozen=True)
class RuntimeSettings:
    mode: str = "mock"
    model_name: str = DEFAULT_NEMOTRON_MODEL_NAME
    gguf_path: str | None = None
    model_repo: str = DEFAULT_NEMOTRON_GGUF_REPO
    model_file: str = DEFAULT_NEMOTRON_GGUF_FILE
    zero_gpu_model_id: str = DEFAULT_ZERO_GPU_MODEL_ID
    server_url: str = DEFAULT_LLAMA_SERVER_URL
    model_alias: str = "telltale-agent"
    context_size: int = 4096
    max_tokens: int = 220
    temperature: float = 0.65
    seed: int | None = None
    request_timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        seed_text = os.getenv("TELLTALE_SEED")
        default_mode = "zero_gpu" if os.getenv("SPACE_ID") else "mock"
        return cls(
            mode=_normalize_mode(os.getenv("TELLTALE_MODEL_MODE", default_mode)),
            model_name=os.getenv("TELLTALE_MODEL_NAME", DEFAULT_NEMOTRON_MODEL_NAME),
            gguf_path=os.getenv("TELLTALE_GGUF_PATH") or None,
            model_repo=os.getenv("TELLTALE_MODEL_REPO", DEFAULT_NEMOTRON_GGUF_REPO),
            model_file=os.getenv("TELLTALE_MODEL_FILE", DEFAULT_NEMOTRON_GGUF_FILE),
            zero_gpu_model_id=os.getenv("TELLTALE_ZERO_GPU_MODEL_ID", DEFAULT_ZERO_GPU_MODEL_ID),
            server_url=os.getenv("TELLTALE_LLAMA_SERVER_URL", DEFAULT_LLAMA_SERVER_URL),
            model_alias=os.getenv("TELLTALE_MODEL_ALIAS", "telltale-agent"),
            context_size=int(os.getenv("TELLTALE_CONTEXT_SIZE", "4096")),
            max_tokens=int(os.getenv("TELLTALE_MAX_TOKENS", "220")),
            temperature=float(os.getenv("TELLTALE_TEMPERATURE", "0.65")),
            seed=int(seed_text) if seed_text else None,
            request_timeout_seconds=float(os.getenv("TELLTALE_REQUEST_TIMEOUT_SECONDS", "120")),
        )


@dataclass(frozen=True)
class LlamaRuntimeConfig:
    model_path: str | None = None
    repo_id: str | None = None
    filename: str | None = None
    zero_gpu_model_id: str = DEFAULT_ZERO_GPU_MODEL_ID
    server_url: str = DEFAULT_LLAMA_SERVER_URL
    model_alias: str = "telltale-agent"
    context_size: int = 4096
    max_tokens: int = 220
    temperature: float = 0.65
    seed: int | None = None
    n_gpu_layers: int = 0
    model_name: str = DEFAULT_NEMOTRON_MODEL_NAME
    verbose: bool = False
    request_timeout_seconds: float = 120.0

    def to_runtime_settings(self) -> RuntimeSettings:
        return RuntimeSettings(
            mode="llama_server",
            model_name=self.model_name,
            gguf_path=self.model_path,
            model_repo=self.repo_id or DEFAULT_NEMOTRON_GGUF_REPO,
            model_file=self.filename or DEFAULT_NEMOTRON_GGUF_FILE,
            zero_gpu_model_id=self.zero_gpu_model_id,
            server_url=self.server_url,
            model_alias=self.model_alias,
            context_size=self.context_size,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            seed=self.seed,
            request_timeout_seconds=self.request_timeout_seconds,
        )


@dataclass(frozen=True)
class GenerationResult:
    text: str
    latency_ms: int
    tokens_per_second: float | None
    metadata: dict[str, Any]


def _first_choice(output: dict[str, Any]) -> dict[str, Any]:
    choices = output.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return {}
    return choices[0]


def _choice_text(output: dict[str, Any]) -> str:
    choice = _first_choice(output)
    message = choice.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(choice.get("text") or choice.get("content") or "")


def _generation_metadata(output: dict[str, Any]) -> dict[str, Any]:
    choice = _first_choice(output)
    text = _choice_text(output)
    metadata: dict[str, Any] = {
        "finish_reason": choice.get("finish_reason"),
        "raw_text_length": len(text),
        "raw_text_stripped_length": len(text.strip()),
        "raw_text_repr": repr(text[:240]),
    }
    usage = output.get("usage")
    if isinstance(usage, dict):
        metadata["usage"] = usage
    return metadata


class LocalTextRuntime:
    """Text runtime backed by mock responses or an actual llama.cpp HTTP server."""

    def __init__(self, settings: RuntimeSettings | None = None):
        raw_settings = settings or RuntimeSettings.from_env()
        self.settings = RuntimeSettings(
            mode=_normalize_mode(raw_settings.mode),
            model_name=raw_settings.model_name,
            gguf_path=raw_settings.gguf_path,
            model_repo=raw_settings.model_repo,
            model_file=raw_settings.model_file,
            zero_gpu_model_id=raw_settings.zero_gpu_model_id,
            server_url=raw_settings.server_url.rstrip("/"),
            model_alias=raw_settings.model_alias,
            context_size=raw_settings.context_size,
            max_tokens=raw_settings.max_tokens,
            temperature=raw_settings.temperature,
            seed=raw_settings.seed,
            request_timeout_seconds=raw_settings.request_timeout_seconds,
        )
        self.last_generation_metadata: dict[str, Any] = {}
        if self.settings.mode not in {"mock", "llama_server", "zero_gpu"}:
            raise RuntimeConfigurationError(
                "TELLTALE_MODEL_MODE must be 'mock', 'llama_server', or 'zero_gpu'."
            )
        if self.settings.mode == "llama_server":
            self._ensure_server_is_reachable()
        self._zero_gpu_runtime: TransformersZeroGPURuntime | None = None

    @property
    def mode(self) -> str:
        return self.settings.mode

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> GenerationResult:
        started = time.perf_counter()
        if self.settings.mode == "mock":
            text = self._mock_response(prompt, context or {})
            latency_ms = int((time.perf_counter() - started) * 1000)
            return GenerationResult(text=text, latency_ms=latency_ms, tokens_per_second=None, metadata=self.metadata())

        if self.settings.mode == "zero_gpu":
            runtime = self._get_zero_gpu_runtime()
            text = runtime.generate(
                prompt,
                max_tokens=max_tokens or self.settings.max_tokens,
                temperature=temperature if temperature is not None else self.settings.temperature,
                seed=seed if seed is not None else self.settings.seed,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            token_count = len(text.split())
            tps = (token_count / (latency_ms / 1000)) if latency_ms > 0 else None
            self.last_generation_metadata = {
                "raw_text_length": len(text),
                "raw_text_stripped_length": len(text.strip()),
                "raw_text_repr": repr(text[:240]),
            }
            return GenerationResult(text=text, latency_ms=latency_ms, tokens_per_second=tps, metadata=self.metadata())

        output = self._post_json(
            "/v1/chat/completions",
            {
                "model": self.settings.model_alias,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens or self.settings.max_tokens,
                "temperature": temperature if temperature is not None else self.settings.temperature,
                "seed": seed if seed is not None else self.settings.seed,
                "response_format": {"type": "json_object"},
            },
        )
        self.last_generation_metadata = _generation_metadata(output)
        text = _choice_text(output)
        latency_ms = int((time.perf_counter() - started) * 1000)
        token_count = len(text.split())
        tps = (token_count / (latency_ms / 1000)) if latency_ms > 0 else None
        return GenerationResult(text=text, latency_ms=latency_ms, tokens_per_second=tps, metadata=self.metadata())

    def metadata(self) -> dict[str, Any]:
        return {
            "model_name": self.settings.model_name,
            "gguf_path": self.settings.gguf_path,
            "model_repo": self.settings.model_repo,
            "model_file": self.settings.model_file,
            "zero_gpu_model_id": self.settings.zero_gpu_model_id,
            "server_url": self.settings.server_url,
            "model_alias": self.settings.model_alias,
            "runtime_backend": self.settings.mode,
            "hardware_profile": os.getenv("TELLTALE_HARDWARE_PROFILE", "local_cpu"),
        }

    def _get_zero_gpu_runtime(self) -> "TransformersZeroGPURuntime":
        if self._zero_gpu_runtime is None:
            self._zero_gpu_runtime = TransformersZeroGPURuntime(
                model_id=self.settings.zero_gpu_model_id,
                model_name=self.settings.model_name,
            )
        return self._zero_gpu_runtime

    def _ensure_server_is_reachable(self) -> None:
        try:
            self._get_json("/v1/models")
        except RuntimeConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrap connection failures cleanly
            raise RuntimeConfigurationError(
                "TELLTALE_MODEL_MODE=llama_server requires a reachable llama.cpp "
                f"server at {self.settings.server_url}. Start llama-server first or set "
                "TELLTALE_LLAMA_SERVER_URL."
            ) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.settings.server_url}{path}"
        http_request = request.Request(url, method="GET")
        try:
            with request.urlopen(http_request, timeout=self.settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeConfigurationError(f"llama-server request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeConfigurationError("llama-server returned invalid JSON.") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.server_url}{path}"
        body = json.dumps({key: value for key, value in payload.items() if value is not None}).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.settings.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeConfigurationError(f"llama-server generation failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeConfigurationError(f"llama-server generation failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeConfigurationError("llama-server returned invalid generation JSON.") from exc

    def _mock_response(self, prompt: str, context: dict[str, Any]) -> str:
        action = str(context.get("suggested_action") or "check")
        amount = int(context.get("suggested_amount") or 0)
        agent_name = str(context.get("agent_name") or "The regular")
        player_utterance = str(context.get("player_utterance") or "").strip()
        if player_utterance:
            speech = f"{agent_name}: I heard that. The chips still decide."
            summary = f"Player used table talk: {player_utterance[:80]}"
        else:
            speech = f"{agent_name}: I will take the clean line."
            summary = "Played the solver-informed line without extra table pressure."
        return json.dumps(
            {
                "action": action,
                "amount": amount,
                "speech": speech,
                "honest_rationale": "The recommendation fits the current price and stack pressure.",
                "emotional_state": "focused",
                "memory_delta": {
                    "summary": summary,
                    "recent_dialogue_impressions": [player_utterance] if player_utterance else [],
                },
            }
        )


class LocalLlamaCppRuntime:
    """Compatibility wrapper for evals, backed by actual llama-server HTTP calls."""

    def __init__(self, config: LlamaRuntimeConfig):
        self.config = config
        self.runtime = LocalTextRuntime(config.to_runtime_settings())
        self.last_generation_metadata: dict[str, Any] = {}

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> str:
        result = self.runtime.generate(
            prompt,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
            seed=seed if seed is not None else self.config.seed,
        )
        self.last_generation_metadata = result.metadata
        return result.text


def _normalize_mode(mode: str) -> str:
    if mode == "llama_cpp":
        return "llama_server"
    return mode


def _gpu_decorator() -> Callable:
    if spaces is None:
        return lambda fn: fn
    return spaces.GPU(duration=120)


class TransformersZeroGPURuntime:
    """ZeroGPU-compatible text runtime using Transformers inside a Gradio Space."""

    _model = None
    _tokenizer = None

    def __init__(self, *, model_id: str, model_name: str):
        self.model_id = model_id
        self.model_name = model_name

    @_gpu_decorator()
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
    ) -> str:
        if seed is not None:
            try:
                import torch

                torch.manual_seed(seed)
            except ImportError:
                pass
        model, tokenizer = self._load_model()
        messages = [
            {
                "role": "system",
                "content": "Return only the requested compact JSON object. Do not include hidden reasoning.",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            inputs = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                enable_thinking=False,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(model.device)
        except TypeError:
            inputs = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(model.device)
        output_ids = model.generate(
            inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            eos_token_id=tokenizer.eos_token_id,
        )
        generated = output_ids[0][inputs.shape[-1] :]
        return str(tokenizer.decode(generated, skip_special_tokens=True)).strip()

    def _load_model(self):
        if TransformersZeroGPURuntime._model is not None and TransformersZeroGPURuntime._tokenizer is not None:
            return TransformersZeroGPURuntime._model, TransformersZeroGPURuntime._tokenizer
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeConfigurationError(
                "TELLTALE_MODEL_MODE=zero_gpu requires transformers, torch, and spaces."
            ) from exc
        tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            device_map="auto",
        )
        TransformersZeroGPURuntime._tokenizer = tokenizer
        TransformersZeroGPURuntime._model = model
        return model, tokenizer
