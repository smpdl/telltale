import Chip from "@mui/material/Chip";

export function TableChip({
  label,
  value,
  className = "",
  tone = "default"
}: {
  label: string;
  value?: string | number;
  className?: string;
  tone?: "default" | "gold" | "red" | "green";
}) {
  const text = value === undefined ? label : `${label} ${value}`;
  return <Chip className={`table-chip table-chip-${tone} ${className}`} label={text} size="small" />;
}
