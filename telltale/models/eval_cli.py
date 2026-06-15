from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from telltale.models.eval_prompts import (
    COMPARISON_MODEL_CANDIDATES,
    DEFAULT_MODEL_CANDIDATES,
    EVAL_CASES_BY_ID,
    MODEL_CANDIDATES_BY_LABEL,
    AgentEvalCase,
    ModelCandidate,
    get_eval_case,
    load_candidates_from_json,
)
from telltale.models.eval_runner import (
    EvalRunConfig,
    build_runtime_for_candidate,
    evaluate_candidate,
    write_eval_bundle,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    candidates = _candidate_pool(args.candidate_file)
    if args.list_candidates:
        _print_candidates(candidates)
        return 0
    if args.list_cases:
        _print_cases(EVAL_CASES_BY_ID.values())
        return 0

    selected_candidates = _select_candidates(candidates, args.candidate)
    selected_cases = _select_cases(args.case, args.case_set, args.max_cases)
    profile_defaults = _profile_defaults(args.profile)
    config = EvalRunConfig(
        max_tokens=args.max_tokens if args.max_tokens is not None else profile_defaults["max_tokens"],
        context_size=args.context_size,
        temperature=args.temperature if args.temperature is not None else profile_defaults["temperature"],
        seed=args.seed,
        output_dir=args.output_dir,
        hardware_profile=args.hardware_profile,
        n_gpu_layers=args.n_gpu_layers,
        speech_max_words=args.speech_max_words
        if args.speech_max_words is not None
        else profile_defaults["speech_max_words"],
        rationale_max_words=args.rationale_max_words
        if args.rationale_max_words is not None
        else profile_defaults["rationale_max_words"],
    )

    results_by_candidate = {}
    for candidate in selected_candidates:
        model_path = _model_path_for_candidate(candidate, args.model_path)
        runtime = build_runtime_for_candidate(candidate, config, model_path=model_path)
        results_by_candidate[candidate.label] = evaluate_candidate(
            candidate,
            runtime,
            cases=selected_cases,
            config=config,
        )

    bundle = write_eval_bundle(results_by_candidate, output_dir=args.output_dir)
    print(json.dumps(bundle, ensure_ascii=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate GGUF models on Telltale agent prompts.")
    parser.add_argument(
        "--candidate",
        action="append",
        help="Candidate label to evaluate. Repeat for multiple. Defaults to built-in defaults.",
    )
    parser.add_argument(
        "--candidate-file",
        help="JSON list/object of extra candidates with label, hf_repo_id, and gguf_filename.",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Eval case id to run. Repeat for multiple.",
    )
    parser.add_argument(
        "--case-set",
        choices=["smoke"],
        default="smoke",
        help="Named case set to run when --case is omitted.",
    )
    parser.add_argument("--max-cases", type=int, default=None, help="Cap selected cases for budget control.")
    parser.add_argument("--model-path", action="append", help="Map candidate to local GGUF: label=/path/model.gguf.")
    parser.add_argument("--output-dir", default="runs/model_evals", help="Directory for JSONL and summary artifacts.")
    parser.add_argument("--profile", choices=["default", "nemotron"], default="default")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--context-size", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--speech-max-words", type=int, default=None)
    parser.add_argument("--rationale-max-words", type=int, default=None)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--hardware-profile", default="local")
    parser.add_argument("--n-gpu-layers", type=int, default=0)
    parser.add_argument("--list-candidates", action="store_true")
    parser.add_argument("--list-cases", action="store_true")
    return parser


def _profile_defaults(profile: str) -> dict[str, float | int]:
    if profile == "nemotron":
        return {
            "max_tokens": 520,
            "temperature": 0.55,
            "speech_max_words": 36,
            "rationale_max_words": 44,
        }
    return {
        "max_tokens": 420,
        "temperature": 0.45,
        "speech_max_words": 28,
        "rationale_max_words": 36,
    }


def _candidate_pool(candidate_file: str | None) -> dict[str, ModelCandidate]:
    candidates = dict(MODEL_CANDIDATES_BY_LABEL)
    if candidate_file:
        for candidate in load_candidates_from_json(candidate_file):
            candidates[candidate.label] = candidate
    return candidates


def _select_candidates(
    candidates: dict[str, ModelCandidate],
    labels: list[str] | None,
) -> tuple[ModelCandidate, ...]:
    if not labels:
        return DEFAULT_MODEL_CANDIDATES
    if "all" in labels:
        return COMPARISON_MODEL_CANDIDATES
    selected = []
    for label in labels:
        if label not in candidates:
            known = ", ".join(sorted(candidates))
            raise SystemExit(f"unknown candidate {label!r}; known candidates: {known}")
        selected.append(candidates[label])
    return tuple(selected)


def _select_cases(
    case_ids: list[str] | None,
    case_set: str,
    max_cases: int | None,
) -> tuple[AgentEvalCase, ...]:
    if case_ids:
        cases = tuple(get_eval_case(case_id) for case_id in case_ids)
    elif case_set == "smoke":
        cases = tuple(EVAL_CASES_BY_ID.values())
    else:
        raise SystemExit(f"unknown case set: {case_set}")
    if max_cases is not None:
        if max_cases <= 0:
            raise SystemExit("--max-cases must be positive")
        cases = cases[:max_cases]
    return cases


def _model_path_for_candidate(candidate: ModelCandidate, model_path_args: list[str] | None) -> str | None:
    paths = _parse_model_paths(model_path_args or [])
    return paths.get(candidate.label)


def _parse_model_paths(values: Iterable[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--model-path must use label=/path/model.gguf")
        label, path = value.split("=", 1)
        if not label or not path:
            raise SystemExit("--model-path must use label=/path/model.gguf")
        if not Path(path).exists():
            raise SystemExit(f"local GGUF path does not exist for {label}: {path}")
        paths[label] = path
    return paths


def _print_candidates(candidates: dict[str, ModelCandidate]) -> None:
    for candidate in sorted(candidates.values(), key=lambda item: item.label):
        print(
            json.dumps(
                {
                    "label": candidate.label,
                    "hf_repo_id": candidate.hf_repo_id,
                    "gguf_filename": candidate.gguf_filename,
                    "quantization": candidate.quantization,
                },
                ensure_ascii=True,
            )
        )


def _print_cases(cases: Iterable[AgentEvalCase]) -> None:
    for case in cases:
        print(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "agent_id": case.agent_id,
                    "legal_actions": [action.value for action in case.legal_actions],
                    "expected_pressure": case.expected_pressure,
                },
                ensure_ascii=True,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
