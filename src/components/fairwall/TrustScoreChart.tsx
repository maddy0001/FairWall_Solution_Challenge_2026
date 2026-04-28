import { AreaChart, Area, XAxis, YAxis, ReferenceLine, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import type { TrustScoreHistory } from "@/hooks/use-fairwall";

interface Props {
  data: TrustScoreHistory[];
}

function getColor(score: number) {
  if (score >= 80) return "#00E676";
  if (score >= 40) return "#FFD600";
  return "#FF1744";
}

export function TrustScoreChart({ data }: Props) {
  const latestColor = data.length > 0 ? getColor(data[data.length - 1].score) : "#FF8C00";

  return (
    <div className="ember-card p-5 flex flex-col" style={{ height: "100%" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-medium tracking-[0.15em]" style={{ color: "rgba(245,245,245,0.30)" }}>
          TRUST SCORE OVER TIME
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full"
          style={{ background: "rgba(0,230,118,0.10)", color: "#00E676" }}>
          <span className="w-2 h-2 rounded-full" style={{ background: "#00E676", animation: "warming-dot 1s ease-in-out infinite" }} />
          LIVE
        </div>
      </div>

      {data.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm" style={{ color: "rgba(245,245,245,0.25)" }}>
          Run simulation to see bias build in real time
        </div>
      ) : (
        <div className="flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={true} vertical={false} />
              <XAxis dataKey="prediction" tick={{ fill: "rgba(245,245,245,0.30)", fontSize: 11 }}
                axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} ticks={[0, 40, 80]}
                tick={{ fill: "rgba(245,245,245,0.30)", fontSize: 11 }}
                axisLine={false} tickLine={false} />
              <ReferenceLine y={80} stroke="rgba(0,230,118,0.30)" strokeDasharray="4 4"
                label={{ value: "Safe zone", fill: "rgba(0,230,118,0.50)", fontSize: 10, position: "right" }} />
              <ReferenceLine y={40} stroke="rgba(255,23,68,0.30)" strokeDasharray="4 4"
                label={{ value: "Critical", fill: "rgba(255,23,68,0.50)", fontSize: 10, position: "right" }} />
              <Tooltip
                contentStyle={{
                  background: "#0F0F0F",
                  border: "1px solid rgba(255,140,0,0.30)",
                  borderRadius: 8,
                  color: "#F5F5F5",
                  fontSize: 12,
                }}
                formatter={(value) => [`Score: ${value}`, ""]}
                labelFormatter={(label) => `Prediction: #${label}`}
              />
              <defs>
                <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={latestColor} stopOpacity={0.12} />
                  <stop offset="100%" stopColor={latestColor} stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="score" stroke={latestColor}
                strokeWidth={2} fill="url(#areaFill)" dot={false}
                activeDot={{ r: 4, fill: latestColor }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
