import json
from pathlib import Path

from telltale.game.holdem import ActionType
from telltale.models.eval_prompts import NEMOTRON_3_NANO_4B_Q4_K_M, SMOKE_EVAL_CASES
from telltale.models.eval_prompts import load_candidates_from_json
from telltale.models.eval_runner import (
    EvalRunConfig,
    evaluate_case,
    summarize_candidate_results,
    summarize_results,
    write_eval_bundle,
    write_eval_results,
)


class StaticRuntime:
    def __init__(self, output: str):
        self.output = output
        self.prompts = []

    def generate(self, prompt: str, *, max_tokens=None, temperature=None, seed=None):
        self.prompts.append(
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "seed": seed,
            }
        )
        return self.output


class DiagnosticRuntime(StaticRuntime):
    last_generation_metadata = {"finish_reason": "stop", "raw_text_length": 0}


def test_smoke_eval_cases_build_real_agent_prompts():
    prompts = [case.build_prompt() for case in SMOKE_EVAL_CASES]

    assert len(prompts) == 3
    assert "worm" in prompts[0]
    assert "molly" in prompts[1].lower()
    assert "teddy" in prompts[2].lower()
    assert "required_output" in prompts[0]
    assert "max 28 words" in prompts[0]


def test_eval_case_can_build_richer_dialogue_prompt():
    prompt = SMOKE_EVAL_CASES[0].build_prompt(speech_max_words=36, rationale_max_words=44)

    assert "max 36 words" in prompt
    assert "max 44 words" in prompt


def test_valid_model_eval_records_success():
    case = SMOKE_EVAL_CASES[0]
    legal_action = case.legal_actions[0].value
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": legal_action,
                "amount": 0,
                "speech": "I hear you. Still, this is my price, and I am not donating another chip.",
                "honest_rationale": "The legal action fits the solver pressure.",
                "emotional_state": "needled",
                "memory_delta": {"summary": "Player is applying verbal pressure."},
            }
        )
    )

    result = evaluate_case(
        NEMOTRON_3_NANO_4B_Q4_K_M,
        runtime,
        case,
        EvalRunConfig(max_tokens=111, temperature=0.6, seed=9),
    )

    assert result.json_valid is True
    assert result.legal_action_valid is True
    assert result.error is None
    assert result.final_decision["action"] == legal_action
    assert runtime.prompts[0]["max_tokens"] == 111
    assert runtime.prompts[0]["temperature"] == 0.6
    assert runtime.prompts[0]["seed"] == 9


def test_speech_length_uses_configured_limit():
    case = SMOKE_EVAL_CASES[0]
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "fold",
                "amount": 0,
                "speech": "This line has exactly seven calm words.",
                "honest_rationale": "The legal action follows the solver.",
                "emotional_state": "calm",
                "memory_delta": {},
            }
        )
    )

    strict = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, case, EvalRunConfig(speech_max_words=5))
    generous = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, case, EvalRunConfig(speech_max_words=12))

    assert strict.speech_length_valid is False
    assert generous.speech_length_valid is True


def test_illegal_model_action_is_recorded_as_repaired():
    case = SMOKE_EVAL_CASES[1]
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "check",
                "amount": 500,
                "speech": "I will not buy the act.",
                "honest_rationale": "The price and line are worth contesting.",
                "emotional_state": "composed",
                "memory_delta": {},
            }
        )
    )

    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, case, EvalRunConfig())

    assert result.json_valid is True
    assert result.legal_action_valid is False
    assert result.repair_applied is True
    assert result.normalization_applied is False
    assert result.repair_reason is not None
    assert result.final_decision["action"] == ActionType.CALL.value
    assert result.final_decision["amount"] == 0


def test_invalid_json_model_output_is_a_visible_eval_error():
    runtime = StaticRuntime("I call. Trust me.")

    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, SMOKE_EVAL_CASES[0], EvalRunConfig())

    assert result.json_valid is False
    assert result.final_decision is None
    assert result.error is not None


def test_eval_result_includes_runtime_generation_diagnostics():
    runtime = DiagnosticRuntime("")

    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, SMOKE_EVAL_CASES[0], EvalRunConfig())

    assert result.json_valid is False
    assert result.runtime_metadata["generation"] == {"finish_reason": "stop", "raw_text_length": 0}


def test_call_amount_canonicalization_is_not_scored_as_repair():
    case = SMOKE_EVAL_CASES[0]
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "call",
                "amount": 45,
                "speech": "Nice try, but I am not your charity.",
                "honest_rationale": "The table talk got under my skin, but call is legal.",
                "emotional_state": "annoyed",
                "memory_delta": {"summary": "Player needled Worm."},
            }
        )
    )

    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, case, EvalRunConfig())

    assert result.json_valid is True
    assert result.legal_action_valid is True
    assert result.normalization_applied is True
    assert result.repair_applied is False
    assert result.final_decision["amount"] == 0


def test_extra_model_keys_are_tracked_without_breaking_parse():
    case = SMOKE_EVAL_CASES[0]
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "fold",
                "amount": 0,
                "speech": "Not paying for that speech.",
                "honest_rationale": "The solver pressure says fold and the board is poor.",
                "emotional_state": "annoyed",
                "memory_delta": {},
                "player_utterance": "echoed input",
            }
        )
    )

    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, case, EvalRunConfig())

    assert result.json_valid is True
    assert result.schema_keys_valid is False
    assert result.unexpected_keys == ["player_utterance"]


def test_eval_results_write_jsonl_and_summarize(tmp_path):
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "bet",
                "amount": 90,
                "speech": "The trap has teeth.",
                "honest_rationale": "Strong equity should charge draws.",
                "emotional_state": "amused",
                "memory_delta": {},
            }
        )
    )
    config = EvalRunConfig(output_dir=str(tmp_path))
    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, SMOKE_EVAL_CASES[2], config)

    path = write_eval_results([result], NEMOTRON_3_NANO_4B_Q4_K_M, config)
    lines = path.read_text(encoding="utf-8").splitlines()
    summary = summarize_results([result])

    assert len(lines) == 1
    assert json.loads(lines[0])["case_id"] == "teddy_boss_value_raise"
    assert summary["total"] == 1
    assert summary["json_valid"] == 1


def test_candidate_json_can_extend_harness_without_code_changes(tmp_path):
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "label": "example_qwen",
                        "hf_repo_id": "example/qwen-gguf",
                        "gguf_filename": "qwen-q4_k_m.gguf",
                        "quantization": "Q4_K_M",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    candidates = load_candidates_from_json(str(path))

    assert candidates[0].label == "example_qwen"
    assert candidates[0].hf_repo_id == "example/qwen-gguf"
    assert candidates[0].quantization == "Q4_K_M"


def test_candidate_summary_scores_mechanical_viability():
    good_runtime = StaticRuntime(
        json.dumps(
            {
                "action": "bet",
                "amount": 90,
                "speech": "The trap has teeth.",
                "honest_rationale": "Strong equity should charge draws.",
                "emotional_state": "amused",
                "memory_delta": {},
            }
        )
    )
    bad_runtime = StaticRuntime("plain text, no JSON")
    config = EvalRunConfig()

    good = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, good_runtime, SMOKE_EVAL_CASES[2], config)
    bad = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, bad_runtime, SMOKE_EVAL_CASES[2], config)

    good_summary = summarize_candidate_results("good", [good])
    bad_summary = summarize_candidate_results("bad", [bad])

    assert good_summary.automatic_score > bad_summary.automatic_score
    assert good_summary.speech_length_valid == 1
    assert bad_summary.errors == 1


def test_eval_bundle_writes_per_candidate_jsonl_and_summary(tmp_path):
    runtime = StaticRuntime(
        json.dumps(
            {
                "action": "fold",
                "amount": 0,
                "speech": "Not buying this one.",
                "honest_rationale": "The price trails my equity.",
                "emotional_state": "annoyed",
                "memory_delta": {},
            }
        )
    )
    config = EvalRunConfig(output_dir=str(tmp_path))
    result = evaluate_case(NEMOTRON_3_NANO_4B_Q4_K_M, runtime, SMOKE_EVAL_CASES[0], config)

    bundle = write_eval_bundle({NEMOTRON_3_NANO_4B_Q4_K_M.label: [result]}, output_dir=str(tmp_path))

    summary = json.loads(Path(bundle["summary_path"]).read_text(encoding="utf-8"))
    result_path = Path(bundle["result_paths"][NEMOTRON_3_NANO_4B_Q4_K_M.label])
    assert summary["ranking"][0]["candidate_label"] == NEMOTRON_3_NANO_4B_Q4_K_M.label
    assert json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])["case_id"] == "worm_needle_facing_call"
