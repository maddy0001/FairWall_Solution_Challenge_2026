import type { MetricData } from "@/hooks/use-fairwall";

// ALL possible backend metric name variants → short display name
const SHORT_NAMES: Record<string, string> = {
  // Actual names returned by bias_engine.py
  demographic_parity_diff:       "DPD",
  equal_opportunity_diff:        "EOD",
  selection_rate_disparity:      "SRD",
  // Alternate names (just in case)
  demographic_parity_difference: "DPD",
  equalized_odds_difference:     "EOD",
  statistical_rate_difference:   "SRD",
  equal_opportunity_difference:  "EOD",
  selection_rate_diff:           "SRD",
};

const FULL_NAMES: Record<string, string> = {
  DPD: "Demographic Parity",
  EOD: "Equal Opportunity",
  SRD: "Selection Rate",
};

interface Props {
  metrics: MetricData[];
}

export function MetricCards({ metrics }: Props) {
  // Default placeholders before data arrives
  const display = metrics.length > 0 ? metrics : [
    { name: "demographic_parity_diff",  value: 0, threshold: 0.1, status: "pass", affected_attribute: "", affected_group: "" },
    { name: "equal_opportunity_diff",   value: 0, threshold: 0.1, status: "pass", affected_attribute: "", affected_group: "" },
    { name: "selection_rate_disparity", value: 0, threshold: 0.2, status: "pass", affected_attribute: "", affected_group: "" },
  ] as MetricData[];

  return (
    <div className="ember-card p-3 flex flex-col gap-2" style={{ minHeight: 180 }}>
      {display.map((m) => {
        const short = SHORT_NAMES[m.name] || m.name.slice(0, 3).toUpperCase();
        const full  = FULL_NAMES[short]   || m.name;

        const barWidth     = Math.min((Math.abs(m.value) / 1.0) * 100, 100);
        const thresholdPos = Math.min((m.threshold / 1.0) * 100, 100);

        const statusUpper = (m.status || "pass").toUpperCase() as "PASS" | "WARN" | "FAIL";
        const fillColor   = statusUpper === "PASS" ? "#00E676" : statusUpper === "WARN" ? "#FFD600" : "#FF1744";
        const badgeClass  = statusUpper === "PASS" ? "badge-pass" : statusUpper === "WARN" ? "badge-warn" : "badge-fail";

        return (
          <div key={m.name} className="px-3 py-2">
            <div className="flex items-center justify-between mb-1.5">
              <div>
                <span className="font-bold text-[12px]" style={{ color: "#00D9E8" }}>{short}</span>
                <span className="text-[11px] ml-2" style={{ color: "rgba(245,245,245,0.35)" }}>{full}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-[14px] font-mono" style={{ color: "#F5F5F5" }}>
                  {Math.abs(m.value).toFixed(3)}
                </span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${badgeClass}`}>
                  {statusUpper}
                </span>
              </div>
            </div>
            <div className="relative h-[3px] rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
              <div
                className="absolute h-full rounded-full transition-all duration-500"
                style={{ width: `${barWidth}%`, background: fillColor }}
              />
              <div
                className="absolute h-[6px] -top-[1.5px] w-px"
                style={{ left: `${thresholdPos}%`, borderLeft: "1px dashed rgba(255,255,255,0.25)" }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
