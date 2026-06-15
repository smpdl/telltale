from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Protocol

from telltale.agents.decision import AgentDecision, parse_agent_decision, validate_and_repair
from telltale.game.holdem import ActionType
from telltale.models.eval_prompts import AgentEvalCase, ModelCandidate, SMOKE_EVAL_CASES
from telltale.models.llama_runtime import LlamaRuntimeConfig, LocalLlamaCppRuntime


class TextRuntime(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> str:
        ...


@dataclass(frozen=True)
class EvalRunConfig:
    context_size: int = 2048
    max_tokens: int = 420
    temperature: float = 0.45
    seed: int | None = 17
    output_dir: str = "runs/model_evals"
    hardware_profile: str = "local"
    n_gpu_layers: int = 0
    speech_max_words: int = 28
    rationale_max_words: int = 36


@dataclass(frozen=True)
class AgentEvalResult:
    candidate_label: str
    case_id: str
    timestamp: str
    prompt: str
    raw_output: str
    parsed_output: dict | None
    final_decision: dict | None
    json_valid: bool
    legal_action_valid: bool
    speech_length_valid: bool
    memory_delta_valid: bool
    schema_keys_valid: bool
    unexpected_keys: list[str]
    normalization_applied: bool
    repair_applied: bool
    repair_reason: str | None
    error: str | None
    latency_ms: float
    runtime_metadata: dict

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True)


@dataclass(frozen=True)
class CandidateEvalSummary:
    candidate_label: str
    total: int
    json_valid: int
    legal_action_valid: int
    speech_length_valid: int
    memory_delta_valid: int
    schema_keys_valid: int
    normalization_applied: int
    repair_applied: int
    errors: int
    average_latency_ms: float
    json_valid_rate: float
    legal_action_valid_rate: float
    speech_length_valid_rate: float
    memory_delta_valid_rate: float
    schema_keys_valid_rate: float
    normalization_rate: float
    repair_rate: float
    error_rate: float
    automatic_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def build_runtime_for_candidate(
    candidate: ModelCandidate,
    config: EvalRunConfig,
    *,
    model_path: str | None = None,
) -> LocalLlamaCppRuntime:
    runtime_config = LlamaRuntimeConfig(
        model_path=model_path,
        repo_id=None if model_path else candidate.hf_repo_id,
        filename=None if model_path else candidate.gguf_filename,
        context_size=config.context_size,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        seed=config.seed,
        n_gpu_layers=config.n_gpu_layers,
    )
    return LocalLlamaCppRuntime(runtime_config)


def evaluate_candidate(
    candidate: ModelCandidate,
    runtime: TextRuntime,
    *,
    cases: tuple[AgentEvalCase, ...] = SMOKE_EVAL_CASES,
    config: EvalRunConfig | None = None,
) -> list[AgentEvalResult]:
    run_config = config or EvalRunConfig()
    results: list[AgentEvalResult] = []
    for case in cases:
        results.append(evaluate_case(candidate, runtime, case, run_config))
    return results


def evaluate_candidates(
    candidates: tuple[ModelCandidate, ...],
    runtime_factory,
    *,
    cases: tuple[AgentEvalCase, ...] = SMOKE_EVAL_CASES,
    config: EvalRunConfig | None = None,
) -> dict[str, list[AgentEvalResult]]:
    run_config = config or EvalRunConfig()
    results_by_candidate: dict[str, list[AgentEvalResult]] = {}
    for candidate in candidates:
        runtime = runtime_factory(candidate, run_config)
        results_by_candidate[candidate.label] = evaluate_candidate(
            candidate,
            runtime,
            cases=cases,
            config=run_config,
        )
    return results_by_candidate


def evaluate_case(
    candidate: ModelCandidate,
    runtime: TextRuntime,
    case: AgentEvalCase,
    config: EvalRunConfig,
) -> AgentEvalResult:
    prompt = case.build_prompt(
        speech_max_words=config.speech_max_words,
        rationale_max_words=config.rationale_max_words,
    )
    started = time.perf_counter()
    raw_output = ""
    parsed: AgentDecision | None = None
    repaired: AgentDecision | None = None
    json_valid = False
    legal_action_valid = False
    repair_applied = False
    normalization_applied = False
    repair_reason: str | None = None
    error: str | None = None
    speech_length_valid = False
    memory_delta_valid = False
    schema_keys_valid = False
    unexpected_keys: list[str] = []
    try:
        raw_output = runtime.generate(
            prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            seed=config.seed,
        )
        parsed = parse_agent_decision(raw_output)
        json_valid = True
        unexpected_keys = _unexpected_output_keys(raw_output)
        schema_keys_valid = not unexpected_keys
        speech_length_valid = _speech_length_is_valid(parsed.speech, config.speech_max_words)
        memory_delta_valid = True
        parsed_action = parsed.action.value if isinstance(parsed.action, ActionType) else str(parsed.action)
        legal_values = {action.value for action in case.legal_actions}
        legal_action_valid = parsed_action in legal_values
        original = parsed.to_dict()
        repaired = validate_and_repair(parsed, case.legal_actions, case.solver_recommendation)
        repaired_dict = repaired.to_dict()
        normalization_applied = _normalization_only(original, repaired_dict)
        repair_applied = original != repaired_dict and not normalization_applied
        if repair_applied:
            repair_reason = "model output required legal action or amount repair"
    except Exception as exc:  # noqa: BLE001 - eval records failures instead of hiding them
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = (time.perf_counter() - started) * 1000
    return AgentEvalResult(
        candidate_label=candidate.label,
        case_id=case.case_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        prompt=prompt,
        raw_output=raw_output,
        parsed_output=parsed.to_dict() if parsed else None,
        final_decision=repaired.to_dict() if repaired else None,
        json_valid=json_valid,
        legal_action_valid=legal_action_valid,
        speech_length_valid=speech_length_valid,
        memory_delta_valid=memory_delta_valid,
        schema_keys_valid=schema_keys_valid,
        unexpected_keys=unexpected_keys,
        normalization_applied=normalization_applied,
        repair_applied=repair_applied,
        repair_reason=repair_reason,
        error=error,
        latency_ms=latency_ms,
        runtime_metadata={
            "hf_repo_id": candidate.hf_repo_id,
            "gguf_filename": candidate.gguf_filename,
            "quantization": candidate.quantization,
            "hardware_profile": config.hardware_profile,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "seed": config.seed,
            "speech_max_words": config.speech_max_words,
            "rationale_max_words": config.rationale_max_words,
        },
    )


def write_eval_results(
    results: list[AgentEvalResult],
    candidate: ModelCandidate,
    config: EvalRunConfig,
) -> Path:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{timestamp}_{candidate.label}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(result.to_json_line())
            handle.write("\n")
    return path


def write_eval_bundle(
    results_by_candidate: dict[str, list[AgentEvalResult]],
    *,
    output_dir: str,
) -> dict[str, str | dict]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / timestamp
    run_dir.mkdir()

    result_paths: dict[str, str] = {}
    summaries: dict[str, dict] = {}
    for label, results in results_by_candidate.items():
        path = run_dir / f"{label}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(result.to_json_line())
                handle.write("\n")
        result_paths[label] = str(path)
        summaries[label] = summarize_candidate_results(label, results).to_dict()

    ranking = sorted(
        summaries.values(),
        key=lambda item: (-float(item["automatic_score"]), float(item["average_latency_ms"])),
    )
    summary_path = run_dir / "summary.json"
    summary_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result_paths": result_paths,
        "summaries": summaries,
        "ranking": ranking,
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return {
        "run_dir": str(run_dir),
        "summary_path": str(summary_path),
        "result_paths": result_paths,
        "summaries": summaries,
        "ranking": ranking,
    }


def summarize_results(results: list[AgentEvalResult]) -> dict[str, float | int]:
    total = len(results)
    if total == 0:
        return {
            "total": 0,
            "json_valid": 0,
            "legal_action_valid": 0,
            "speech_length_valid": 0,
            "memory_delta_valid": 0,
            "schema_keys_valid": 0,
            "normalization_applied": 0,
            "repair_applied": 0,
            "errors": 0,
            "average_latency_ms": 0.0,
        }
    return {
        "total": total,
        "json_valid": sum(result.json_valid for result in results),
        "legal_action_valid": sum(result.legal_action_valid for result in results),
        "speech_length_valid": sum(result.speech_length_valid for result in results),
        "memory_delta_valid": sum(result.memory_delta_valid for result in results),
        "schema_keys_valid": sum(result.schema_keys_valid for result in results),
        "normalization_applied": sum(result.normalization_applied for result in results),
        "repair_applied": sum(result.repair_applied for result in results),
        "errors": sum(result.error is not None for result in results),
        "average_latency_ms": sum(result.latency_ms for result in results) / total,
    }


def summarize_candidate_results(candidate_label: str, results: list[AgentEvalResult]) -> CandidateEvalSummary:
    total = len(results)
    if total == 0:
        return CandidateEvalSummary(
            candidate_label=candidate_label,
            total=0,
            json_valid=0,
            legal_action_valid=0,
            speech_length_valid=0,
            memory_delta_valid=0,
            schema_keys_valid=0,
            normalization_applied=0,
            repair_applied=0,
            errors=0,
            average_latency_ms=0.0,
            json_valid_rate=0.0,
            legal_action_valid_rate=0.0,
            speech_length_valid_rate=0.0,
            memory_delta_valid_rate=0.0,
            schema_keys_valid_rate=0.0,
            normalization_rate=0.0,
            repair_rate=0.0,
            error_rate=1.0,
            automatic_score=0.0,
        )

    json_valid = sum(result.json_valid for result in results)
    legal_action_valid = sum(result.legal_action_valid for result in results)
    speech_length_valid = sum(result.speech_length_valid for result in results)
    memory_delta_valid = sum(result.memory_delta_valid for result in results)
    schema_keys_valid = sum(result.schema_keys_valid for result in results)
    normalization_applied = sum(result.normalization_applied for result in results)
    repair_applied = sum(result.repair_applied for result in results)
    errors = sum(result.error is not None for result in results)
    average_latency_ms = sum(result.latency_ms for result in results) / total
    json_rate = json_valid / total
    legal_rate = legal_action_valid / total
    speech_rate = speech_length_valid / total
    memory_rate = memory_delta_valid / total
    schema_rate = schema_keys_valid / total
    normalization_rate = normalization_applied / total
    repair_rate = repair_applied / total
    error_rate = errors / total
    latency_score = _latency_score(average_latency_ms)
    automatic_score = (
        0.31 * json_rate
        + 0.22 * legal_rate
        + 0.13 * speech_rate
        + 0.10 * memory_rate
        + 0.04 * schema_rate
        + 0.10 * (1.0 - repair_rate)
        + 0.06 * (1.0 - error_rate)
        + 0.04 * latency_score
    )
    return CandidateEvalSummary(
        candidate_label=candidate_label,
        total=total,
        json_valid=json_valid,
        legal_action_valid=legal_action_valid,
        speech_length_valid=speech_length_valid,
        memory_delta_valid=memory_delta_valid,
        schema_keys_valid=schema_keys_valid,
        normalization_applied=normalization_applied,
        repair_applied=repair_applied,
        errors=errors,
        average_latency_ms=average_latency_ms,
        json_valid_rate=json_rate,
        legal_action_valid_rate=legal_rate,
        speech_length_valid_rate=speech_rate,
        memory_delta_valid_rate=memory_rate,
        schema_keys_valid_rate=schema_rate,
        normalization_rate=normalization_rate,
        repair_rate=repair_rate,
        error_rate=error_rate,
        automatic_score=automatic_score,
    )


def _speech_length_is_valid(speech: str, max_words: int) -> bool:
    word_count = len(speech.split())
    return 1 <= word_count <= max_words


def _latency_score(average_latency_ms: float) -> float:
    if average_latency_ms <= 1_000:
        return 1.0
    if average_latency_ms >= 12_000:
        return 0.0
    return (12_000 - average_latency_ms) / 11_000


def _normalization_only(original: dict, repaired: dict) -> bool:
    if original == repaired:
        return False
    ignored_fields = {"amount"}
    for key, original_value in original.items():
        if key in ignored_fields:
            continue
        if repaired.get(key) != original_value:
            return False
    return set(repaired) == set(original)


def _unexpected_output_keys(raw_output: str) -> list[str]:
    allowed = {"action", "amount", "speech", "honest_rationale", "emotional_state", "memory_delta", "memory_updates"}
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    return sorted(str(key) for key in data if str(key) not in allowed)


__all__ = [
    "AgentEvalResult",
    "CandidateEvalSummary",
    "EvalRunConfig",
    "TextRuntime",
    "build_runtime_for_candidate",
    "evaluate_candidate",
    "evaluate_candidates",
    "evaluate_case",
    "summarize_candidate_results",
    "summarize_results",
    "write_eval_bundle",
    "write_eval_results",
]
