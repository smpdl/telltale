import { Card as PlayingCardSvg } from "@yojda/react-playing-cards";
import { motion } from "framer-motion";

type CardRank = "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "10" | "T" | "J" | "Q" | "K" | "A";
type CardSuit = "h" | "d" | "c" | "s";

export function PlayingCard({ code, hidden, compact = false }: { code?: string; hidden?: boolean; compact?: boolean }) {
  const parsed = parseCardCode(code);
  return (
    <motion.span
      className={`playing-card-shell ${hidden || !parsed ? "back" : ""} ${compact ? "compact" : ""}`}
      layout
      initial={hidden || !parsed ? undefined : { rotateY: 80 }}
      animate={hidden || !parsed ? undefined : { rotateY: 0 }}
    >
      <PlayingCardSvg
        suit={parsed?.suit ?? "s"}
        rank={parsed?.rank ?? "A"}
        variant="tertiary"
        faceDown={hidden || !parsed}
        width={compact ? 34 : 68}
        className="playing-card-svg"
      />
    </motion.span>
  );
}

function parseCardCode(code?: string): { rank: CardRank; suit: CardSuit } | null {
  if (!code) return null;
  const suit = code.slice(-1).toLowerCase() as CardSuit;
  const rawRank = code.slice(0, -1).toUpperCase();
  const rank = (rawRank === "10" ? "T" : rawRank) as CardRank;
  if (!["h", "d", "c", "s"].includes(suit)) return null;
  if (!["2", "3", "4", "5", "6", "7", "8", "9", "10", "T", "J", "Q", "K", "A"].includes(rank)) return null;
  return { rank, suit };
}
