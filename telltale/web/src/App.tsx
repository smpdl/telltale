import React from "react";
import { AnimatePresence } from "framer-motion";
import { HomeScene } from "./components/HomeScene";
import { InfoModal, SoundPromptModal } from "./components/Modals";
import { MapScene } from "./components/MapScene";
import { TableScene } from "./components/TableScene";
import { useHomeSoundtrack } from "./hooks/useHomeSoundtrack";
import { apiRequest } from "./lib/api";
import type {
  ActionName,
  EventBatch,
  FloorCatalog,
  FloorPreview,
  GameEvent,
  PublicState,
  TraceExport
} from "./lib/types";

export function App() {
  const [homeScreen, setHomeScreen] = React.useState<"title" | "map">("title");
  const [state, setState] = React.useState<PublicState | null>(null);
  const [events, setEvents] = React.useState<GameEvent[]>([]);
  const [amount, setAmount] = React.useState(12);
  const [utterance, setUtterance] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [trace, setTrace] = React.useState<TraceExport | null>(null);
  const [traceOpen, setTraceOpen] = React.useState(false);
  const [aboutOpen, setAboutOpen] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [floors, setFloors] = React.useState<FloorPreview[]>([]);
  const [floorsLoading, setFloorsLoading] = React.useState(true);
  const [ttsEnabled, setTtsEnabled] = React.useState(false);
  const [sttEnabled, setSttEnabled] = React.useState(false);
  const soundtrack = useHomeSoundtrack(!state);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await apiRequest<FloorCatalog>("/api/floors");
        if (!cancelled) setFloors(data.floors);
      } catch (error) {
        if (!cancelled) {
          setNotice(error instanceof Error ? error.message : String(error));
        }
      } finally {
        if (!cancelled) setFloorsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const runApi = React.useCallback(async <T,>(call: () => Promise<T>): Promise<T | null> => {
    setIsLoading(true);
    setNotice("");
    try {
      return await call();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  async function startRun() {
    const result = await runApi(() =>
      apiRequest<PublicState>("/api/start", {
        method: "POST",
        body: JSON.stringify({
          tts_enabled: ttsEnabled,
          stt_enabled: sttEnabled
        })
      })
    );
    if (result) {
      setState(result);
      setEvents([]);
      setTrace(null);
      setTraceOpen(false);
    }
  }

  async function refresh() {
    if (!state) return;
    const result = await runApi(() => apiRequest<PublicState>(`/api/state/${state.run_id}`));
    if (result) setState(result);
  }

  async function submitAction(action: ActionName) {
    if (!state) return;
    const result = await runApi(() =>
      apiRequest<EventBatch>("/api/action", {
        method: "POST",
        body: JSON.stringify({ run_id: state.run_id, action, amount, utterance })
      })
    );
    if (result) {
      setState(result.public_state);
      setEvents(result.events);
      setUtterance("");
    }
  }

  async function chooseReward(perkId: string) {
    if (!state) return;
    const result = await runApi(() =>
      apiRequest<EventBatch>("/api/reward", {
        method: "POST",
        body: JSON.stringify({ run_id: state.run_id, perk_id: perkId })
      })
    );
    if (result) {
      setState(result.public_state);
      setEvents(result.events);
    }
  }

  async function exportTrace() {
    if (!state) return;
    const result = await runApi(() => apiRequest<TraceExport>(`/api/trace/${state.run_id}`));
    if (result) {
      setTrace(result);
      setTraceOpen(true);
    }
  }

  function clearRun() {
    setState(null);
    setEvents([]);
    setTrace(null);
    setTraceOpen(false);
  }

  return (
    <main className="game-root">
      <AnimatePresence mode="wait">
        {!state ? (
          homeScreen === "title" ? (
            <HomeScene
              key="home"
              isLoading={isLoading}
              soundEnabled={soundtrack.enabled}
              soundReady={soundtrack.ready}
              onToggleSound={soundtrack.toggle}
              onPlay={() => setHomeScreen("map")}
              onAbout={() => setAboutOpen(true)}
              onSettings={() => setSettingsOpen(true)}
            />
          ) : (
            <MapScene
              key="map"
              isLoading={isLoading}
              floorsLoading={floorsLoading}
              floors={floors}
              onBack={() => setHomeScreen("title")}
              onStart={startRun}
              soundEnabled={soundtrack.enabled}
              onToggleSound={soundtrack.toggle}
            />
          )
        ) : (
          <TableScene
            key="table"
            state={state}
            events={events}
            amount={amount}
            utterance={utterance}
            notice={notice}
            isLoading={isLoading}
            trace={trace}
            traceOpen={traceOpen}
            onAmountChange={setAmount}
            onUtteranceChange={setUtterance}
            onAction={submitAction}
            onRefresh={refresh}
            onExportTrace={exportTrace}
            onCloseTrace={() => setTraceOpen(false)}
            onReward={chooseReward}
            onExitToMap={() => {
              clearRun();
              setNotice("");
              setHomeScreen("map");
            }}
            onNewRun={() => {
              clearRun();
              setHomeScreen("title");
            }}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {!soundtrack.unlocked && (
          <SoundPromptModal
            onEnable={() => void soundtrack.unlockAndPlay()}
            onSkip={soundtrack.playWithoutSound}
          />
        )}
        {aboutOpen && (
          <InfoModal title="About" onClose={() => setAboutOpen(false)}>
            <p>
              Telltale is a single-player poker roguelike about pressure, memory, and table talk.
              Clear five floors, read the room, and survive opponents who adapt to both your bets
              and your words.
            </p>
          </InfoModal>
        )}
        {settingsOpen && (
          <InfoModal title="Settings" onClose={() => setSettingsOpen(false)}>
            <div className="settings-row">
              <span>Home soundtrack</span>
              <button className="secondary-action" onClick={soundtrack.toggle}>
                {soundtrack.enabled ? "Turn off" : "Turn on"}
              </button>
            </div>
            <div className="settings-row">
              <span>Agent voices</span>
              <button className="secondary-action" onClick={() => setTtsEnabled((value) => !value)}>
                {ttsEnabled ? "Turn off" : "Turn on"}
              </button>
            </div>
            <div className="settings-row">
              <span>Speech input</span>
              <button className="secondary-action" onClick={() => setSttEnabled((value) => !value)}>
                {sttEnabled ? "Turn off" : "Turn on"}
              </button>
            </div>
            <p>Gameplay starts through the configured llama-server runtime.</p>
          </InfoModal>
        )}
      </AnimatePresence>
    </main>
  );
}
