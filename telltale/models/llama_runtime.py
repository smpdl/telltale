from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any


DEFAULT_NEMOTRON_MODEL_NAME = "NVIDIA Nemotron 3 Nano 4B GGUF"


class RuntimeConfigurationError(RuntimeError):
    """Raised when a local model runtime is requested without required config."""


@dataclass(frozen=True)
class RuntimeSettings:
    mode: str = "mock"
    model_name: str = DEFAULT_NEMOTRON_MODEL_NAME
    gguf_path: str | None = None
    context_size: int = 4096
    max_tokens: int = 220
    temperature: float = 0.65
    seed: int | None = None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        seed_text = os.getenv("TELLTALE_SEED")
        return cls(
            mode=os.getenv("TELLTALE_MODEL_MODE", "mock"),
            model_name=os.getenv("TELLTALE_MODEL_NAME", DEFAULT_NEMOTRON_MODEL_NAME),
            gguf_path=os.getenv("TELLTALE_GGUF_PATH") or None,
            context_size=int(os.getenv("TELLTALE_CONTEXT_SIZE", "4096")),
            max_tokens=int(os.getenv("TELLTALE_MAX_TOKENS", "220")),
            temperature=float(os.getenv("TELLTALE_TEMPERATURE", "0.65")),
            seed=int(seed_text) if seed_text else None,
        )


@dataclass(frozen=True)
class LlamaRuntimeConfig:
    model_path: str | None = None
    repo_id: str | None = None
    filename: str | None = None
    context_size: int = 4096
    max_tokens: int = 220
    temperature: float = 0.65
    seed: int | None = None
    n_gpu_layers: int = 0
    model_name: str = DEFAULT_NEMOTRON_MODEL_NAME
    verbose: bool = False

    def to_runtime_settings(self) -> RuntimeSettings:
        if self.model_path:
            return RuntimeSettings(
                mode="llama_cpp",
                model_name=self.model_name,
                gguf_path=self.model_path,
                context_size=self.context_size,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                seed=self.seed,
            )
        return RuntimeSettings(
            mode="mock",
            model_name=self.model_name,
            context_size=self.context_size,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            seed=self.seed,
        )


@dataclass(frozen=True)
class GenerationResult:
    text: str
    latency_ms: int
    tokens_per_second: float | None
    metadata: dict[str, Any]


class LocalTextRuntime:
    """Small llama.cpp-compatible text runtime with a deterministic mock mode."""

    def __init__(self, settings: RuntimeSettings | None = None):
        self.settings = settings or RuntimeSettings.from_env()
        self._llama = None
        if self.settings.mode not in {"mock", "llama_cpp"}:
            raise RuntimeConfigurationError(
                "TELLTALE_MODEL_MODE must be 'mock' or 'llama_cpp'."
            )
        if self.settings.mode == "llama_cpp":
            if not self.settings.gguf_path:
                raise RuntimeConfigurationError(
                    "Nemotron model mode requires TELLTALE_GGUF_PATH to point at a local GGUF file."
                )
            try:
                from llama_cpp import Llama  # type: ignore
            except ImportError as error:
                raise RuntimeConfigurationError(
                    "llama-cpp-python is required for TELLTALE_MODEL_MODE=llama_cpp."
                ) from error
            self._llama = Llama(
                model_path=self.settings.gguf_path,
                n_ctx=self.settings.context_size,
                verbose=False,
            )

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

        assert self._llama is not None
        output = self._llama(
            prompt,
            max_tokens=max_tokens or self.settings.max_tokens,
            temperature=temperature if temperature is not None else self.settings.temperature,
            seed=seed if seed is not None else self.settings.seed,
            stop=["\n\n"],
        )
        text = str(output["choices"][0]["text"]).strip()
        latency_ms = int((time.perf_counter() - started) * 1000)
        token_count = len(text.split())
        tps = (token_count / (latency_ms / 1000)) if latency_ms > 0 else None
        return GenerationResult(text=text, latency_ms=latency_ms, tokens_per_second=tps, metadata=self.metadata())

    def metadata(self) -> dict[str, Any]:
        return {
            "model_name": self.settings.model_name,
            "gguf_path": self.settings.gguf_path,
            "runtime_backend": self.settings.mode,
            "hardware_profile": os.getenv("TELLTALE_HARDWARE_PROFILE", "local_cpu"),
        }

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
    """Compatibility wrapper used by the model-evaluation harness."""

    def __init__(self, config: LlamaRuntimeConfig):
        self.config = config
        self.model_path = self._resolve_model_path(config)
        self._llama = self._load_llama(config, self.model_path)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> str:
        output = self._llama(
            prompt,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
            seed=seed if seed is not None else self.config.seed,
            stop=["\n\n"],
        )
        return str(output["choices"][0]["text"]).strip()

    @staticmethod
    def _resolve_model_path(config: LlamaRuntimeConfig) -> str:
        if config.model_path:
            model_path = Path(config.model_path)
            if not model_path.exists():
                raise RuntimeConfigurationError(f"GGUF model path does not exist: {model_path}")
            return str(model_path)

        if not config.repo_id or not config.filename:
            raise RuntimeConfigurationError(
                "Model eval requires either model_path or both repo_id and filename."
            )

        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except ImportError as error:
            raise RuntimeConfigurationError(
                "huggingface_hub is required to download GGUF candidates from Hugging Face."
            ) from error

        return str(hf_hub_download(repo_id=config.repo_id, filename=config.filename))

    @staticmethod
    def _load_llama(config: LlamaRuntimeConfig, model_path: str):
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError as error:
            raise RuntimeConfigurationError(
                "llama-cpp-python is required for model evaluation."
            ) from error

        return Llama(
            model_path=model_path,
            n_ctx=config.context_size,
            n_gpu_layers=config.n_gpu_layers,
            verbose=config.verbose,
        )
