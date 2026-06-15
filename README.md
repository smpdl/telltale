---
title: Telltale
sdk: gradio
sdk_version: 6.18.0
app_file: app.py
python_version: "3.10"
colorFrom: indigo
colorTo: gray
short_description: AI poker roguelike with table talk.
models:
  - nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
  - nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF
tags:
  - gradio
  - zerogpu
  - build-small
  - thousand-token-wood
  - off-brand
  - best-agent
  - tiny-titan
  - nvidia-nemotron
  - codex
---

# Telltale

Telltale is a single-player Texas Hold'em roguelike about pressure, memory, and table talk. You climb five casino floors against fixed AI opponents who speak in character, remember the run, and make legal poker decisions from a solver-informed local model prompt.

## Hackathon Fit

- Track: Thousand Token Wood.
- Deadline Space runtime: ZeroGPU with `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`, because the hackathon org currently cannot upgrade paid GPU hardware.
- Full standard-GPU runtime: actual `llama.cpp` through `llama-server`, not `llama-cpp-python`.
- ZeroGPU model: `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16`, under the 32B cap, Tiny Titan-friendly, and NVIDIA sponsor-aligned.
- Standard-GPU model target: `nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF`, under the 32B cap and eligible for the Nemotron sponsor path.
- Gradio: `app.py` exposes a `gr.Server` app with a custom React frontend instead of a stock Blocks UI.
- Target badges/prizes: Off Brand, Best Agent, Tiny Titan, Best Demo, Nemotron Hardware Prize, and Best Use of Codex.

## Local Development

```bash
uv sync
uv run pytest
cd telltale/web
npm ci
npm run build
```

Text-only mock mode is useful for fast local tests:

```bash
TELLTALE_MODEL_MODE=mock uv run python app.py
```

## Actual llama.cpp Runtime

Run a local `llama-server` first:

```bash
llama-server \
  --host 127.0.0.1 \
  --port 8080 \
  --hf-repo nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M \
  --hf-file NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
  --alias telltale-agent \
  --ctx-size 4096 \
  --n-gpu-layers 999
```

Then launch Telltale:

```bash
TELLTALE_MODEL_MODE=llama_server \
TELLTALE_LLAMA_SERVER_URL=http://127.0.0.1:8080 \
uv run python app.py
```

The older `llama_cpp` mode string is accepted as a compatibility alias, but the runtime is now `llama_server`.

## Hugging Face Space

Create the Space under the `build-small-hackathon` organization with:

- SDK: Gradio
- Hardware: ZeroGPU
- Visibility: Public

The frontend build is committed under `telltale/web/dist` because Gradio Spaces do not run the Vite build automatically.

On Hugging Face, the default runtime becomes `TELLTALE_MODEL_MODE=zero_gpu` automatically when `SPACE_ID` is present. If the model path has trouble close to submission, add this Space variable to force the emergency text-only demo:

```text
TELLTALE_MODEL_MODE=mock
```

When standard GPU hardware is available, switch to:

```text
TELLTALE_MODEL_MODE=llama_server
```

and run the actual `llama-server` setup described above.

## Voice

Voice is progressive enhancement. Text gameplay remains fully playable.

- TTS target: OpenBMB VoxCPM2 for sponsor-aligned creative character voices, with a fallback to a lightweight local TTS if needed.
- STT target: Cohere Transcribe or Nemotron 3 ASR for sponsor-aligned speech input.
- Current API surface includes transcription and cached audio endpoints so the concrete model can be swapped without changing gameplay.

## Traces

Every model-driven agent decision records prompt, model output, solver recommendation, repairs, memory changes, and runtime metadata. Use the trace export button in the UI or call:

```bash
curl http://127.0.0.1:7860/api/trace/<run_id>
```

## Known Limitations

- TTS/STT model implementations are intentionally behind wrappers so the final sponsor model can be selected without touching game state.
- ZeroGPU mode is the deadline-compatible org deployment path; actual `llama.cpp` mode requires standard GPU hardware.
- Demo video and social-post links must be added before final submission.
