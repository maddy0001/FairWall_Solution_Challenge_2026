import { Play, Pause } from "lucide-react";

interface Props {
  isSimulating: boolean;
  progress: number;
  total: number;
  onRun: () => void;
}

export function SimulationButton({ isSimulating, progress, total, onRun }: Props) {
  return (
    <div className="ember-card p-4" style={{ height: 72 }}>
      <button onClick={onRun} className="w-full h-[42px] rounded-lg font-bold text-sm flex items-center justify-center gap-2 transition-all duration-200"
        style={isSimulating ? {
          background: "rgba(255,140,0,0.12)",
          border: "1px solid rgba(255,140,0,0.35)",
          color: "#FFB347",
        } : {
          background: "linear-gradient(135deg, #FF8C00 0%, #FF5500 100%)",
          border: "none",
          color: "#080808",
          boxShadow: "0 4px 20px rgba(255,140,0,0.40)",
          letterSpacing: "0.05em",
        }}>
        {isSimulating ? (
          <><Pause className="w-4 h-4" /> Simulating... ({progress}/{total})</>
        ) : (
          <><Play className="w-4 h-4" /> Run Simulation</>
        )}
      </button>
      {isSimulating && (
        <div className="mt-2 h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
          <div className="h-full rounded-full transition-all duration-200"
            style={{ width: `${(progress / total) * 100}%`, background: "#FF8C00" }} />
        </div>
      )}
    </div>
  );
}
