"""
evaluate.py — NDCG harness. Scores the ranker against your gold labels so weight
changes are MEASURED, not asserted. Since there's no leaderboard, this is our only
feedback loop before we spend a submission.

Usage:
  python evaluate.py --contested contested_set.json --coherence coherence.jsonl --gold gold.csv

gold.csv needs columns: candidate_id, gold_tier (0-5).
Reports NDCG@10 and NDCG@50 over the candidates you've labeled (the ranker's order
is graded; any top-k candidate missing a gold label is reported so you can label it).
"""

import argparse
import csv
import math

from rank_survivors import load_survivors, rank


def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked_tiers, k):
    gains = [(2 ** t - 1) for t in ranked_tiers[:k]]
    ideal = sorted([(2 ** t - 1) for t in ranked_tiers], reverse=True)[:k]
    idcg = dcg(ideal)
    return (dcg(gains) / idcg) if idcg > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--gold", default="gold.csv")
    args = ap.parse_args()

    gold = {}
    for row in csv.DictReader(open(args.gold)):
        try:
            gold[row["candidate_id"].strip()] = int(float(row["gold_tier"]))
        except (ValueError, KeyError):
            pass

    # Mirror rank.py's human floor: tier<=2 candidates are EXCLUDED from the submission,
    # so they must be excluded from both the ranking and the graded gold here — otherwise
    # the NDCG measures a pipeline we don't ship (and a floored fake can pollute the score).
    floor = {cid for cid, t in gold.items() if t <= 2}
    graded = {cid: t for cid, t in gold.items() if cid not in floor}

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    scored = rank(survivors, incoherent)
    order = [r["candidate_id"] for _, r in scored if r["candidate_id"] not in floor]

    labeled_order = [(cid, graded[cid]) for cid in order if cid in graded]
    tiers = [t for _, t in labeled_order]

    missing_top = [cid for cid in order[:50] if cid not in graded]

    print(f"gold (tier 3-5 graded): {len(graded)} | human-floored (tier<=2 excluded): "
          f"{len(floor)} | labeled & in ranking: {len(tiers)}")
    if tiers:
        print(f"\n  NDCG@10 = {ndcg_at_k(tiers, 10):.3f}")
        print(f"  NDCG@50 = {ndcg_at_k(tiers, 50):.3f}")
        print(f"\n  ranked order of labeled candidates (tier): "
              + " ".join(str(t) for t in tiers[:25]))
    if missing_top:
        print(f"\n  WARNING: {len(missing_top)} of the ranker's top 50 are unlabeled "
              f"-> NDCG is incomplete. Label these for an accurate score:")
        for cid in missing_top[:15]:
            print("   ", cid)


if __name__ == "__main__":
    main()