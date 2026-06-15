export type ModelMode = "mock" | "zero_gpu" | "llama_server" | "llama_cpp";
export type ActionName = "fold" | "check" | "call" | "bet" | "raise" | "all_in";

export type ApiError = {
  error: {
    code: "bad_request" | "not_found" | "illegal_action" | "server_error";
    message: string;
  };
};

export type GameEvent = {
  event_id: string;
  event_type: string;
  run_id: string;
  sequence: number;
  payload: Record<string, unknown>;
};

export type EventBatch = {
  run_id: string;
  events: GameEvent[];
  public_state: PublicState;
};

export type FloorPreview = {
  floor_number: number;
  name: string;
  buy_in: number;
  win_target: number;
  small_blind: number;
  big_blind: number;
  is_boss: boolean;
  opponent_count_min: number;
  opponent_count_max: number;
};

export type FloorCatalog = {
  floors: FloorPreview[];
  total_floors: number;
};

export type FloorState = {
  floor_number: number;
  name: string;
  buy_in: number;
  win_target: number;
  small_blind: number;
  big_blind: number;
  is_boss: boolean;
  total_floors: number;
};

export type SeatState = {
  player_id: string;
  name: string;
  seat_index: number;
  stack: number;
  hole_cards: string[];
  current_bet: number;
  has_folded: boolean;
  is_all_in: boolean;
  is_human: boolean;
};

export type HandState = {
  hand_id: string;
  street: string;
  board_cards: string[];
  players: SeatState[];
  pot_contributions: Record<string, number>;
  current_actor_index: number | null;
  legal_actions: ActionName[];
};

export type PerkState = {
  perk_id: string;
  name: string;
  description: string;
  trigger_timing?: string;
  remaining_uses?: number | null;
  remaining_floors?: number | null;
};

export type PublicState = {
  run_id: string;
  seed: string;
  status: "active" | "won" | "lost";
  objective: string;
  floor_index: number;
  floor: FloorState | null;
  bankroll: number;
  debt_markers: number;
  active_perks: PerkState[];
  completed_floors: number[];
  hand: HandState | null;
  pot: number;
  legal_actions: ActionName[];
  latest_speech: Record<string, string>;
  reward_choices: PerkState[];
  awaiting_reward: boolean;
  model: {
    mode?: string;
    model_name?: string;
    runtime_backend?: string;
  };
  voice: {
    tts_enabled: boolean;
    stt_enabled: boolean;
  };
  trace_available: boolean;
};

export type TraceExport = {
  run_id: string;
  path: string | null;
  content: string;
};
