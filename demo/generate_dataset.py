"""
demo/generate_dataset.py
Generates a synthetic hiring dataset with embedded gender bias.
Women selected 34% less than equally qualified men.

Usage:
    cd fairwall
    python demo/generate_dataset.py
    # outputs: demo/hiring_dataset.csv
"""

import csv
import os
import random
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "hiring_dataset.csv"
RANDOM_SEED = 42
N_SAMPLES = 1000


def generate_dataset(n: int = N_SAMPLES, seed: int = RANDOM_SEED) -> list[dict]:
    random.seed(seed)
    rows = []

    for i in range(n):
        age = random.randint(22, 55)
        education = random.choices(
            ["high_school", "bachelor", "master", "phd"],
            weights=[15, 50, 28, 7],
        )[0]
        experience = max(0, random.randint(0, 20) - (4 if education == "high_school" else 0))
        skills_score = round(random.gauss(0.65, 0.15), 3)
        skills_score = max(0.0, min(1.0, skills_score))
        gender = random.choices(["male", "female"], weights=[52, 48])[0]
        ethnicity = random.choices(["A", "B", "C", "D"], weights=[60, 20, 12, 8])[0]
        age_group = "young" if age < 30 else ("mid" if age < 45 else "senior")

        # Compute a merit score (gender-blind)
        edu_bonus = {"high_school": 0.0, "bachelor": 0.1, "master": 0.2, "phd": 0.3}
        merit = (
            skills_score * 0.5
            + min(experience / 20, 1.0) * 0.3
            + edu_bonus[education] * 0.2
        )

        # Base selection probability from merit
        base_prob = merit * 0.85

        # Inject gender bias — women have 34% lower chance at same merit
        if gender == "female":
            selection_prob = base_prob * 0.66
        else:
            selection_prob = base_prob

        # Small noise
        selection_prob += random.gauss(0, 0.05)
        selection_prob = max(0.0, min(1.0, selection_prob))

        selected = 1 if random.random() < selection_prob else 0

        rows.append({
            "id": f"cand_{i+1:04d}",
            "age": age,
            "education": education,
            "experience": experience,
            "skills_score": skills_score,
            "gender": gender,
            "ethnicity": ethnicity,
            "age_group": age_group,
            "selected": selected,
        })

    return rows


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def print_stats(rows: list[dict]) -> None:
    total = len(rows)
    male = [r for r in rows if r["gender"] == "male"]
    female = [r for r in rows if r["gender"] == "female"]
    male_rate = sum(r["selected"] for r in male) / len(male)
    female_rate = sum(r["selected"] for r in female) / len(female)
    disparity = (male_rate - female_rate) / male_rate * 100

    print(f"Total candidates : {total}")
    print(f"Male             : {len(male)}  selected rate: {male_rate:.1%}")
    print(f"Female           : {len(female)}  selected rate: {female_rate:.1%}")
    print(f"Gender disparity : {disparity:.1f}% lower selection rate for women")
    print(f"Overall selected : {sum(r['selected'] for r in rows)}/{total}")


def main():
    print(f"Generating {N_SAMPLES} synthetic hiring records (seed={RANDOM_SEED})...")
    rows = generate_dataset()
    save_csv(rows, OUTPUT_PATH)
    print(f"Saved to: {OUTPUT_PATH}\n")
    print_stats(rows)
    print(f"\nLoad into pandas: df = pd.read_csv('{OUTPUT_PATH}')")


if __name__ == "__main__":
    main()


# ── test ──────────────────────────────────────────────────────────────────────
# python demo/generate_dataset.py
# Expected output: ~34% disparity in selection rate (women vs men)
