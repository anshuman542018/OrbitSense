import type { EventCard } from "../lib/feed";

const EVIDENCE_LABELS: Record<string, string> = {
  miss_distance_km: "miss distance",
  relative_speed_km_s: "rel. speed",
  tca: "closest approach",
  delta: "element step",
  z_score: "z-score",
  noise_floor: "noise floor",
  element: "element",
  epoch: "epoch",
};

function formatValue(key: string, value: unknown): string {
  if (value == null) return "—";
  if (key === "miss_distance_km") return `${Number(value).toFixed(3)} km`;
  if (key === "relative_speed_km_s") return `${Number(value).toFixed(2)} km/s`;
  if (key === "noise_floor" || key === "delta") return String(value);
  if ((key === "tca" || key === "epoch") && typeof value === "string")
    return value.replace("T", " ").slice(0, 16) + " UTC";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function EventCardView({ card }: { card: EventCard }) {
  const evidenceKeys = Object.keys(card.evidence).filter(
    (k) => k in EVIDENCE_LABELS
  );
  return (
    <article className="card">
      <div className="top">
        <span className={`badge ${card.type}`}>
          {card.type.replace(/_/g, " ")}
        </span>
        <span className={`conf ${card.confidence}`}>
          {card.confidence === "low" ? "low confidence" : "confirmed"}
        </span>
      </div>
      <h3>{card.headline}</h3>
      <p className="exp">{card.explanation}</p>
      {evidenceKeys.length > 0 && (
        <div className="evidence">
          {evidenceKeys.map((k) => (
            <div className="kv" key={k}>
              <div className="k">{EVIDENCE_LABELS[k]}</div>
              <div className="v">{formatValue(k, card.evidence[k])}</div>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
