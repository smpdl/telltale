import Card from "@mui/material/Card";
import { motion } from "framer-motion";
import { ArrowLeft, Volume2, VolumeX } from "lucide-react";
import { floorNote } from "../lib/game";
import type { FloorPreview } from "../lib/types";

export function MapScene(props: {
  isLoading: boolean;
  floorsLoading: boolean;
  floors: FloorPreview[];
  soundEnabled: boolean;
  onToggleSound: () => void;
  onBack: () => void;
  onStart: () => void;
}) {
  const totalFloors = props.floors[0] ? props.floors.length : 5;
  const firstFloor = props.floors[0];

  return (
    <motion.section
      className="map-scene"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -18 }}
      transition={{ duration: 0.35 }}
    >
      <header className="map-header">
        <button className="round-action" title="Back" onClick={props.onBack}><ArrowLeft size={20} /></button>
        <div>
          <h2>Clear {totalFloors} floors</h2>
        </div>
        <button className="round-action" title={props.soundEnabled ? "Turn soundtrack off" : "Turn soundtrack on"} onClick={props.onToggleSound}>
          {props.soundEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
        </button>
      </header>
      <div className="floor-map" aria-label="Floor progression">
        {props.floorsLoading ? (
          <p className="map-status">Loading floors...</p>
        ) : props.floors.length === 0 ? (
          <p className="map-status">Floor data unavailable.</p>
        ) : (
          props.floors.map((floor) => (
            <Card
              className={`map-node${floor.is_boss ? " map-node-boss" : ""}`}
              component="article"
              key={floor.floor_number}
              variant="outlined"
            >
              <span>{floor.floor_number}</span>
              <div className="map-node-copy">
                <strong>{floor.name}</strong>
                <small>{floorNote(floor)}</small>
              </div>
            </Card>
          ))
        )}
      </div>
      <button
        className="primary-action menu-action map-start"
        onClick={props.onStart}
        disabled={props.isLoading || props.floorsLoading || !firstFloor}
      >
        {props.isLoading ? "Opening table..." : `Enter ${firstFloor?.name ?? "Floor 1"}`}
      </button>
    </motion.section>
  );
}
