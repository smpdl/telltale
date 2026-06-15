import json

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


def test_llama_cpp_mode_is_compatibility_alias():
    with pytest.raises(RuntimeConfigurationError, match="llama-server request failed"):
        LocalTextRuntime(RuntimeSettings(mode="llama_cpp", server_url="http://127.0.0.1:9"))


def test_llama_server_runtime_calls_openai_compatible_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "body": json.loads(request.data.decode("utf-8")) if request.data else None,
                "timeout": timeout,
            }
        )
        if request.full_url.endswith("/v1/models"):
            return FakeResponse({"data": [{"id": "telltale-agent"}]})
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {"content": ' {"action":"check"}\n'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"completion_tokens": 5},
            }
        )

    monkeypatch.setattr("telltale.models.llama_runtime.request.urlopen", fake_urlopen)

    runtime = LocalTextRuntime(RuntimeSettings(mode="llama_server", server_url="http://llama.test:8080"))

    result = runtime.generate("prompt", max_tokens=32, temperature=0.4, seed=17)

    assert result.text == ' {"action":"check"}\n'
    assert calls[0]["url"] == "http://llama.test:8080/v1/models"
    assert calls[1]["url"] == "http://llama.test:8080/v1/chat/completions"
    assert calls[1]["body"]["messages"] == [{"role": "user", "content": "prompt"}]
    assert calls[1]["body"]["max_tokens"] == 32
    assert calls[1]["body"]["temperature"] == 0.4
    assert calls[1]["body"]["seed"] == 17
    assert result.metadata["runtime_backend"] == "llama_server"
    assert runtime.last_generation_metadata["finish_reason"] == "stop"
    assert runtime.last_generation_metadata["usage"] == {"completion_tokens": 5}


def test_eval_runtime_uses_llama_server(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("/v1/models"):
            return FakeResponse({"data": [{"id": "telltale-agent"}]})
        return FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("telltale.models.llama_runtime.request.urlopen", fake_urlopen)

    runtime = LocalLlamaCppRuntime(
        LlamaRuntimeConfig(
            repo_id="nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF",
            filename="NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf",
            context_size=2048,
            n_gpu_layers=-1,
            server_url="http://llama.test:8080",
        )
    )

    output = runtime.generate("prompt", max_tokens=32, temperature=0.4, seed=17)

    assert output == "{}"
    assert calls == ["http://llama.test:8080/v1/models", "http://llama.test:8080/v1/chat/completions"]
    assert runtime.last_generation_metadata["runtime_backend"] == "llama_server"
