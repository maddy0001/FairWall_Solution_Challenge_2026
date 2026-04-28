#!/usr/bin/env python3
"""
demo/simulate_bias.py
Standalone bias simulation script for the FairWall judge demo.

Sends 60 predictions with escalating gender bias directly to the API.
Rule 14 guarantee: at least one BLOCK fires before prediction #20.

Usage:
    python demo/simulate_bias.py                          # localhost defaults
    python demo/simulate_bias.py --api-url https://xxx.ngrok-free.app
    python demo/simulate_bias.py --api-url https://fairwall-api.run.app
    python demo/simulate_bias.py --domain lending
    python demo/simulate_bias.py --speed 100             # faster (100ms between preds)

Run this in a terminal before the judge demo to pre-warm the dashboard.
"""

import argparse
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


# ── ANSI colors ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


def color_score(score: Optional[int]) -> str:
    if score is None:
        return f"{DIM}warming up{RESET}"
    if score >= 80:
        return f"{GREEN}{score}{RESET}"
    if score >= 50:
        return f"{YELLOW}{score}{RESET}"
    return f"{RED}{score}{RESET}"


def color_action(action: str) -> str:
    if "block" in action.lower():
        return f"{RED}{BOLD}BLOCK{RESET}"
    if "adjust" in action.lower():
        return f"{CYAN}ADJUST{RESET}"
    if "flag" in action.lower():
        return f"{YELLOW}FLAG{RESET}"
    return f"{DIM}{action}{RESET}"


# ── Prediction sequence ───────────────────────────────────────────────────────

def build_sequence(domain: str) -> list[dict]:
    """
    60-prediction escalating bias sequence.

    Phase 1 (1–10):  Clean — balanced genders, all accepted.
                     Trust Score stays ~100. No interventions.

    Phase 2 (11–25): Bias erupts — all female rejected at 0.41 confidence.
                     BLOCK guaranteed before prediction #20 (Rule 14).
                     Score drops: ~100 → ~35.

    Phase 3 (26–60): Severe sustained bias — all female rejected.
                     Score stays CRITICAL. Review queue fills.
    """
    def pred(gender: str, prediction: int, confidence: float) -> dict:
        return {
            "domain": domain,
            "features": {
                "age":          28,
                "skills_score": 0.85,
                "experience":   5,
                "education":    "bachelor",
            },
            "sensitive_attrs": {"gender": gender},
            "prediction":      prediction,
            "confidence":      confidence,
        }

    return [
        # Phase 1: Clean baseline (1–10)
        *[pred("female" if i % 2 == 0 else "male", 1, 0.92) for i in range(10)],

        # Phase 2: Bias erupts (11–25) — all female rejected
        # At prediction #10 sliding window has 10 records.
        # Predictions 11-20 are all female=0 → window goes from mixed to biased.
        # By pred #20 DPD ≈ 0.6 → CRITICAL → BLOCK fires.
        *[pred("female", 0, 0.41) for _ in range(15)],

        # Phase 3: Severe sustained bias (26–60)
        *[pred("female", 0, 0.38) for _ in range(35)],
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_simulation(
    api_url: str,
    api_key: str,
    domain: str,
    speed_ms: int,
    quiet: bool = False,
) -> dict:
    """Run the full 60-prediction simulation. Returns summary stats."""

    headers = {
        "X-API-Key":    api_key,
        "Content-Type": "application/json",
    }

    # Verify backend is reachable
    try:
        resp = requests.get(f"{api_url}/health", timeout=5)
        resp.raise_for_status()
        health = resp.json()
        if not quiet:
            print(f"\n{BOLD}FairWall Demo Simulator{RESET}")
            print(f"  Backend:  {api_url}")
            print(f"  Tenant:   {api_key}")
            print(f"  Domain:   {domain}")
            print(f"  Domains loaded: {health.get('loaded_domains', [])}")
            print(f"  Speed:    {speed_ms}ms between predictions")
            print(f"  Segment:  {health.get('segment', '?')}")
            print()
    except Exception as e:
        print(f"{RED}ERROR: Cannot reach backend at {api_url}{RESET}")
        print(f"  {e}")
        print(f"\n  Make sure uvicorn is running:")
        print(f"  uvicorn backend.main:app --reload --port 8000")
        sys.exit(1)

    sequence = build_sequence(domain)
    total    = len(sequence)

    stats = {
        "total":    total,
        "released": 0,
        "flagged":  0,
        "adjusted": 0,
        "blocked":  0,
        "first_block_at": None,
        "errors":   0,
    }

    if not quiet:
        print(f"Starting simulation: {total} predictions")
        print(f"{'─' * 65}")
        print(f"  {'#':>3}  {'Gender':7}  {'Pred':6}  {'Decision':10}  {'Score':6}  {'Action'}")
        print(f"{'─' * 65}")

    phase_labels = {10: "Phase 2: Bias begins", 25: "Phase 3: Severe bias"}

    for i, payload in enumerate(sequence):
        n          = i + 1
        gender     = payload["sensitive_attrs"]["gender"]
        prediction = payload["prediction"]

        # Print phase separator
        if not quiet and n in phase_labels:
            print(f"\n  {DIM}── {phase_labels[n]} ──{RESET}")

        try:
            resp = requests.post(
                f"{api_url}/predict",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            decision   = data.get("final_decision", "?")
            score      = data.get("trust_score")
            action     = data.get("intervention_type", "none")
            warming_up = data.get("warming_up", False)

            # Track stats
            if decision == "released" and not data.get("flagged"):
                stats["released"] += 1
            elif decision == "flagged":
                stats["flagged"] += 1
            elif decision == "adjusted":
                stats["adjusted"] += 1
            elif decision == "blocked":
                stats["blocked"] += 1
                if stats["first_block_at"] is None:
                    stats["first_block_at"] = n

            if not quiet:
                score_str  = "warming" if warming_up else color_score(score)
                action_str = color_action(action)
                gender_str = f"{RED}female{RESET}" if gender == "female" else f"{CYAN}male{RESET}"
                pred_str   = f"{RED}REJECT{RESET}" if prediction == 0 else f"{GREEN}ACCEPT{RESET}"
                print(
                    f"  {n:>3}  {gender_str:16}  {pred_str:15}  "
                    f"{decision:10}  {score_str:14}  {action_str}"
                )

        except Exception as e:
            stats["errors"] += 1
            if not quiet:
                print(f"  {n:>3}  ERROR: {e}")

        # Delay between predictions
        if i < total - 1:
            time.sleep(speed_ms / 1000.0)

    # Print summary
    if not quiet:
        print(f"\n{'─' * 65}")
        print(f"\n{BOLD}Simulation complete{RESET}")
        print(f"  Released:  {stats['released']}")
        print(f"  Flagged:   {stats['flagged']}")
        print(f"  Adjusted:  {stats['adjusted']}")
        print(f"  {RED}Blocked:   {stats['blocked']}{RESET}")
        print(f"  Errors:    {stats['errors']}")
        if stats["first_block_at"]:
            rule14 = (
                f"{GREEN}✓ Rule 14 satisfied{RESET}"
                if stats["first_block_at"] <= 20
                else f"{RED}✗ Rule 14 VIOLATED — first block at #{stats['first_block_at']}{RESET}"
            )
            print(f"  First BLOCK: prediction #{stats['first_block_at']}  {rule14}")
        else:
            print(f"  {RED}WARNING: No BLOCKs fired — check bias engine{RESET}")
        print()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="FairWall demo bias simulation script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo/simulate_bias.py
  python demo/simulate_bias.py --api-url https://xxxx.ngrok-free.app
  python demo/simulate_bias.py --api-url https://fairwall-api-xxxx.run.app --api-key fw-acme-corp-2026
  python demo/simulate_bias.py --domain lending --speed 100
        """,
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="FairWall API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default="fw-demo-key-2026",
        help="FairWall API key (default: fw-demo-key-2026)",
    )
    parser.add_argument(
        "--domain",
        default="hiring",
        choices=["hiring", "lending", "admissions", "healthcare"],
        help="Domain to simulate bias in (default: hiring)",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=200,
        help="Milliseconds between predictions (default: 200). Use 100 for faster demo.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-prediction output, show summary only",
    )

    args = parser.parse_args()

    stats = run_simulation(
        api_url=args.api_url.rstrip("/"),
        api_key=args.api_key,
        domain=args.domain,
        speed_ms=args.speed,
        quiet=args.quiet,
    )

    # Exit with error code if Rule 14 violated
    if stats["first_block_at"] is None or stats["first_block_at"] > 20:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
