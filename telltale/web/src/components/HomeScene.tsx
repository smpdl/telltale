import { motion } from "framer-motion";
import { Settings, Volume2, VolumeX } from "lucide-react";
import { SoundStatus } from "./SoundStatus";

export function HomeScene(props: {
  isLoading: boolean;
  soundEnabled: boolean;
  soundReady: boolean;
  onToggleSound: () => void;
  onPlay: () => void;
  onAbout: () => void;
  onSettings: () => void;
}) {
  return (
    <motion.section
      className="title-scene"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.45 }}
    >
      <div className="title-atmosphere" aria-hidden="true">
        <span className="title-blob title-blob-a" />
        <span className="title-blob title-blob-b" />
        <span className="title-blob title-blob-c" />
        <span className="title-blob title-blob-d" />
        <span className="title-blob title-blob-e" />
        <span className="title-blob title-blob-f" />
      </div>
      <nav className="title-utility" aria-label="Title utilities">
        <button className="title-icon-btn" type="button" title="Settings" onClick={props.onSettings}>
          <Settings size={18} />
        </button>
        <button
          className="title-icon-btn"
          type="button"
          title={props.soundEnabled ? "Turn soundtrack off" : "Turn soundtrack on"}
          onClick={props.onToggleSound}
        >
          {props.soundEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
      </nav>
      <div className="title-copy">
        <div className="brand-lockup">
          <h1>Telltale</h1>
        </div>
        <p className="lede">
          A cinematic poker roguelike where conversation, memory, and pressure decide how far
          your bankroll can carry you.
        </p>
        <div className="home-actions" aria-label="Main menu">
          <button className="title-btn" type="button" onClick={props.onPlay} disabled={props.isLoading}>
            Play
          </button>
          <button className="title-btn" type="button" onClick={props.onAbout}>
            About
          </button>
        </div>
        <SoundStatus enabled={props.soundEnabled} />
      </div>
    </motion.section>
  );
}
