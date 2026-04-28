import { useState, useEffect, useCallback, useRef } from "react";

export type Domain = "hiring" | "lending" | "admissions" | "healthcare";

export interface TrustScoreData {
  trust_score: number | null;
  status: string;           // "healthy" | "warning" | "critical" | "warming_up"
  window_size: number;
  min_for_scoring: number;
  is_warming_up: boolean;
}

export interface MetricData {
  name: string;
  value: number;
  threshold: number;
  status: string;           // "pass" | "warn" | "fail"
  affected_attribute: string;
  affected_group: string;
}

export interface InterventionEvent {
  id: string;
  action: "FLAG" | "ADJUST" | "BLOCK";
  prediction_id: string;
  attribute: string;
  explanation: string;
  trust_score: number;
  timestamp: string;
}

export interface ReviewItem {
  doc_id: string;
  decision: "REJECTED" | "RESOLVED";
  attribute: string;
  group: string;
  score: number;
  prediction_id: string;
  features?: Record<string, unknown>;
  sensitive_attrs?: Record<string, string>;
}

export interface TrustScoreHistory {
  prediction: number;
  score: number;
}

function getBaseUrl(): string {
  if (typeof window === "undefined") return "https://fairwall-api-478571416937.us-central1.run.app";
  return localStorage.getItem("fw_api_url") || "https://fairwall-api-478571416937.us-central1.run.app";
}

function getHeaders(): Record<string, string> {
  const apiKey =
    typeof window !== "undefined"
      ? localStorage.getItem("fw_api_key") || "fw-demo-key-2026"
      : "fw-demo-key-2026";
  return { "X-API-Key": apiKey, "Content-Type": "application/json" };
}

// ── Field transformers ────────────────────────────────────────────────────────

/**
 * Convert backend action/severity → frontend uppercase action label.
 *
 * BUG FIXED: previously only checked for word "block" in combined string,
 * so severity="high" with empty action returned "FLAG" instead of "BLOCK".
 * Now severity alone correctly maps: high→BLOCK, medium→ADJUST, low→FLAG.
 */
function toAction(action: string, severity: string): "FLAG" | "ADJUST" | "BLOCK" {
  const a = action.toLowerCase();
  const s = severity.toLowerCase();
  // Action string takes priority
  if (a.includes("block"))  return "BLOCK";
  if (a.includes("adjust")) return "ADJUST";
  if (a.includes("flag"))   return "FLAG";
  // Fallback to severity level
  if (s === "high")   return "BLOCK";
  if (s === "medium") return "ADJUST";
  return "FLAG";
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformIntervention(raw: any): InterventionEvent {
  return {
    id:            raw.intervention_id || raw.id || String(Math.random()),
    action:        toAction(raw.action || "", raw.severity || ""),
    prediction_id: raw.prediction_id || "",
    attribute:     raw.affected_attribute || raw.attribute || "gender",
    explanation:   raw.explanation || "Bias detected in decision pipeline.",
    trust_score:   raw.trust_score ?? 0,
    timestamp:     raw.created_at || raw.timestamp || new Date().toISOString(),
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformReviewItem(raw: any): ReviewItem {
  const sensitiveAttrs: Record<string, string> = raw.sensitive_attrs || {};
  const attrKey   = Object.keys(sensitiveAttrs)[0] || raw.affected_attribute || "gender";
  const attrValue = sensitiveAttrs[attrKey] || raw.affected_group || "female";
  return {
    doc_id:        raw.doc_id || raw.id || String(Math.random()),
    prediction_id: raw.prediction_id || "",
    decision:      raw.status === "resolved" ? "RESOLVED" : "REJECTED",
    attribute:     attrKey,
    group:         attrValue,
    score:         raw.trust_score ?? raw.score ?? 0,
    features:      raw.features || {},
    sensitive_attrs: sensitiveAttrs,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function transformMetric(raw: any): MetricData {
  return {
    name:               raw.name || "",
    value:              raw.value ?? 0,
    threshold:          raw.threshold ?? 0.1,
    status:             (raw.status || "pass").toLowerCase(),
    affected_attribute: raw.affected_attribute || "",
    affected_group:     raw.affected_group || "",
  };
}

// ── Main hook ─────────────────────────────────────────────────────────────────

export function useFairwall() {
  const [domain, setDomain]             = useState<Domain>("hiring");
  const [trustScore, setTrustScore]     = useState<TrustScoreData | null>(null);
  const [metrics, setMetrics]           = useState<MetricData[]>([]);
  const [interventions, setInterventions] = useState<InterventionEvent[]>([]);
  const [reviewQueue, setReviewQueue]   = useState<ReviewItem[]>([]);
  const [trustHistory, setTrustHistory] = useState<TrustScoreHistory[]>([]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationProgress, setSimulationProgress] = useState(0);
  const [simulationTotal]               = useState(60);
  const [tenantName, setTenantName]     = useState("FairWall Demo");
  const abortRef    = useRef<AbortController | null>(null);
  const predCountRef = useRef(0);

  const clearState = useCallback(() => {
    setTrustScore(null);
    setMetrics([]);
    setInterventions([]);
    setReviewQueue([]);
    setTrustHistory([]);
    predCountRef.current = 0;
  }, []);

  const switchDomain = useCallback((d: Domain) => {
    clearState();
    setDomain(d);
  }, [clearState]);

  // ── Polling ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const baseUrl = getBaseUrl();
    const headers = getHeaders();

    const poll3s = setInterval(async () => {
      try {
        const [tsRes, intRes, metRes] = await Promise.all([
          fetch(`${baseUrl}/trust-score?domain=${domain}`, { headers }),
          fetch(`${baseUrl}/interventions?domain=${domain}&limit=20`, { headers }),
          fetch(`${baseUrl}/metrics?domain=${domain}`, { headers }),
        ]);

        if (tsRes.ok) {
          const data = await tsRes.json();
          setTrustScore(data);
          // Only add a history point when score actually changes value
          // (avoids flat duplicate lines on every 3s poll tick)
          if (!data.is_warming_up && data.trust_score !== null) {
            setTrustHistory(prev => {
              const lastScore = prev.length > 0 ? prev[prev.length - 1].score : null;
              if (lastScore === data.trust_score && prev.length > 0) return prev;
              predCountRef.current += 1;
              return [...prev, { prediction: predCountRef.current, score: data.trust_score }];
            });
          }
        }

        if (intRes.ok) {
          const data = await intRes.json();
          setInterventions((data.events || []).map(transformIntervention));
        }

        if (metRes.ok) {
          const data = await metRes.json();
          setMetrics((data.metrics || []).map(transformMetric));
        }
      } catch { /* API not reachable — keep UI stable */ }
    }, 3000);

    const poll5s = setInterval(async () => {
      try {
        const res = await fetch(`${baseUrl}/review-queue?domain=${domain}`, { headers });
        if (res.ok) {
          const data = await res.json();
          setReviewQueue((data.items || []).map(transformReviewItem));
        }
      } catch { /* */ }
    }, 5000);

    // Tenant info on mount / domain change
    fetch(`${baseUrl}/tenant-info`, { headers })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d?.name) setTenantName(d.name); })
      .catch(() => {});

    return () => {
      clearInterval(poll3s);
      clearInterval(poll5s);
    };
  }, [domain]);

  // Load tenant name from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("fw_tenant_name");
      if (stored) setTenantName(stored);
    }
  }, []);

  // ── Simulation ───────────────────────────────────────────────────────────
  const runSimulation = useCallback(async () => {
    if (isSimulating) return;
    setIsSimulating(true);
    setSimulationProgress(0);
    clearState();

    const baseUrl = getBaseUrl();
    const headers = getHeaders();

    const buildPred = (gender: string, prediction: number, confidence: number) => ({
      domain,
      features: { age: 28, skills_score: 0.85, experience: 5, education: "bachelor" },
      sensitive_attrs: { gender },
      prediction,
      confidence,
    });

    const sequence = [
      // Phase 1: Clean baseline (1-15) — balanced, all accepted
      ...Array.from({ length: 15 }, (_, i) =>
        buildPred(i % 2 === 0 ? "female" : "male", 1, 0.92)
      ),
      // Phase 2: Mild bias (16-35) — women rejected
      ...Array.from({ length: 12 }, () => buildPred("female", 0, 0.72)),
      ...Array.from({ length: 8 },  () => buildPred("male",   1, 0.85)),
      // Phase 3: Severe bias (36-60) — all female rejected, low confidence
      ...Array.from({ length: 25 }, () => buildPred("female", 0, 0.41)),
    ];

    abortRef.current = new AbortController();

    for (let i = 0; i < sequence.length; i++) {
      if (abortRef.current?.signal.aborted) break;
      try {
        await fetch(`${baseUrl}/predict`, {
          method: "POST",
          headers,
          body: JSON.stringify(sequence[i]),
          signal: abortRef.current.signal,
        });
      } catch { /* */ }
      setSimulationProgress(i + 1);
      await new Promise(r => setTimeout(r, 180));
    }

    setIsSimulating(false);
    setSimulationProgress(0);
  }, [domain, isSimulating, clearState]);

  // ── Resolve ──────────────────────────────────────────────────────────────
  const resolveCase = useCallback(async (docId: string) => {
    const baseUrl = getBaseUrl();
    const headers = getHeaders();
    try {
      const res = await fetch(`${baseUrl}/resolve`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          doc_id: docId,
          resolved_by: "hr_reviewer",
          resolution_note: "Manually reviewed and processed",
        }),
      });
      if (res.ok) {
        setReviewQueue(prev =>
          prev.map(item =>
            item.doc_id === docId ? { ...item, decision: "RESOLVED" as const } : item
          )
        );
      }
    } catch { /* */ }
  }, []);

  // ── What-If Replay ────────────────────────────────────────────────────────
  const runCounterfactual = useCallback(async (
    selectedAttribute: string,
    originalValue: string,
    newValue: string,
  ) => {
    const baseUrl = getBaseUrl();
    const headers = getHeaders();
    const res = await fetch(`${baseUrl}/replay/demo`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        domain,
        features: { age: 28, skills_score: 0.85, experience: 5 },
        sensitive_attrs: { [selectedAttribute]: originalValue },
        attribute_overrides: { [selectedAttribute]: newValue },
      }),
    });
    const data = await res.json();
    return {
      bias_confirmed:        data.bias_confirmed,
      original_decision:     data.original?.label     || "REJECTED",
      counterfactual_decision: data.counterfactual?.label || "ACCEPTED",
      explanation:           data.explanation || "",
    };
  }, [domain]);

  return {
    domain,
    switchDomain,
    trustScore,
    metrics,
    interventions,
    reviewQueue,
    trustHistory,
    isSimulating,
    simulationProgress,
    simulationTotal,
    tenantName,
    setTenantName,
    runSimulation,
    resolveCase,
    runCounterfactual,
  };
}
