import Card from "@mui/material/Card";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  BadgeDollarSign,
  ChevronRight,
  Download,
  Flame,
  Gauge,
  Mic,
  RefreshCw,
  Sparkles,
  X
} from "lucide-react";
import { actions, eventLabel, initials, portraitPath } from "../lib/game";
import type { ActionName, GameEvent, PerkState, PublicState, SeatState, TraceExport } from "../lib/types";
import { PlayingCard } from "./PlayingCard";
import { TableChip } from "./TableChip";

export function TableScene(props: {
  state: PublicState;
  events: GameEvent[];
  amount: number;
  utterance: string;
  notice: string;
  isLoading: boolean;
  trace: TraceExport | null;
  traceOpen: boolean;
  onAmountChange: (value: number) => void;
  onUtteranceChange: (value: string) => void;
  onAction: (action: ActionName) => void;
  onRefresh: () => void;
  onExportTrace: () => void;
  onCloseTrace: () => void;
  onReward: (perkId: string) => void;
  onExitToMap: () => void;
  onNewRun: () => void;
}) {
  const hand = props.state.hand;
  const legal = new Set(props.state.legal_actions);
  const boardCards = hand?.board_cards ?? [];
  const players = hand?.players ?? [];
  const latestEvent = props.events.at(-1);

  return (
    <motion.section
      className="table-scene"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.42 }}
    >
      <TopHud state={props.state} onRefresh={props.onRefresh} onExportTrace={props.onExportTrace} onExitToMap={props.onExitToMap} />
      {props.notice && <div className="notice-banner">{props.notice}</div>}
      <section className="table-stage" aria-label="Poker table">
        <FloorRail state={props.state} />
        <motion.div className="felt-table" layout>
          <div className="board-zone">
            <p>{hand?.street ?? "between hands"}</p>
            <div className="board-cards">
              {[0, 1, 2, 3, 4].map((index) => (
                <PlayingCard key={`${hand?.hand_id ?? "none"}-${index}-${boardCards[index] ?? "back"}`} code={boardCards[index]} hidden={!boardCards[index]} />
              ))}
            </div>
            <motion.div key={props.state.pot} initial={{ scale: 0.88 }} animate={{ scale: 1 }}>
              <TableChip className="pot-badge" tone="gold" label="Pot" value={props.state.pot} />
            </motion.div>
          </div>
          <div className="seat-layer">
            {players.map((seat, index) => (
              <SeatCard key={seat.player_id} seat={seat} speech={props.state.latest_speech[seat.player_id]} position={index} />
            ))}
          </div>
        </motion.div>
        <EventReel events={props.events} latestEvent={latestEvent} />
      </section>
      <ActionDock
        state={props.state}
        legal={legal}
        amount={props.amount}
        utterance={props.utterance}
        isLoading={props.isLoading}
        onAmountChange={props.onAmountChange}
        onUtteranceChange={props.onUtteranceChange}
        onAction={props.onAction}
      />
      <AnimatePresence>
        {props.state.awaiting_reward && <RewardOverlay rewards={props.state.reward_choices} onReward={props.onReward} />}
        {props.traceOpen && <TraceDrawer trace={props.trace} onClose={props.onCloseTrace} />}
        {props.state.status !== "active" && <RunEndOverlay state={props.state} onNewRun={props.onNewRun} />}
      </AnimatePresence>
    </motion.section>
  );
}

function TopHud({
  state,
  onRefresh,
  onExportTrace,
  onExitToMap
}: {
  state: PublicState;
  onRefresh: () => void;
  onExportTrace: () => void;
  onExitToMap: () => void;
}) {
  const floor = state.floor;
  return (
    <header className="top-hud">
      <div>
        <p className="eyebrow">Telltale</p>
        <h2>{floor?.name ?? state.status}</h2>
      </div>
      <div className="hud-metrics">
        <Metric icon={<Gauge size={17} />} label="Target" value={floor ? `${floor.win_target}` : "-"} />
        <Metric icon={<BadgeDollarSign size={17} />} label="Bankroll" value={`${state.bankroll}`} />
        <Metric icon={<Flame size={17} />} label="Debt" value={`${state.debt_markers}`} />
        <Metric icon={<Mic size={17} />} label="Voice" value={state.voice.tts_enabled ? "TTS" : "Text"} />
      </div>
      <div className="hud-actions">
        <button title="Back to map" onClick={onExitToMap}>
          <ArrowLeft size={18} />
        </button>
        <button title="Refresh state" onClick={onRefresh}>
          <RefreshCw size={18} />
        </button>
        <button title="Export trace" onClick={onExportTrace}>
          <Download size={18} />
        </button>
        <button className="text-button" onClick={onExitToMap}>Back</button>
      </div>
    </header>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card className="metric" component="div" variant="outlined">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}

function FloorRail({ state }: { state: PublicState }) {
  const active = state.floor?.floor_number ?? 0;
  const done = new Set(state.completed_floors);
  const total = state.floor?.total_floors ?? 5;
  return (
    <nav className="floor-rail" aria-label="Floor progression">
      {Array.from({ length: total }, (_, index) => index + 1).map((floor) => (
        <TableChip key={floor} className={done.has(floor) ? "done" : floor === active ? "active" : ""} label={`${floor}`} tone={done.has(floor) ? "green" : floor === active ? "gold" : "default"} />
      ))}
    </nav>
  );
}

function SeatCard({ seat, speech, position }: { seat: SeatState; speech?: string; position: number }) {
  const portrait = portraitPath(seat.player_id);
  const flags = [seat.has_folded && "folded", seat.is_all_in && "all in"].filter(Boolean).join(" / ") || "live";
  return (
    <motion.article className={`seat-card seat-${position} ${seat.is_human ? "human" : ""}`} layout initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
      <div className="portrait-frame">
        {portrait ? <img src={portrait} alt="" /> : <span>{initials(seat.name)}</span>}
      </div>
      <Card className="seat-panel" component="div" variant="outlined">
        <div className="seat-title">
          <strong>{seat.name}</strong>
          <TableChip label={flags} tone={seat.has_folded ? "red" : seat.is_all_in ? "gold" : "green"} />
        </div>
        <div className="mini-cards">
          {(seat.hole_cards.length ? seat.hole_cards : ["", ""]).map((card, index) => (
            <PlayingCard key={`${seat.player_id}-${index}-${card || "hidden"}`} code={card} hidden={!card} compact />
          ))}
        </div>
        <div className="chip-line">
          <TableChip label="Stack" value={seat.stack} tone="gold" />
          <TableChip label="Bet" value={seat.current_bet} />
        </div>
        <AnimatePresence>
          {speech && (
            <motion.div className="speech-bubble" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              {speech}
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.article>
  );
}

function ActionDock(props: {
  state: PublicState;
  legal: Set<ActionName>;
  amount: number;
  utterance: string;
  isLoading: boolean;
  onAmountChange: (value: number) => void;
  onUtteranceChange: (value: string) => void;
  onAction: (action: ActionName) => void;
}) {
  return (
    <Card className="action-dock" component="section" aria-label="Player actions" variant="outlined">
      <label className="talk-field">
        <span>Table talk</span>
        <input
          value={props.utterance}
          onChange={(event) => props.onUtteranceChange(event.target.value)}
          placeholder="Put pressure on the room..."
          disabled={props.isLoading || props.state.awaiting_reward || props.state.status !== "active"}
        />
      </label>
      <label className="amount-field">
        <span>Amount</span>
        <input
          type="number"
          min={0}
          value={props.amount}
          onChange={(event) => props.onAmountChange(Number(event.target.value))}
          disabled={props.isLoading || props.state.awaiting_reward}
        />
      </label>
      <div className="action-buttons">
        {actions.map(({ id, label, Icon }) => (
          <button
            key={id}
            title={label}
            disabled={props.isLoading || props.state.awaiting_reward || props.state.status !== "active" || !props.legal.has(id)}
            onClick={() => props.onAction(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}

function RewardOverlay({ rewards, onReward }: { rewards: PerkState[]; onReward: (perkId: string) => void }) {
  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Card className="reward-panel" component={motion.section} variant="outlined" initial={{ y: 28, scale: 0.96 }} animate={{ y: 0, scale: 1 }}>
        <p className="eyebrow">Floor cleared</p>
        <h3>Choose your edge</h3>
        <div className="reward-grid">
          {rewards.map((reward) => (
            <Card component="button" variant="outlined" key={reward.perk_id} onClick={() => onReward(reward.perk_id)}>
              <Sparkles size={20} />
              <strong>{reward.name}</strong>
              <span>{reward.description}</span>
              <ChevronRight size={18} />
            </Card>
          ))}
        </div>
      </Card>
    </motion.div>
  );
}

function TraceDrawer({ trace, onClose }: { trace: TraceExport | null; onClose: () => void }) {
  return (
    <motion.aside className="trace-drawer" initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}>
      <header>
        <div>
          <p className="eyebrow">Trace export</p>
          <h3>{trace?.path ?? "In-memory trace"}</h3>
        </div>
        <button title="Close trace" onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      <pre>{trace?.content || "No trace records yet. Make an agent act, then export again."}</pre>
    </motion.aside>
  );
}

function RunEndOverlay({ state, onNewRun }: { state: PublicState; onNewRun: () => void }) {
  const won = state.status === "won";
  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Card className="end-panel" component={motion.section} variant="outlined" initial={{ y: 24, scale: 0.96 }} animate={{ y: 0, scale: 1 }}>
        <p className="eyebrow">{won ? "Run won" : "Run lost"}</p>
        <h3>{won ? "The room is yours." : "The table kept the secret."}</h3>
        <p>Bankroll {state.bankroll}. Debt markers {state.debt_markers}. Completed floors {state.completed_floors.length}.</p>
        <button className="primary-action" onClick={onNewRun}>Return to title</button>
      </Card>
    </motion.div>
  );
}

function EventReel({ events, latestEvent }: { events: GameEvent[]; latestEvent?: GameEvent }) {
  const visible = events.slice(-4);
  return (
    <aside className="event-reel" aria-label="Recent table events">
      <AnimatePresence initial={false}>
        {visible.map((event) => (
          <Card component={motion.div} variant="outlined" key={event.event_id} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
            <span>{event.sequence}</span>
            <strong>{eventLabel(event)}</strong>
          </Card>
        ))}
      </AnimatePresence>
      {!latestEvent && <Card component="div" variant="outlined" className="quiet-event">Waiting for the first tell.</Card>}
    </aside>
  );
}
