"""
review.py — summarize dev-set labels and surface the top for the human gold-audit.

Usage:
  python review.py --labels labels.jsonl --contested contested_set.json --top 60
"""

import argparse
import json
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="labels.jsonl")
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--top", type=int, default=60)
    args = ap.parse_args()

    labels = [json.loads(l) for l in open(args.labels) if l.strip()]
    by_id = {l["candidate_id"]: l for l in labels}
    cand = {r["candidate_id"]: r["candidate"]["profile"]
            for r in json.load(open(args.contested))}

    tiers = Counter(l.get("tier") for l in labels)
    srcs = Counter(l.get("source") for l in labels)
    print(f"labels: {len(labels)} | sources: {dict(srcs)}")
    print("tier distribution: " + "  ".join(
        f"T{t}={tiers.get(t,0)}" for t in [5, 4, 3, 2, 1, 0, None]))

    ranked = sorted(labels, key=lambda l: l.get("first_pass_score", 0), reverse=True)
    print(f"\n=== TOP {args.top} for gold-audit (read tier vs your judgment) ===")
    print(f"{'fps':>6} {'T':>2} {'id':12} {'title':30} evidence | concerns")
    for l in ranked[:args.top]:
        p = cand.get(l["candidate_id"], {})
        ev = (l.get("decisive_evidence", "") or l.get("source", ""))[:34]
        cn = (l.get("concerns", "") or "")[:30]
        print(f"{l.get('first_pass_score',0):6.1f} {str(l.get('tier')):>2} "
              f"{l['candidate_id']:12} {(p.get('current_title','') or '')[:29]:30} {ev} | {cn}")


if __name__ == "__main__":
    main()