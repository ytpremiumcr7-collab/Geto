type Props = {
  hours: number | null;
  onChange: (hours: number | null) => void;
};

const PRESETS: { label: string; hours: number | null }[] = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
  { label: "All", hours: null },
];

export function TimeFilter({ hours, onChange }: Props) {
  return (
    <div className="time-filter">
      {PRESETS.map((p) => (
        <button
          key={p.label}
          type="button"
          className={hours === p.hours ? "active" : ""}
          onClick={() => onChange(p.hours)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
