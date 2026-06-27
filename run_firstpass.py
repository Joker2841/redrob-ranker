"""
run_firstpass.py — surface (and optionally dump) the contested top set.

Examples:
    # just look at the top 30
    python run_firstpass.py --path data/candidates.json --show 30

    # dump the top 500 contested profiles to a file for the labeling step
    python run_firstpass.py --path data/candidates.json --show 30 \
        --out contested_set.json --dump 500

Honeypots are TAGGED, not removed — we want them in the labeled set as
hard-negatives. The final ranker is what floors them.
"""

import argparse
import json
from datetime import date

from ranker.load import load_candidates
from ranker.consistency import check_consistency, parse_date
from ranker.firstpass import first_pass_score


def data_reference_date(cands):
    mx = None
    for c in cands:
        d = parse_date((c.get("redrob_signals", {}) or {}).get("last_active_date", ""))
        if d and (mx is None or d > mx):
            mx = d
    return mx or date(2026, 6, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="/mnt/project/sample_candidates.json")
    ap.add_argument("--show", type=int, default=30, help="rows to print")
    ap.add_argument("--out", default=None, help="optional JSON file to dump the contested set")
    ap.add_argument("--dump", type=int, default=500, help="how many to dump to --out")
    args = ap.parse_args()

    cands = load_candidates(args.path)
    dd = data_reference_date(cands)

    rows = []
    for c in cands:
        s, comp = first_pass_score(c)
        cons = check_consistency(c, dd)
        rows.append((s, c, comp, cons))
    rows.sort(key=lambda r: r[0], reverse=True)

    n_hp = sum(1 for _, _, _, cons in rows if cons["hard"])
    print(f"loaded {len(cands)} | data_date={dd} | honeypots flagged: {n_hp} | top {args.show}\n")
    print(f"{'score':>6}  {'id':12} {'title':26} {'yoe':>4}  {'location':14} "
          f"{'dec':>3} {'str':>3} {'tool':>4} {'off':>3} {'bsk':>4}  flags")
    print("-" * 110)
    for s, c, comp, cons in rows[:args.show]:
        p = c["profile"]
        tag = "HONEYPOT" if cons["hard"] else (f"soft×{cons['n_soft']}" if cons["n_soft"] else "")
        print(f"{s:6.2f}  {c['candidate_id']:12} {p['current_title'][:25]:26} "
              f"{p['years_of_experience']:>4.1f}  {p['location'][:13]:14} "
              f"{comp['decisive']:>3.0f} {comp['strong']:>3.0f} {comp['tools']:>4.0f} "
              f"{comp['off_area']:>3.0f} {comp['backed_skill']:>4.1f}  {tag}")
        if cons["reasons"]:
            print("         ! " + "; ".join(cons["reasons"][:3]))

    if args.out:
        dump = [{
            "candidate_id": c["candidate_id"],
            "first_pass_score": round(s, 3),
            "components": comp,
            "consistency": cons,
            "candidate": c,
        } for s, c, comp, cons in rows[:args.dump]]
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=1)
        print(f"\nwrote top {len(dump)} contested profiles -> {args.out}")


if __name__ == "__main__":
    main()