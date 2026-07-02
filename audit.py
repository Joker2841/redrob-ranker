"""
audit.py — overfit + top-10 stability audit for the ranker.

Answers the question the hidden leaderboard can't: is the shipped calibration
trustworthy, or is it overfit to a small gold set / fragile to weights we set by
hand? Reuses the EXACT NDCG methodology in evaluate.py so the numbers are
directly comparable to sweep.py, and imports the TRUE shipped weights from
rank_survivors (no hardcoded "current" config that can drift).

Runs on the same inputs as the rest of the pipeline:

  python audit.py --contested contested_set.json --coherence coherence.jsonl --gold gold.csv
"""

import argparse
import csv
import itertools

from rank_survivors import load_survivors, rank, W, COH_PENALTY
from evaluate import ndcg_at_k

EPS = 0.005  # NDCG@10 gap within which two configs are "tied" (gold can't separate)


def load_gold(path):
    gold = {}
    for row in csv.DictReader(open(path)):
        try:
            gold[row["candidate_id"].strip()] = int(float(row["gold_tier"]))
        except (ValueError, KeyError):
            pass
    return gold


def ranked_order(survivors, incoherent, weights, coh, floor):
    """Return the ranked candidate_id list, mirroring the shipped human floor."""
    scored = rank(survivors, incoherent, weights, coh)
    return [r["candidate_id"] for _, r in scored if r["candidate_id"] not in floor]


def tiers_of(order, graded):
    return [graded[c] for c in order if c in graded]


def country_of(rec):
    return ((rec.get("candidate", {}) or {}).get("profile", {}) or {}).get("country")


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a or b) else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--gold", default="gold.csv")
    args = ap.parse_args()

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    country = {r["candidate_id"]: country_of(r) for r in survivors}

    gold = load_gold(args.gold)
    floor = {c for c, t in gold.items() if t <= 2}          # human-floored fakes
    graded = {c: t for c, t in gold.items() if t > 2}       # tier 3-5, gradeable
    total5 = sum(1 for t in graded.values() if t >= 5)

    print(f"survivors: {len(survivors)} | gold graded (tier 3-5): {len(graded)} "
          f"({total5} tier-5) | human-floored (tier<=2): {len(floor)}")
    if len(graded) < 10:
        print("\n[!] Fewer than 10 gradeable gold candidates among survivors — NDCG@10 "
              "is under-powered. Run against the full-pool contested_set.json.\n")

    # ---- 1. Shipped-config baseline (the config you actually submit) ----
    base_order = ranked_order(survivors, incoherent, W, COH_PENALTY, floor)
    base_tiers = tiers_of(base_order, graded)
    base_top10 = base_order[:10]
    b10, b50 = ndcg_at_k(base_tiers, 10), ndcg_at_k(base_tiers, 50)
    print("\n=== 1. SHIPPED CONFIG (ground truth) ===")
    print(f"  W = {W}  coh = {COH_PENALTY}")
    print(f"  NDCG@10 = {b10:.3f}   NDCG@50 = {b50:.3f}   "
          f"(labeled-in-order: {len(base_tiers)})")

    # ---- 2. Gold discrimination + top-10 churn across near-tied configs ----
    depths = [0.40, 0.50, 0.60, 0.70]
    yoes = [0.15, 0.25, 0.35]
    locs = [0.05, 0.10, 0.15]
    priors = [0.0, 0.10, 0.15]
    cohs = [0.30, 0.40, 0.55, 0.70]

    configs = []
    for d, y, l, p, ch in itertools.product(depths, yoes, locs, priors, cohs):
        w = dict(depth=d, yoe=y, loc=l, prior=p)
        order = ranked_order(survivors, incoherent, w, ch, floor)
        n10 = ndcg_at_k(tiers_of(order, graded), 10)
        configs.append((n10, w, ch, order[:10]))

    best10 = max(c[0] for c in configs) if configs else 0.0
    tied = [c for c in configs if c[0] >= best10 - EPS]
    swing = set()
    jac = []
    for n10, w, ch, top10 in tied:
        swing |= (set(top10) - set(base_top10))
        jac.append(jaccard(top10, base_top10))
    # shipped top-10 members that some tied config would drop
    at_risk = [c for c in base_top10 if any(c not in set(t[3]) for t in tied)]
    rank_of = {c: i + 1 for i, c in enumerate(base_order)}

    def label(c):
        if c in graded:
            return f"tier {graded[c]}"
        if c in floor:
            return "tier<=2 (floored)"
        return "UNLABELED  <- label this"

    print("\n=== 2. GOLD DISCRIMINATION (can the gold pick the right config?) ===")
    print(f"  grid size: {len(configs)} configs")
    print(f"  best gold NDCG@10 = {best10:.3f}; shipped = {b10:.3f} "
          f"(gap {best10 - b10:+.3f})")
    print(f"  configs TIED within {EPS} of best: {len(tied)} / {len(configs)}")
    if jac:
        print(f"  mean top-10 Jaccard of tied configs vs shipped: {sum(jac)/len(jac):.2f}")
    print(f"  SWING candidates (in some tied top-10 but NOT shipped top-10): {len(swing)}")
    if swing or at_risk:
        print("\n  Contested top-10 slots — label these to lock the bottom of the top-10:")
        for c in sorted(at_risk, key=lambda c: rank_of.get(c, 999)):
            print(f"    [shipped #{rank_of.get(c,'?'):>2}, at risk]  {c}   {label(c)}")
        for c in sorted(swing, key=lambda c: rank_of.get(c, 999)):
            print(f"    [shipped #{rank_of.get(c,'?'):>2}, challenger] {c}   {label(c)}")
    print("    -> few tied configs + high Jaccard + few swing candidates = your top-10 is")
    print("       well-determined; only the listed slots are genuinely contested.")

    # ---- 3. Location-signal sensitivity ----
    print("\n=== 3. LOCATION SENSITIVITY (is India=1.0/else=0.35 load-bearing?) ===")
    print(f"  {'loc_w':>6} {'NDCG@10':>8} {'top10_churn':>12} {'non-India@10':>12}")
    for lw in [0.00, 0.05, 0.10, 0.15, 0.20]:
        w = dict(W, loc=lw)
        order = ranked_order(survivors, incoherent, w, COH_PENALTY, floor)
        n10 = ndcg_at_k(tiers_of(order, graded), 10)
        t10 = order[:10]
        churn = len(base_top10) - len(set(t10) & set(base_top10))
        non_in = sum(1 for c in t10 if country.get(c) != "India")
        print(f"  {lw:6.2f} {n10:8.3f} {churn:11d}  {non_in:11d}")
    print("    -> if NDCG@10 barely moves while churn/non-India counts swing, the")
    print("       location weight is an unvalidated assumption steering your top-10.")


if __name__ == "__main__":
    main()