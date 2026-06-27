"""
goldaudit.py — fast human gold-audit. For the ranker's top N survivors it prints
the CONDENSED CAREER (company, industry, dates, key line) + structured signals +
a proposed tier, and writes gold_template.csv for you to edit. Reading the career
inline is seconds vs. minutes of raw JSON, so you can tier the top set quickly.

Usage:
  python goldaudit.py --contested contested_set.json --coherence coherence.jsonl --top 20

Then edit gold_template.csv -> set the 'gold_tier' column -> save as gold.csv.
"""

import argparse
import csv

from rank_survivors import load_survivors, rank, TODAY
from compare import is_consulting


def propose(s, p):
    """Rough proposed tier from signals — you are the authority, this is a draft."""
    if not s["coh"]:
        return 2
    y = float(p.get("years_of_experience") or 0)
    strong = s["depth"] >= 0.75 and p.get("country") == "India"
    if strong and 6 <= y <= 8:
        return 5
    if strong and 5 <= y < 10:
        return 4
    if s["depth"] >= 0.6 and 4 <= y < 10:
        return 4
    return 3


def career_line(c):
    out = []
    for h in (c.get("career_history", []) or [])[:4]:
        d = (h.get("description") or "").strip().replace("\n", " ")
        out.append(f"    {h.get('title')} @ {h.get('company')} "
                   f"({h.get('industry')}, {h.get('duration_months')}mo): {d[:150]}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out", default="gold_template.csv")
    args = ap.parse_args()

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    scored = rank(survivors, incoherent)[:args.top]

    rows = []
    for i, (s, r) in enumerate(scored, 1):
        c = r["candidate"]
        p = c.get("profile", {}) or {}
        sig = c.get("redrob_signals", {}) or {}
        nc = sum(1 for h in (c.get("career_history", []) or []) if is_consulting(h.get("company")))
        prop = propose(s, p)
        print("=" * 96)
        print(f"#{i}  score={s['final']:.2f}  {c['candidate_id']}  PROPOSED TIER={prop}"
              f"{'   (coherence-flagged)' if not s['coh'] else ''}")
        print(f"  {p.get('current_title')} | yoe={p.get('years_of_experience')} | "
              f"{p.get('country')} | depth={s['depth']:.2f} asx={s['asx']} "
              f"| avail={s['amult']:.2f} resp={sig.get('recruiter_response_rate')} "
              f"otw={sig.get('open_to_work_flag')} | consulting_roles={nc}")
        print(career_line(c))
        rows.append({"rank": i, "candidate_id": c["candidate_id"],
                     "title": p.get("current_title"), "yoe": p.get("years_of_experience"),
                     "proposed_tier": prop, "gold_tier": prop, "notes": ""})

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "candidate_id", "title", "yoe",
                                          "proposed_tier", "gold_tier", "notes"])
        w.writeheader()
        w.writerows(rows)
    print("=" * 96)
    print(f"\nwrote {len(rows)} rows -> {args.out}")
    print("Edit the 'gold_tier' column where you disagree, save as gold.csv, then run evaluate.py")


if __name__ == "__main__":
    main()