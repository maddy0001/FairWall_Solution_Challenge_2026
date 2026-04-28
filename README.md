# FairWall — AI Fairness Firewall

> **"Every network has a firewall. FairWall is the missing fairness layer for AI."**

[![Live API](https://img.shields.io/badge/API-Live%20on%20Cloud%20Run-brightgreen)](https://fairwall-api-478571416937.us-central1.run.app/health)
[![GitHub](https://img.shields.io/badge/GitHub-Fair--Wall-blue)](https://github.com/ShriHarsan64K/Fair-Wall)
[![Challenge](https://img.shields.io/badge/Challenge-Unbiased%20AI%20Decision-orange)](https://hack2skill.com)

**Challenge:** [Unbiased AI Decision] — Build with AI, Solution Challenge 2026 (hack2skill / Google)  
**Team:** Madhusuthanan G · Gaggula Eshwara Aryan · Rohith A · Shri Harsan M

---

## Live URLs

| Service | URL |
|---------|-----|
| **Backend API** | https://fairwall-api-478571416937.us-central1.run.app |
| **Health Check** | https://fairwall-api-478571416937.us-central1.run.app/health |
| **API Docs** | https://fairwall-api-478571416937.us-central1.run.app/docs |
| **GitHub** | https://github.com/ShriHarsan64K/Fair-Wall |

---

## What is FairWall?

FairWall is a **real-time AI fairness middleware** that intercepts biased decisions before they reach users. Unlike tools that audit bias retrospectively, FairWall acts during inference.

```
WITHOUT FAIRWALL:
AI Model → [biased decision released] → Person harmed → audit discovers bias (too late)

WITH FAIRWALL:
AI Model → FairWall intercepts → bias detected → decision blocked → human review → fair outcome
```

### 3-Line Integration

```python
from fairwall import FairWall

fw = FairWall(domain="hiring", api_key="fw-acme-corp-2026")

@fw.protect
def my_hiring_model(candidate):
    return model.predict(candidate)
# Every prediction is now intercepted. No model changes needed.
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Real-Time Sliding Window** | Trust Score updates on every single prediction — no batch delays |
| **3-Level Intervention** | FLAG (low) → ADJUST threshold (medium) → BLOCK + human review (high) |
| **Gemma Explainability** | Google Gemma 2B generates plain-English explanations for every flagged decision |
| **What-If Bias Replay** | Flip any sensitive attribute, re-run model, see counterfactual — bias made undeniable |
| **Multi-Tenant API Keys** | Each company gets an isolated FairWall instance scoped by API key |
| **Domain Profiles** | YAML configs for hiring (EEOC), lending (ECOA), admissions (Title IX), healthcare |

---

## Architecture

```
CLIENT AI MODEL
    │
    │  POST /predict {features, prediction, sensitive_attrs, domain}
    │  Header: X-API-Key: fw-acme-corp-2026
    ▼
FAIRWALL MIDDLEWARE (FastAPI — Google Cloud Run)
    ├── Tenant Auth Gate          → validate API key, inject tenant_id
    ├── Prediction Logger         → BigQuery audit log
    ├── Bias Detection Engine     → Fairlearn metrics on sliding window
    ├── Trust Score Calculator    → 0–100 score, updates per prediction
    ├── Intervention Engine       → FLAG / ADJUST / BLOCK
    ├── Gemma Explainability      → plain-English explanation per decision
    └── Bias Replay Engine        → What-If counterfactual analysis

REACT DASHBOARD (localhost / Network)
    TrustScoreGauge | BiasChart | InterventionFeed | ReviewQueue | WhatIfPanel
```

---

## AI Trust Score

A single **0–100 score** computed using a sliding window of the last 30 predictions:

- **80–100** → 🟢 HEALTHY — system is fair
- **50–79** → 🟡 WARNING — bias building, flagging active  
- **0–49** → 🔴 CRITICAL — active intervention, decisions being blocked

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (Python 3.11) |
| Bias Metrics | Fairlearn (Microsoft) + IBM AIF360 |
| ML Models | Scikit-learn (demo classifiers) |
| Explainability | Google Gemma 2B (template fallback in demo) |
| Audit Log | Google BigQuery |
| Queue | Google Firestore |
| Backend Host | Google Cloud Run |
| Frontend | React 18 + TanStack Router + Tailwind + Recharts |
| CI/CD | GitHub Actions |

**All on Google free tier — $0 infrastructure cost.**

---

## API Keys (Demo)

```
fw-demo-key-2026      → FairWall Demo    — all 4 domains
fw-acme-corp-2026     → Acme Corp        — hiring + lending
fw-university-2026    → State University — admissions only
```

---

## Quick Start

### Backend (local)
```bash
git clone https://github.com/ShriHarsan64K/Fair-Wall
cd Fair-Wall
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend (local)
```bash
bun install
bun run dev    # http://localhost:8080
```

### Run Demo Simulation
```bash
python demo/simulate_bias.py \
  --api-url https://fairwall-api-478571416937.us-central1.run.app \
  --api-key fw-demo-key-2026
```

### Test Live API
```bash
# Health check
curl https://fairwall-api-478571416937.us-central1.run.app/health

# Send a biased prediction
curl -X POST https://fairwall-api-478571416937.us-central1.run.app/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fw-demo-key-2026" \
  -d '{"domain":"hiring","features":{"age":28,"skills_score":0.85},"sensitive_attrs":{"gender":"female"},"prediction":0}'
```

---

## Fairness Metrics

| Metric | Meaning | Threshold |
|--------|---------|-----------|
| **Demographic Parity Diff** | Equal approval rates across groups | < 0.10 |
| **Equal Opportunity Diff** | Qualified people equally likely to be approved | < 0.10 |
| **Selection Rate Disparity** | No group selected at < 80% the rate of others | ratio > 0.80 |

---

## Domain Profiles

```yaml
# hiring.yaml — EEOC compliance
domain: hiring
sensitive_attributes: [gender, age, ethnicity]
fairness_thresholds:
  demographic_parity_diff: 0.10
  equal_opportunity_diff: 0.10
regulatory_framework: EEOC
sliding_window_size: 30
```

Profiles available: `hiring` · `lending` · `admissions` · `healthcare`

---

## Project Structure

```
Fair-Wall/
├── backend/
│   ├── api/          ← FastAPI endpoints (predict, metrics, simulate, replay...)
│   ├── core/         ← Bias engine, trust score, interventions, Gemma client
│   ├── profiles/     ← YAML domain configs
│   └── prompts/      ← Gemma prompt templates per domain
├── src/              ← React dashboard (TanStack + Tailwind)
├── demo/             ← simulate_bias.py + DEMO_SCRIPT.md
├── Dockerfile        ← Cloud Run production build
└── DEPLOY.md         ← Full deployment guide
```

---

## Future Work

### Short Term
- **Vertex AI Gemma** — Replace template fallback with real Gemma 2B on Vertex AI for production-grade explanations
- **BigQuery Dashboard** — Connect Looker Studio to BigQuery audit logs for historical bias reporting
- **Firestore Persistence** — Enable full Firestore integration for persistent review queues across restarts

### Medium Term
- **More Fairness Metrics** — Add Calibration Difference, Predictive Equality, Individual Fairness scores
- **Threshold Auto-Tuning** — ML-based threshold adjustment that learns from HR resolution decisions
- **Multi-Model Support** — Support for LLM outputs (text classification, ranking) not just binary classifiers
- **Audit Reports** — Auto-generate regulatory compliance PDF reports (EEOC, ECOA, Title IX)

### Long Term
- **Real-Time Alerts** — Slack/email webhook notifications when Trust Score drops below threshold
- **Federated FairWall** — Deploy as a shared fairness layer across multiple AI systems in an enterprise
- **Bias Prediction** — Proactively predict when a model is *likely* to become biased before it happens
- **Open Source SDK** — Publish `fairwall-python` and `fairwall-js` packages on PyPI and npm
- **Browser Extension** — FairWall Chrome extension that audits any AI-powered web product in real time

---

## Demo Script

See [`demo/DEMO_SCRIPT.md`](demo/DEMO_SCRIPT.md) for the verbatim 3-minute judge demo script.

---

## Deployment

See [`DEPLOY.md`](DEPLOY.md) for full Cloud Run + Firebase deployment guide.

---

*Built for Google Solution Challenge 2026 — [Unbiased AI Decision] track*  
*FairWall v1.2 — All 6 segments complete — Cloud Run deployed*