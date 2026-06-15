import sys
import types

import pytest

from telltale.models.llama_runtime import (
    DEFAULT_NEMOTRON_MODEL_NAME,
    LocalTextRuntime,
    LlamaRuntimeConfig,
    LocalLlamaCppRuntime,
    RuntimeConfigurationError,
    RuntimeSettings,
)


def test_mock_runtime_uses_nemotron_metadata_without_gguf():
    runtime = LocalTextRuntime(RuntimeSettings(mode="mock"))

    result = runtime.generate("", context={"suggested_action": "call", "agent_name": "Teddy"})

    assert '"action": "call"' in result.text
    assert result.metadata["model_name"] == DEFAULT_NEMOTRON_MODEL_NAME
    assert result.metadata["runtime_backend"] == "mock"


def test_llama_mode_requires_local_gguf_path():
    with pytest.raises(RuntimeConfigurationError, match="TELLTALE_GGUF_PATH"):
        LocalTextRuntime(RuntimeSettings(mode="llama_cpp", gguf_path=None))


def test_eval_runtime_can_resolve_huggingface_candidate(monkeypatch, tmp_path):
    model_path = tmp_path / "nemotron.gguf"
    model_path.write_text("placeholder", encoding="utf-8")
    calls = {}

    def fake_hf_hub_download(*, repo_id, filename):
        calls["repo_id"] = repo_id
        calls["filename"] = filename
        return str(model_path)

    class FakeLlama:
        def __init__(self, **kwargs):
            calls["llama_kwargs"] = kwargs

        def __call__(self, prompt, **kwargs):
            calls["prompt"] = prompt
            calls["generate_kwargs"] = kwargs
            return {"choices": [{"text": '{"action":"check"}'}]}

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(hf_hub_download=fake_hf_hub_download),
    )
    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))

    runtime = LocalLlamaCppRuntime(
        LlamaRuntimeConfig(
            repo_id="nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF",
            filename="NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf",
            context_size=2048,
            n_gpu_layers=-1,
        )
    )

    output = runtime.generate("prompt", max_tokens=32, temperature=0.4, seed=17)

    assert output == '{"action":"check"}'
    assert calls["repo_id"] == "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF"
    assert calls["filename"] == "NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf"
    assert calls["llama_kwargs"]["model_path"] == str(model_path)
    assert calls["llama_kwargs"]["n_gpu_layers"] == -1
    assert calls["generate_kwargs"]["max_tokens"] == 32
