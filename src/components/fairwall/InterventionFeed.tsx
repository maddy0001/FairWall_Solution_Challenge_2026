import { Shield } from "lucide-react";
import type { InterventionEvent } from "@/hooks/use-fairwall";

interface Props {
  events: InterventionEvent[];
}

const ACTION_STYLES: Record<string, { bg: string; border: string; color: string; left: string }> = {
  FLAG: {
    bg: "rgba(255,214,0,0.10)", border: "rgba(255,214,0,0.35)", color: "#FFD600", left: "#FFD600",
  },
  ADJUST: {
    bg: "rgba(0,217,232,0.10)", border: "rgba(0,217,232,0.35)", color: "#00D9E8", left: "#00D9E8",
  },
  BLOCK: {
    bg: "rgba(255,23,68,0.12)", border: "rgba(255,23,68,0.40)", color: "#FF1744", left: "#FF1744",
  },
};

function getScoreColor(score: number) {
  if (score >= 80) return "#00E676";
  if (score >= 40) return "#FFD600";
  return "#FF1744";
}

export function InterventionFeed({ events }: Props) {
  return (
    <div className="ember-card p-5 flex flex-col" style={{ height: "100%" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium tracking-[0.15em]" style={{ color: "rgba(245,245,245,0.30)" }}>
            LIVE INTERVENTION FEED
          </span>
          {events.length > 0 && (
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#00E676", animation: "warming-dot 1s ease-in-out infinite" }} />
          )}
        </div>
      </div>

      {events.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3" style={{ color: "rgba(245,245,245,0.25)" }}>
          <Shield className="w-10 h-10" style={{ color: "rgba(255,140,0,0.25)" }} />
          <div className="text-sm text-center">
            System quiet — no interventions yet.<br />
            <span style={{ color: "rgba(245,245,245,0.35)" }}>Run a simulation to see FairWall intercept bias in real time.</span>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
          {events.map((evt, i) => {
            const style = ACTION_STYLES[evt.action] || ACTION_STYLES.FLAG;
            return (
              <div key={evt.id || i}
                className={`ember-card flex items-center gap-3 px-3 py-2.5 ${evt.action === "BLOCK" ? "block-flash-in" : ""}`}
                style={{ borderLeft: `3px solid ${style.left}`, borderRadius: "0 12px 12px 0" }}>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold shrink-0"
                  style={{ background: style.bg, border: `1px solid ${style.border}`, color: style.color }}>
                  {evt.action}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1 text-xs">
                    <span className="font-mono" style={{ color: "#00D9E8", fontSize: 12 }}>{evt.prediction_id}</span>
                    <span style={{ color: "rgba(245,245,245,0.20)" }}> · </span>
                    <span style={{ color: "rgba(245,245,245,0.55)" }}>{evt.attribute}</span>
                  </div>
                  <div className="text-[11px] truncate" style={{ color: "rgba(245,245,245,0.55)" }}>
                    {evt.explanation}
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono shrink-0"
                  style={{ color: getScoreColor(evt.trust_score), background: `${getScoreColor(evt.trust_score)}15` }}>
                  {evt.trust_score}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
