import { useState } from "react";
import { Eye, Check, RotateCcw } from "lucide-react";
import type { ReviewItem } from "@/hooks/use-fairwall";
import { WhatIfPanel } from "./WhatIfPanel";

interface Props {
  items: ReviewItem[];
  onResolve: (docId: string) => void;
  onRunCounterfactual: (attr: string, orig: string, newVal: string) => Promise<unknown>;
  domain: string;
}

function getScoreColor(score: number) {
  if (score >= 80) return "#00E676";
  if (score >= 40) return "#FFD600";
  return "#FF1744";
}

export function ReviewQueue({ items, onResolve, onRunCounterfactual, domain }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const pendingCount = items.filter(i => i.decision === "REJECTED").length;

  return (
    <div className="ember-card p-5 flex flex-col" style={{ height: "100%" }}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-medium tracking-[0.12em]" style={{ color: "rgba(245,245,245,0.30)" }}>
          HUMAN REVIEW QUEUE
        </span>
        {pendingCount > 0 && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold"
            style={{ background: "rgba(255,140,0,0.12)", color: "#FFB347", border: "1px solid rgba(255,140,0,0.30)" }}>
            {pendingCount}
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm" style={{ color: "rgba(245,245,245,0.25)" }}>
          No blocked decisions — system is fair.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="grid grid-cols-[80px_90px_80px_70px_60px_90px] gap-2 px-2 py-1.5 text-[10px] font-medium tracking-wider"
            style={{ color: "rgba(245,245,245,0.30)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <span>ID</span><span>DECISION</span><span>ATTRIBUTE</span><span>GROUP</span><span>SCORE</span><span>ACTIONS</span>
          </div>

          {items.map((item, idx) => {
            const isResolved = item.decision === "RESOLVED";
            return (
              <div key={item.doc_id}>
                <div className="grid grid-cols-[80px_90px_80px_70px_60px_90px] gap-2 px-2 py-2 items-center text-xs"
                  style={{
                    opacity: isResolved ? 0.35 : 1,
                    background: idx % 2 === 0 ? "rgba(255,255,255,0.01)" : undefined,
                    borderLeft: !isResolved ? "2px solid rgba(255,23,68,0.50)" : undefined,
                    backgroundColor: !isResolved ? "rgba(255,23,68,0.03)" : (idx % 2 === 0 ? "rgba(255,255,255,0.01)" : undefined),
                  }}>
                  <span className="font-mono truncate" style={{
                    color: "#00D9E8",
                    textDecoration: isResolved ? "line-through" : undefined,
                    fontSize: 12,
                  }}>
                    {item.prediction_id?.slice(0, 8) || item.doc_id.slice(0, 8)}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold w-fit ${isResolved ? "" : "badge-fail"}`}
                    style={isResolved ? { background: "rgba(255,255,255,0.05)", color: "rgba(245,245,245,0.35)", textDecoration: "line-through" } : {}}>
                    {item.decision}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px]"
                    style={{ background: "rgba(255,140,0,0.10)", border: "1px solid rgba(255,140,0,0.25)", color: "#FFB347" }}>
                    {item.attribute}
                  </span>
                  <span style={{ color: "rgba(245,245,245,0.55)" }}>{item.group}</span>
                  <span className="font-bold" style={{ color: getScoreColor(item.score) }}>{item.score}</span>
                  <div className="flex gap-1">
                    <button className="p-1 rounded transition-all hover:scale-110" style={{ color: "#FF8C00" }}>
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => onResolve(item.doc_id)}
                      className="p-1 rounded transition-all hover:scale-110" style={{ color: "#FF8C00" }}>
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setExpandedId(expandedId === item.doc_id ? null : item.doc_id)}
                      className="p-1 rounded transition-all hover:scale-110" style={{ color: "#FF8C00" }}>
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {expandedId === item.doc_id && (
                  <WhatIfPanel
                    item={item}
                    onRunCounterfactual={onRunCounterfactual}
                    domain={domain}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
