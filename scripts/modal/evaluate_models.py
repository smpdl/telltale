from __future__ import annotations

import json
from pathlib import Path

import modal


APP_NAME = "telltale-model-eval"
PROJECT_ROOT = None


def _find_project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "telltale").is_dir():
            return parent
    return Path("/root")


PROJECT_ROOT = _find_project_root()

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-runtime-ubuntu22.04", add_python="3.11") 
    .apt_install("curl") 
    .env(
        {
            "HF_XET_HIGH_PERFORMANCE": "1",
            "PYTHONPATH": "/root",
        }
    )
    .pip_install("huggingface_hub[hf_transfer]", "pydantic", "numpy")
    .run_commands(
        "python -m pip install --upgrade pip",
        "python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124",
    )
    .add_local_dir(PROJECT_ROOT / "telltale", remote_path="/root/telltale")
)

app = modal.App(APP_NAME, image=image)
hf_cache = modal.Volume.from_name("telltale-hf-cache", create_if_missing=True)

@app.function(
    gpu="L4",
    cpu=4,
    memory=24_576,
    timeout=20 * 60,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    volumes={"/root/.cache/huggingface": hf_cache},
)
def run_model_eval(
    candidate_labels: list[str] | None = None,
    candidate_file_json: str | None = None,
    case_ids: list[str] | None = None,
    max_cases: int | None = 3,
    max_tokens: int = 320,
    context_size: int = 2048,
    temperature: float = 0.30,
    seed: int = 17,
    n_gpu_layers: int = -1,
    speech_max_words: int = 16,
    rationale_max_words: int = 24,
) -> str:
    from telltale.models.eval_prompts import (
        COMPARISON_MODEL_CANDIDATES,
        DEFAULT_MODEL_CANDIDATES,
        EVAL_CASES_BY_ID,
        MODEL_CANDIDATES_BY_LABEL,
        ModelCandidate,
        get_eval_case,
    )
    from telltale.models.eval_runner import (
        EvalRunConfig,
        build_runtime_for_candidate,
        evaluate_candidate,
        write_eval_bundle,
    )

    candidates_by_label = dict(MODEL_CANDIDATES_BY_LABEL)
    if candidate_file_json:
        data = json.loads(candidate_file_json)
        if isinstance(data, dict):
            data = data.get("candidates", [])
        for item in data:
            candidate = ModelCandidate.from_mapping(item)
            candidates_by_label[candidate.label] = candidate

    if candidate_labels and "all" in candidate_labels:
        selected_candidates = list(COMPARISON_MODEL_CANDIDATES)
    elif candidate_labels:
        selected_candidates = []
        for label in candidate_labels:
            if label not in candidates_by_label:
                known = ", ".join(sorted(candidates_by_label))
                raise ValueError(f"unknown candidate {label!r}; known candidates: {known}")
            selected_candidates.append(candidates_by_label[label])
    else:
        selected_candidates = list(DEFAULT_MODEL_CANDIDATES)

    if case_ids:
        selected_cases = tuple(get_eval_case(case_id) for case_id in case_ids)
    else:
        selected_cases = tuple(EVAL_CASES_BY_ID.values())
    if max_cases is not None:
        selected_cases = selected_cases[:max_cases]

    config = EvalRunConfig(
        context_size=context_size,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
        output_dir="/tmp/telltale_model_evals",
        hardware_profile="modal_l4",
        n_gpu_layers=n_gpu_layers,
        speech_max_words=speech_max_words,
        rationale_max_words=rationale_max_words,
    )
    results_by_candidate = {}
    for candidate in selected_candidates:
        runtime = build_runtime_for_candidate(candidate, config)
        results_by_candidate[candidate.label] = evaluate_candidate(
            candidate,
            runtime,
            cases=selected_cases,
            config=config,
        )

    bundle = write_eval_bundle(results_by_candidate, output_dir=config.output_dir)
    return json.dumps(
        {
            "candidate_labels": [candidate.label for candidate in selected_candidates],
            "case_ids": [case.case_id for case in selected_cases],
            "bundle": bundle,
            "results": {
                label: [json.loads(result.to_json_line()) for result in results]
                for label, results in results_by_candidate.items()
            },
        },
        ensure_ascii=True,
        indent=2,
    )


@app.local_entrypoint()
def main(
    candidates: str = "nemotron_3_nano_4b_q4_k_m",
    candidate_file: str = "",
    cases: str = "",
    max_cases: int = 1,
    max_tokens: int = 0,
    context_size: int = 2048,
    temperature: float = -1.0,
    seed: int = 17,
    n_gpu_layers: int = -1,
    profile: str = "auto",
) -> None:
    candidate_labels = _split_csv(candidates)
    case_ids = _split_csv(cases)
    candidate_file_json = Path(candidate_file).read_text(encoding="utf-8") if candidate_file else None
    if candidate_labels == ["all"]:
        from telltale.models.eval_prompts import COMPARISON_MODEL_CANDIDATES

        candidate_labels = [candidate.label for candidate in COMPARISON_MODEL_CANDIDATES]
    resolved_profile = _resolve_profile(profile, candidate_labels)
    if resolved_profile == "nemotron":
        max_tokens = max_tokens if max_tokens > 0 else 520
        temperature = temperature if temperature >= 0 else 0.55
        speech_max_words = 36
        rationale_max_words = 44
    else:
        max_tokens = max_tokens if max_tokens > 0 else 320
        temperature = temperature if temperature >= 0 else 0.30
        speech_max_words = 16
        rationale_max_words = 24
    outputs = []
    for label in candidate_labels:
        try:
            output = run_model_eval.remote(
                candidate_labels=[label],
                candidate_file_json=candidate_file_json,
                case_ids=case_ids,
                max_cases=max_cases,
                max_tokens=max_tokens,
                context_size=context_size,
                temperature=temperature,
                seed=seed,
                n_gpu_layers=n_gpu_layers,
                speech_max_words=speech_max_words,
                rationale_max_words=rationale_max_words,
            )
            outputs.append({"candidate": label, "ok": True, "output": json.loads(output)})
        except Exception as error:  # noqa: BLE001 - keep comparing after native/model crashes
            outputs.append(
                {
                    "candidate": label,
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    print(json.dumps({"isolated_candidate_runs": outputs}, ensure_ascii=True, indent=2))


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_profile(profile: str, candidate_labels: list[str]) -> str:
    if profile != "auto":
        return profile
    if candidate_labels and all(label.startswith("nemotron") for label in candidate_labels):
        return "nemotron"
    return "default"
