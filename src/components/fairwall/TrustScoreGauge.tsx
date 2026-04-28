import { useEffect, useState, useRef } from "react";
import type { TrustScoreData } from "@/hooks/use-fairwall";

interface Props {
  data: TrustScoreData | null;
}

function getStatusColor(status: string | undefined): string {
  if (!status) return "#FF8C00";
  const s = status.toUpperCase();
  if (s === "HEALTHY") return "#00E676";
  if (s === "WARNING") return "#FFD600";
  if (s === "CRITICAL") return "#FF1744";
  return "#FF8C00"; // warming_up
}

export function TrustScoreGauge({ data }: Props) {
  const [displayScore, setDisplayScore] = useState(0);
  const prevScore = useRef(0);

  /**
   * BUG FIXED: trust_score can be null (backend returns null during warm-up).
   * Previously: score = data?.trust_score ?? 0  ← maps null to 0, draws arc at 0%
   * Now:        isWarmingUp also checks trust_score === null, so arc stays grey
   */
  const isWarmingUp = !data || data.is_warming_up || data.trust_score === null;
  const score  = isWarmingUp ? 0 : (data?.trust_score ?? 0);
  const status = data?.status;
  const color  = getStatusColor(status);

  useEffect(() => {
    if (isWarmingUp) return;
    const start    = prevScore.current;
    const end      = score;
    const duration = 500;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed  = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased    = 1 - Math.pow(1 - progress, 3);
      setDisplayScore(Math.round(start + (end - start) * eased));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
    prevScore.current = end;
  }, [score, isWarmingUp]);

  const radius       = 72;
  const strokeWidth  = 8;
  const circumference = 2 * Math.PI * radius * 0.75;
  const offset        = circumference - circumference * (isWarmingUp ? 0 : score / 100);

  return (
    <div className="ember-card p-5 flex flex-col items-center relative" style={{ height: 260 }}>
      {/* Critical outer pulse ring */}
      {!isWarmingUp && status?.toUpperCase() === "CRITICAL" && (
        <div
          className="absolute inset-0 rounded-xl pointer-events-none"
          style={{
            border: "2px solid rgba(255,23,68,0.4)",
            animation: "critical-ring-pulse 2.5s ease-in-out infinite",
          }}
        />
      )}

      <div
        className="text-[10px] font-medium tracking-[0.18em] mb-2"
        style={{ color: "rgba(245,245,245,0.35)" }}
      >
        AI TRUST SCORE
      </div>

      <div className="relative flex-1 flex items-center justify-center">
        <svg width="180" height="150" viewBox="0 0 180 150">
          {/* Background track */}
          <circle
            cx="90" cy="90" r={radius} fill="none"
            stroke="rgba(255,255,255,0.06)" strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={circumference * 0.25}
            transform="rotate(135, 90, 90)"
            strokeLinecap="round"
          />
          {/* Active arc */}
          <circle
            cx="90" cy="90" r={radius} fill="none"
            stroke={isWarmingUp ? "rgba(100,100,100,0.3)" : color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(135, 90, 90)"
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.7s cubic-bezier(0.4,0,0.2,1), stroke 0.3s" }}
          />
        </svg>

        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          style={{ top: 5 }}
        >
          {isWarmingUp ? (
            <>
              <div className="text-4xl font-bold" style={{ color: "rgba(245,245,245,0.25)" }}>
                —
              </div>
              <div className="text-xs mt-1" style={{ color: "rgba(245,245,245,0.30)" }}>
                Warming up
              </div>
              <div className="flex gap-1 mt-1">
                {[0, 1, 2].map(i => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full"
                    style={{
                      background: "#FF8C00",
                      animation: `warming-dot 1.4s ease-in-out ${i * 0.3}s infinite`,
                    }}
                  />
                ))}
              </div>
              {data && (
                <div className="text-[11px] mt-1" style={{ color: "rgba(255,140,0,0.50)" }}>
                  ({data.window_size} / {data.min_for_scoring} predictions)
                </div>
              )}
            </>
          ) : (
            <>
              <div
                className="font-extrabold"
                style={{ fontSize: 64, color, lineHeight: 1 }}
              >
                {displayScore}
              </div>
              <div
                className="text-[10px] font-bold tracking-[0.22em] mt-1"
                style={{ color }}
              >
                {status?.toUpperCase()}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
