"""
sweep.py — calibrate the ranker EMPIRICALLY. Tries a grid of weightings (depth,
yoe, location, fps-prior) and coherence-penalty strengths, re-ranks for each, and
reports NDCG@10/@50 against the gold set. Settles the knobs with evidence instead
of guesses. Only relative base-weights matter (availability + coherence are
multipliers), so the grid sweeps ratios.

Usage:
  python sweep.py --contested contested_set.json --coherence coherence.jsonl --gold gold.csv
"""

import argparse
import csv
import itertools

from rank_survivors import load_survivors, rank, W, COH_PENALTY
from evaluate import ndcg_at_k


def load_gold(path):
    gold = {}
    for row in csv.DictReader(open(path)):
        try:
            gold[row["candidate_id"].strip()] = int(float(row["gold_tier"]))
        except (ValueError, KeyError):
            pass
    return gold


def eval_config(survivors, incoherent, gold, weights, coh):
    scored = rank(survivors, incoherent, weights, coh)
    tiers = [gold[r["candidate_id"]] for _, r in scored if r["candidate_id"] in gold]
    n5_top10 = sum(1 for t in tiers[:10] if t >= 5)
    return ndcg_at_k(tiers, 10), ndcg_at_k(tiers, 50), n5_top10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--gold", default="gold.csv")
    args = ap.parse_args()

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    gold = load_gold(args.gold)
    gold = {cid: t for cid, t in gold.items() if t > 2}  # mirror rank.py human floor (tier<=2 excluded)
    total5 = sum(1 for t in gold.values() if t >= 5)
    print(f"gold (tier 3-5 graded): {len(gold)} labeled, {total5} tier-5\n")

    depths = [0.40, 0.50, 0.60, 0.70]
    yoes   = [0.15, 0.25, 0.35]
    locs   = [0.05, 0.10, 0.15]
    priors = [0.0, 0.10, 0.15]
    cohs   = [0.30, 0.40, 0.55, 0.70]

    results = []
    for d, y, l, p, ch in itertools.product(depths, yoes, locs, priors, cohs):
        w = dict(depth=d, yoe=y, loc=l, prior=p)
        n10, n50, n5 = eval_config(survivors, incoherent, gold, w, ch)
        results.append((n10, n50, n5, w, ch))

    # baseline = the ACTUAL shipped config, imported from rank_survivors so this
    # comparison line can never drift from what rank.py submits.
    b10, b50, b5 = eval_config(survivors, incoherent, gold, W, COH_PENALTY)

    results.sort(key=lambda r: (r[0], r[1]), reverse=True)
    print(f"CURRENT  NDCG@10={b10:.3f} @50={b50:.3f}  tier5_in_top10={b5}/{min(10,total5)}"
          f"   (depth .50 yoe .25 loc .10 prior .15 coh .40)\n")
    print("TOP CONFIGS BY NDCG@10:")
    print(f"{'@10':>6} {'@50':>6} {'5@10':>5}  depth  yoe   loc  prior  coh")
    print("-" * 60)
    seen = set()
    shown = 0
    for n10, n50, n5, w, ch in results:
        key = (round(n10, 4), round(n50, 4), w["depth"], w["yoe"], w["prior"], ch)
        if key in seen:
            continue
        seen.add(key)
        print(f"{n10:6.3f} {n50:6.3f} {n5:>4}/{min(10,total5):<2} "
              f"{w['depth']:.2f}  {w['yoe']:.2f}  {w['loc']:.2f}  {w['prior']:.2f}  {ch:.2f}")
        shown += 1
        if shown >= 15:
            break


if __name__ == "__main__":
    main()