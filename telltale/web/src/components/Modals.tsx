import React from "react";
import Card from "@mui/material/Card";
import { motion } from "framer-motion";
import { Volume2, X } from "lucide-react";

export function SoundPromptModal(props: { onEnable: () => void; onSkip: () => void }) {
  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Card className="info-panel sound-prompt" component={motion.section} variant="outlined" initial={{ y: 24, scale: 0.96 }} animate={{ y: 0, scale: 1 }}>
        <header>
          <h3>Turn sound on</h3>
        </header>
        <div className="info-body">
          <p>This game is best enjoyed with the soundtrack on. Enable audio to hear the score as you play.</p>
          <div className="sound-prompt-actions">
            <button className="primary-action menu-action" onClick={props.onEnable}>
              <Volume2 size={18} />
              Enable soundtrack
            </button>
            <button className="secondary-action" onClick={props.onSkip}>Continue without sound</button>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

export function InfoModal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Card className="info-panel" component={motion.section} variant="outlined" initial={{ y: 24, scale: 0.96 }} animate={{ y: 0, scale: 1 }}>
        <header>
          <h3>{title}</h3>
          <button className="round-action" title="Close" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="info-body">{children}</div>
      </Card>
    </motion.div>
  );
}
