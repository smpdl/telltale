from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from random import Random
from typing import Any

from telltale.agents.decision import AgentDecision, parse_agent_decision, validate_and_repair
from telltale.agents.dialogue import PlayerUtterance
from telltale.agents.memory import AgentMemory
from telltale.agents.profiles import (
    DEFAULT_FINAL_BOSS_ID,
    AgentProfile,
    get_agent_profile,
    profiles_for_floor,
)
from telltale.agents.prompts import build_agent_prompt
from telltale.agents.trace import TraceLogger
from telltale.game.economy import RunState, RunStatus, derive_seed
from telltale.game.floors import FLOOR_CONFIGS, FloorConfig
from telltale.game.holdem import ActionType, HandState, PlayerState, PokerError, Street
from telltale.game.perks import PERK_DEFINITIONS
from telltale.models.llama_runtime import LocalTextRuntime, RuntimeSettings
from telltale.models.stt import STTRuntime
from telltale.models.tts import TTSRuntime
from telltale.poker.policy import PokerDecision, PokerPolicyConfig, PokerPolicyWriter
from telltale.server.events import EventBatch, EventBuilder


HUMAN_PLAYER_ID = "player"
DEMO_SEED = 77713


@dataclass(frozen=True)
class RunSettings:
    model_mode: str | None = None
    seed: int | None = None
    tts_enabled: bool = False
    stt_enabled: bool = False
    trace_enabled: bool = True


@dataclass(frozen=True)
class TraceExport:
    run_id: str
    path: str | None
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameSession:
    run: RunState
    runtime: LocalTextRuntime
    tts: TTSRuntime
    stt: STTRuntime
    trace: TraceLogger
    policy: PokerPolicyWriter
    sequence: int = 0
    hand_counter: int = 0
    dealer_index: int = 0
    opponent_profiles: list[AgentProfile] | None = None
    memories: dict[str, AgentMemory] | None = None
    latest_speech: dict[str, str] | None = None
    last_player_utterance: PlayerUtterance | None = None

    def __post_init__(self) -> None:
        self.opponent_profiles = self.opponent_profiles or []
        self.memories = self.memories or {}
        self.latest_speech = self.latest_speech or {}


_SESSIONS: dict[str, GameSession] = {}


def start_run(seed: int | None = None, settings: RunSettings | dict[str, Any] | None = None) -> dict[str, Any]:
    run_settings = _coerce_settings(settings)
    run_seed = seed if seed is not None else run_settings.seed
    run = RunState.start(seed=run_seed, bankroll=260)
    run.enter_current_floor()
    runtime_settings = RuntimeSettings.from_env()
    runtime_settings = RuntimeSettings(
        mode=run_settings.model_mode or runtime_settings.mode,
        model_name=runtime_settings.model_name,
        gguf_path=runtime_settings.gguf_path,
        context_size=runtime_settings.context_size,
        max_tokens=runtime_settings.max_tokens,
        temperature=runtime_settings.temperature,
        seed=runtime_settings.seed,
    )
    session = GameSession(
        run=run,
        runtime=LocalTextRuntime(runtime_settings),
        tts=TTSRuntime(enabled=run_settings.tts_enabled),
        stt=STTRuntime(enabled=run_settings.stt_enabled),
        trace=TraceLogger(run.run_id),
        policy=PokerPolicyWriter(config=PokerPolicyConfig(simulations=250)),
    )
    _SESSIONS[run.run_id] = session
    builder = EventBuilder(run.run_id, session.sequence)
    builder.emit("run_started", seed=run.seed, bankroll=run.bankroll)
    builder.emit("floor_intro", **_floor_payload(run))
    _start_hand(session, builder)
    batch = _continue_until_player_turn(session, builder)
    return batch.public_state


def list_floors() -> dict[str, Any]:
    return {
        "floors": [_floor_config_payload(floor) for floor in FLOOR_CONFIGS],
        "total_floors": len(FLOOR_CONFIGS),
    }


def get_state(run_id: str) -> dict[str, Any]:
    return _public_state(_get_session(run_id))


def submit_player_action(
    run_id: str,
    action: str,
    amount: int | None = None,
    utterance: str | None = None,
    audio: bytes | None = None,
) -> dict[str, Any]:
    session = _get_session(run_id)
    builder = EventBuilder(run_id, session.sequence)
    if audio:
        transcription = session.stt.transcribe(audio)
        if transcription.text and not utterance:
            utterance = transcription.text
        elif transcription.error:
            builder.emit("stt_failed", error=transcription.error)
    session.last_player_utterance = PlayerUtterance(raw_text=utterance or "")
    hand = _require_hand(session)
    if hand.street == Street.COMPLETE:
        _resolve_completed_hand(session, builder)
    else:
        actor = _current_actor(hand)
        if actor.player_id != HUMAN_PLAYER_ID:
            raise ValueError("it is not the player's turn")
        legal = {item.value for item in hand.legal_actions(HUMAN_PLAYER_ID)}
        if action not in legal:
            raise ValueError(f"{action} is not legal right now")
        paid = _apply_action(hand, HUMAN_PLAYER_ID, ActionType(action), amount or 0)
        builder.emit(
            "action_taken",
            player_id=HUMAN_PLAYER_ID,
            name="You",
            action=action,
            amount=paid,
            utterance=utterance or "",
        )
        if utterance:
            session.latest_speech[HUMAN_PLAYER_ID] = utterance
            builder.emit("player_spoke", player_id=HUMAN_PLAYER_ID, text=utterance)
        if hand.street == Street.COMPLETE:
            _resolve_completed_hand(session, builder)
    session.sequence = builder.sequence
    return _continue_until_player_turn(session, builder).to_dict()


def continue_until_player_turn(run_id: str) -> dict[str, Any]:
    session = _get_session(run_id)
    builder = EventBuilder(run_id, session.sequence)
    return _continue_until_player_turn(session, builder).to_dict()


def choose_reward(run_id: str, perk_id: str) -> dict[str, Any]:
    session = _get_session(run_id)
    builder = EventBuilder(run_id, session.sequence)
    session.run.choose_reward(perk_id)
    builder.emit("reward_chosen", perk_id=perk_id)
    if session.run.status == RunStatus.ACTIVE:
        session.run.enter_current_floor()
        builder.emit("floor_intro", **_floor_payload(session.run))
        _start_hand(session, builder)
    session.sequence = builder.sequence
    return _continue_until_player_turn(session, builder).to_dict()


def export_trace(run_id: str) -> dict[str, Any]:
    session = _get_session(run_id)
    path = str(session.trace.path) if session.trace.path.exists() else None
    return TraceExport(run_id=run_id, path=path, content=session.trace.export_text()).to_dict()


def transcribe_player_audio(run_id: str, audio: bytes) -> dict[str, Any]:
    session = _get_session(run_id)
    result = session.stt.transcribe(audio)
    return {
        "text": result.text,
        "confidence": result.confidence,
        "disabled": result.disabled,
        "error": result.error,
    }


def get_tts_audio(audio_id: str) -> dict[str, Any]:
    if "/" in audio_id or "\\" in audio_id or audio_id in {"", ".", ".."}:
        raise ValueError("invalid audio id")
    path = (Path("runs/tts_cache") / audio_id).resolve()
    cache_root = Path("runs/tts_cache").resolve()
    if cache_root not in path.parents:
        raise ValueError("invalid audio id")
    if not path.is_file():
        raise KeyError(f"unknown audio id: {audio_id}")
    return {"path": str(path), "mime_type": "audio/wav"}


def reset_sessions() -> None:
    _SESSIONS.clear()


def _continue_until_player_turn(session: GameSession, builder: EventBuilder) -> EventBatch:
    while session.run.status == RunStatus.ACTIVE and not session.run.awaiting_reward:
        hand = _require_hand(session)
        if hand.street == Street.COMPLETE:
            _resolve_completed_hand(session, builder)
            continue
        actor = _current_actor(hand)
        if actor.player_id == HUMAN_PLAYER_ID:
            builder.emit("player_turn", legal_actions=_legal_actions_payload(hand), pot=_pot(hand))
            break
        _agent_turn(session, builder, actor)
    session.sequence = builder.sequence
    public_state = _public_state(session)
    return EventBatch(session.run.run_id, list(builder.events), public_state)


def _agent_turn(session: GameSession, builder: EventBuilder, actor: PlayerState) -> None:
    hand = _require_hand(session)
    profile = _profile_for_player(session, actor.player_id)
    memory = session.memories.setdefault(profile.agent_id, AgentMemory.neutral(profile.agent_id))
    legal = hand.legal_actions(actor.player_id)
    solver_decision = session.policy.choose_action(
        hand,
        player_id=actor.player_id,
        seed=derive_seed(session.run.seed, "policy", hand.hand_id, len(hand.action_history)),
    )
    public_state = hand.to_public_state(viewer_player_id=actor.player_id)
    private_state = {
        "hole_cards": [str(card) for card in actor.hole_cards],
        "stack": actor.stack,
        "hand_summary": _hand_summary(actor, hand),
    }
    utterance = session.last_player_utterance
    prompt = build_agent_prompt(
        profile,
        memory,
        public_state,
        private_state,
        solver_decision,
        utterance,
        legal,
    )
    generation = session.runtime.generate(
        prompt,
        context={
            "agent_name": profile.name,
            "suggested_action": solver_decision.action.value,
            "suggested_amount": solver_decision.amount,
            "player_utterance": utterance.raw_text if utterance else "",
        },
    )
    repair_applied = False
    repair_reason = ""
    try:
        decision = parse_agent_decision(generation.text)
        decision = validate_and_repair(decision, legal, solver_decision)
    except Exception as error:
        repair_applied = True
        repair_reason = f"model output repaired after parse/validation error: {error}"
        decision = AgentDecision(
            action=solver_decision.action,
            amount=solver_decision.amount,
            speech=f"{profile.name}: I will keep this legal.",
            honest_rationale=solver_decision.reason or "The repaired action follows the solver recommendation.",
            emotional_state="composed",
            memory_delta=memory_delta_empty(),
        )
    before = memory.to_dict()
    paid = _safe_apply_agent_decision(hand, actor.player_id, decision, solver_decision)
    memory.apply_delta(decision.memory_delta)
    after = memory.to_dict()
    session.latest_speech[actor.player_id] = decision.speech
    builder.emit(
        "action_taken",
        player_id=actor.player_id,
        name=actor.name,
        action=_action_value(decision.action),
        amount=paid,
    )
    builder.emit("agent_spoke", player_id=actor.player_id, name=actor.name, text=decision.speech)
    tts = session.tts.synthesize(decision.speech, profile.voice_id)
    if tts.audio_path:
        audio_id = Path(tts.audio_path).name
        builder.emit(
            "tts_ready",
            player_id=actor.player_id,
            audio_id=audio_id,
            audio_url=f"/api/audio/{audio_id}",
            mime_type=tts.mime_type,
        )
    elif tts.error and not tts.disabled:
        builder.emit("tts_failed", player_id=actor.player_id, error=tts.error)
    session.trace.record(
        floor_index=session.run.floor_index,
        hand_id=hand.hand_id,
        action_index=len(hand.action_history),
        agent_id=profile.agent_id,
        public_state=public_state,
        private_agent_state=private_state,
        solver_recommendation=solver_decision,
        player_utterance=utterance.to_dict() if utterance else None,
        memory_before=before,
        prompt=prompt,
        raw_model_output=generation.text,
        parsed_model_output=decision,
        repair_applied=repair_applied,
        repair_reason=repair_reason,
        final_action=_action_value(decision.action),
        final_amount=paid,
        speech=decision.speech,
        honest_rationale=decision.honest_rationale,
        memory_delta=decision.memory_delta,
        memory_after=after,
        runtime_mode=session.runtime.mode,
        model_metadata=generation.metadata | {
            "tokens_per_second": generation.tokens_per_second,
            "latency_ms": generation.latency_ms,
        },
    )
    if hand.street == Street.COMPLETE:
        _resolve_completed_hand(session, builder)


def _safe_apply_agent_decision(
    hand: HandState,
    player_id: str,
    decision: AgentDecision,
    solver_decision: PokerDecision,
) -> int:
    try:
        return _apply_action(hand, player_id, ActionType(_action_value(decision.action)), decision.amount)
    except (PokerError, ValueError):
        return _apply_action(hand, player_id, solver_decision.action, solver_decision.amount)


def _apply_action(hand: HandState, player_id: str, action: ActionType, amount: int) -> int:
    before = hand.pot_contributions[player_id]
    hand.apply_action(action, amount=amount, player_id=player_id)
    return hand.pot_contributions[player_id] - before


def _resolve_completed_hand(session: GameSession, builder: EventBuilder) -> None:
    hand = _require_hand(session)
    if hand.street != Street.COMPLETE:
        return
    player = _player_by_id(hand, HUMAN_PLAYER_ID)
    opponents = [item for item in hand.players if item.player_id != HUMAN_PLAYER_ID]
    if session.run.current_table is not None:
        session.run.current_table.player_stack = player.stack
        session.run.current_table.opponent_stacks = [opponent.stack for opponent in opponents]
        session.run.current_table.hand_index += 1
    builder.emit(
        "hand_complete",
        player_stack=player.stack,
        opponent_stacks=[opponent.stack for opponent in opponents],
        pot=_pot(hand),
        board_cards=[str(card) for card in hand.board_cards],
    )
    floor = session.run.current_floor
    if player.stack <= 0:
        session.run.lose_current_floor(all_in_loss=True)
        if session.run.status == RunStatus.LOST:
            builder.emit("run_lost", reason="player_busted", objective="Win all five floors.")
        elif session.run.status == RunStatus.ACTIVE:
            builder.emit("debt_accepted", debt_markers=session.run.continues, bankroll=session.run.bankroll)
            session.run.enter_current_floor()
            builder.emit("floor_intro", **_floor_payload(session.run))
            _start_hand(session, builder)
        return
    if player.stack >= floor.win_target or all(opponent.stack <= 0 for opponent in opponents):
        session.run.win_current_floor(ending_stack=player.stack)
        builder.emit("floor_won", floor_number=floor.floor_number, bankroll=session.run.bankroll)
        if session.run.status == RunStatus.WON:
            builder.emit("run_won", objective="You cleared the casino.")
        else:
            builder.emit("reward_offered", rewards=session.run.available_rewards)
        return
    _start_hand(session, builder)


def _start_hand(session: GameSession, builder: EventBuilder) -> None:
    run = session.run
    if run.current_table is None:
        run.enter_current_floor()
    assert run.current_table is not None
    profiles = _select_profiles(run.floor_index, len(run.current_table.opponent_stacks), run.seed)
    session.opponent_profiles = profiles
    for profile in profiles:
        session.memories.setdefault(profile.agent_id, AgentMemory.neutral(profile.agent_id))
    player_stack = run.current_table.player_stack
    opponent_stacks = run.current_table.opponent_stacks
    if player_stack <= 0:
        run.lose_current_floor(all_in_loss=True)
        return
    players = [PlayerState(HUMAN_PLAYER_ID, "You", 0, player_stack, is_human=True)]
    for index, (profile, stack) in enumerate(zip(profiles, opponent_stacks, strict=False), start=1):
        if stack > 0:
            players.append(PlayerState(profile.agent_id, profile.name, index, stack))
    if len(players) < 2:
        run.win_current_floor(ending_stack=player_stack)
        return
    session.hand_counter += 1
    hand_seed = run.hand_seed(hand_index=session.hand_counter)
    dealer_index = session.dealer_index % len(players)
    if run.current_table.pending_metadata.get("player_acts_last_first_hand") and run.current_table.hand_index == 0:
        dealer_index = max(0, len(players) - 2)
    run.current_hand = HandState.start(
        players,
        seed=hand_seed,
        dealer_button_index=dealer_index,
        small_blind=run.current_table.small_blind,
        big_blind=run.current_table.big_blind,
        hand_id=f"{run.run_id}-h{session.hand_counter}",
    )
    session.dealer_index = (dealer_index + 1) % len(players)
    builder.emit(
        "hand_started",
        hand_id=run.current_hand.hand_id,
        floor_number=run.current_floor.floor_number,
        blinds={"small": run.current_table.small_blind, "big": run.current_table.big_blind},
    )
    builder.emit("cards_dealt", player_cards=[str(card) for card in players[0].hole_cards])


def _public_state(session: GameSession) -> dict[str, Any]:
    run = session.run
    hand = run.current_hand
    hand_state = hand.to_public_state(HUMAN_PLAYER_ID) if hand is not None else None
    floor = run.current_floor if run.status == RunStatus.ACTIVE else None
    legal_actions = hand_state["legal_actions"] if hand_state else []
    return {
        "run_id": run.run_id,
        "seed": run.seed,
        "status": run.status.value,
        "objective": "Win the run by clearing all five floors. Current floor win target is the next chip goal.",
        "floor_index": run.floor_index,
        "floor": _floor_payload(run) if floor else None,
        "bankroll": run.bankroll,
        "debt_markers": run.continues,
        "active_perks": [perk.serialize() for perk in run.active_perks],
        "completed_floors": list(run.completed_floors),
        "hand": hand_state,
        "pot": _pot(hand) if hand else 0,
        "legal_actions": legal_actions,
        "latest_speech": dict(session.latest_speech or {}),
        "reward_choices": [_perk_payload(perk_id) for perk_id in run.available_rewards],
        "awaiting_reward": run.awaiting_reward,
        "model": session.runtime.metadata(),
        "voice": {"tts_enabled": session.tts.enabled, "stt_enabled": session.stt.enabled},
        "trace_available": bool(session.trace.records or session.trace.path.exists()),
    }


def _floor_config_payload(floor: FloorConfig) -> dict[str, Any]:
    return {
        "floor_number": floor.floor_number,
        "name": floor.name,
        "buy_in": floor.buy_in,
        "win_target": floor.win_target,
        "small_blind": floor.blinds.small_blind,
        "big_blind": floor.blinds.big_blind,
        "is_boss": floor.is_boss,
        "opponent_count_min": floor.opponent_count_min,
        "opponent_count_max": floor.opponent_count_max,
    }


def _floor_payload(run: RunState) -> dict[str, Any]:
    return {
        **_floor_config_payload(run.current_floor),
        "total_floors": len(FLOOR_CONFIGS),
    }


def _perk_payload(perk_id: str) -> dict[str, Any]:
    for perk in PERK_DEFINITIONS:
        if perk.perk_id == perk_id:
            return perk.serialize()
    return {"perk_id": perk_id, "name": perk_id, "description": ""}


def _select_profiles(floor_index: int, opponent_count: int, seed: str) -> list[AgentProfile]:
    floor_number = floor_index + 1
    if FLOOR_CONFIGS[floor_index].is_boss:
        boss = get_agent_profile(DEFAULT_FINAL_BOSS_ID)
        pool = [profile for profile in profiles_for_floor(floor_number) if profile.agent_id != boss.agent_id]
        return [boss, *pool[: max(0, opponent_count - 1)]]
    pool = list(profiles_for_floor(floor_number, include_bosses=False))
    Random(derive_seed(seed, "profiles", floor_number)).shuffle(pool)
    return pool[:opponent_count]


def _profile_for_player(session: GameSession, player_id: str) -> AgentProfile:
    for profile in session.opponent_profiles or []:
        if profile.agent_id == player_id:
            return profile
    return get_agent_profile(player_id)


def _legal_actions_payload(hand: HandState) -> list[str]:
    return sorted(action.value for action in hand.legal_actions(HUMAN_PLAYER_ID))


def _hand_summary(player: PlayerState, hand: HandState) -> str:
    return f"{player.name} has {' '.join(str(card) for card in player.hole_cards)} on {hand.street.value}."


def _current_actor(hand: HandState) -> PlayerState:
    if hand.current_actor_index is None:
        raise PokerError("there is no current actor")
    return hand.players[hand.current_actor_index]


def _player_by_id(hand: HandState, player_id: str) -> PlayerState:
    for player in hand.players:
        if player.player_id == player_id:
            return player
    raise PokerError(f"unknown player id: {player_id}")


def _require_hand(session: GameSession) -> HandState:
    if session.run.current_hand is None:
        raise PokerError("no active hand")
    return session.run.current_hand


def _pot(hand: HandState | None) -> int:
    if hand is None:
        return 0
    return sum(hand.pot_contributions.values())


def _coerce_settings(settings: RunSettings | dict[str, Any] | None) -> RunSettings:
    if settings is None:
        return RunSettings()
    if isinstance(settings, RunSettings):
        return settings
    return RunSettings(**settings)


def _get_session(run_id: str) -> GameSession:
    try:
        return _SESSIONS[run_id]
    except KeyError as error:
        raise KeyError(f"unknown run id: {run_id}") from error


def _action_value(action: ActionType | str | Enum) -> str:
    if isinstance(action, Enum):
        return str(action.value)
    return str(action)


def memory_delta_empty():
    from telltale.agents.memory import MemoryDelta

    return MemoryDelta()


__all__ = [
    "DEMO_SEED",
    "HUMAN_PLAYER_ID",
    "RunSettings",
    "TraceExport",
    "choose_reward",
    "continue_until_player_turn",
    "export_trace",
    "get_tts_audio",
    "get_state",
    "reset_sessions",
    "start_run",
    "submit_player_action",
    "transcribe_player_audio",
]
