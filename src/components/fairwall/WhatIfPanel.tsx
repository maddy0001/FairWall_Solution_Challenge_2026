import { useState } from "react";
import { Loader2, Zap, CheckCircle } from "lucide-react";
import type { ReviewItem } from "@/hooks/use-fairwall";

const ATTR_VALUES: Record<string, string[]> = {
  gender: ["male", "female", "non-binary"],
  age_group: ["young", "mid", "senior"],
  race: ["A", "B", "C", "D"],
  ethnicity: ["A", "B", "C", "D"],
};

interface Props {
  item: ReviewItem;
  onRunCounterfactual: (attr: string, orig: string, newVal: string) => Promise<unknown>;
  domain: string;
}

export function WhatIfPanel({ item, onRunCounterfactual }: Props) {
  const [selectedAttr, setSelectedAttr] = useState(item.attribute || "gender");
  const origValue = item.group || "female";
  const possibleValues = ATTR_VALUES[selectedAttr] || ["A", "B"];
  const [newValue, setNewValue] = useState(possibleValues.find(v => v !== origValue) || possibleValues[0]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ bias_confirmed?: boolean; original_decision?: string; counterfactual_decision?: string; explanation?: string } | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setResult(null);
    try {
      const data = await onRunCounterfactual(selectedAttr, origValue, newValue) as typeof result;
      setResult(data);
    } catch { setResult(null); }
    setLoading(false);
  };

  return (
    <div className="mx-2 mb-2 p-4 overflow-hidden transition-all duration-300"
      style={{
        background: "rgba(255,23,68,0.04)",
        border: "1px solid rgba(255,23,68,0.20)",
        borderRadius: "0 0 10px 10px",
        borderLeft: "3px solid #FF1744",
      }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs font-bold" style={{ color: "#F5F5F5" }}>
          <span>🔁</span> What-If Bias Replay
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          <span className="font-mono" style={{ color: "#00D9E8" }}>{item.prediction_id?.slice(0, 8)}</span>
          <span className="badge-fail px-1.5 py-0.5 rounded text-[10px] font-bold">BLOCKED</span>
        </div>
      </div>

      <div className="flex items-center gap-3 mb-3 text-xs">
        <span style={{ color: "rgba(245,245,245,0.55)" }}>Flip attribute:</span>
        <select value={selectedAttr} onChange={e => {
          setSelectedAttr(e.target.value);
          const vals = ATTR_VALUES[e.target.value] || ["A", "B"];
          setNewValue(vals.find(v => v !== origValue) || vals[0]);
          setResult(null);
        }}
          className="bg-transparent border rounded px-2 py-1 text-xs"
          style={{ borderColor: "rgba(255,140,0,0.30)", color: "#FFB347" }}>
          {Object.keys(ATTR_VALUES).map(a => <option key={a} value={a} style={{ background: "#0F0F0F" }}>{a}</option>)}
        </select>
        <span style={{ color: "#F5F5F5" }}>{origValue}</span>
        <span style={{ color: "rgba(245,245,245,0.20)" }}>→</span>
        <select value={newValue} onChange={e => { setNewValue(e.target.value); setResult(null); }}
          className="bg-transparent border rounded px-2 py-1 text-xs"
          style={{ borderColor: "rgba(255,140,0,0.30)", color: "#FFB347" }}>
          {possibleValues.map(v => <option key={v} value={v} style={{ background: "#0F0F0F" }}>{v}</option>)}
        </select>
      </div>

      <button onClick={handleRun} disabled={loading}
        className="w-full h-9 rounded-lg text-xs font-bold flex items-center justify-center gap-2 mb-3 transition-all"
        style={{
          background: "linear-gradient(135deg, #FF8C00, #FF1744)",
          color: "#FFFFFF",
          boxShadow: "0 4px 20px rgba(255,80,0,0.40)",
        }}>
        {loading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Analyzing...</> : "▶ Run Counterfactual"}
      </button>

      {result && (
        <div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="p-3 rounded-lg" style={{ background: "rgba(255,23,68,0.05)", border: "1px solid rgba(255,23,68,0.30)" }}>
              <div className="text-[10px] font-bold mb-1" style={{ color: "#FF1744" }}>ORIGINAL</div>
              <div className="text-xs mb-1" style={{ color: "rgba(245,245,245,0.55)" }}>{selectedAttr}: {origValue}</div>
              <div className="font-bold text-sm" style={{ color: "#FF1744" }}>✗ {result.original_decision || "REJECTED"}</div>
            </div>
            <div className="p-3 rounded-lg" style={{ background: "rgba(0,230,118,0.05)", border: "1px solid rgba(0,230,118,0.30)" }}>
              <div className="text-[10px] font-bold mb-1" style={{ color: "#00E676" }}>COUNTERFACTUAL</div>
              <div className="text-xs mb-1" style={{ color: "rgba(245,245,245,0.55)" }}>{selectedAttr}: {newValue}</div>
              <div className="font-bold text-sm" style={{ color: "#00E676" }}>✓ {result.counterfactual_decision || "ACCEPTED"}</div>
            </div>
          </div>

          {result.bias_confirmed ? (
            <div className="p-3 rounded-lg" style={{ background: "rgba(255,23,68,0.08)", borderLeft: "3px solid #FF1744" }}>
              <div className="flex items-start gap-2 text-xs">
                <Zap className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#FF1744" }} />
                <div>
                  <div className="font-bold mb-0.5 text-[13px]" style={{ color: "#FF1744" }}>BIAS CONFIRMED</div>
                  <div style={{ color: "rgba(245,245,245,0.70)" }}>
                    {result.explanation || "The decision changed from REJECTED to ACCEPTED when the attribute was flipped — identical qualifications."}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-3 rounded-lg" style={{ background: "rgba(0,230,118,0.06)", borderLeft: "3px solid #00E676" }}>
              <div className="flex items-start gap-2 text-xs">
                <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#00E676" }} />
                <div>
                  <div className="font-bold" style={{ color: "#00E676" }}>No bias detected for this attribute</div>
                  <div style={{ color: "rgba(245,245,245,0.70)" }}>{result.explanation || ""}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
