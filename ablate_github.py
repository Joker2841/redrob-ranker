"""
ablate_github.py — clean A/B of the github signal under the SHIPPED (floored) eval.
Measures floored NDCG@10/@50 with github IN vs OUT of depth, same gold, only github
toggled. Settles whether github carried genuine signal or was an unfloored artifact.

Usage:
  python ablate_github.py --contested contested_set.json --coherence coherence.jsonl --gold gold.csv
"""
import argparse, csv
import rank_survivors as rs
from rank_survivors import load_survivors, rank
from evaluate import ndcg_at_k


def load_gold(path):
    g = {}
    for row in csv.DictReader(open(path)):
        try:
            g[row["candidate_id"].strip()] = int(float(row["gold_tier"]))
        except (ValueError, KeyError):
            pass
    return g


def depth_with_github(c):
    sig = c.get("redrob_signals", {}) or {}
    breadth = min(1.0, rs.n_backed_relevant(c) / 4.0)
    github = min(1.0, (sig.get("github_activity_score") or 0) / 100.0)
    base = 0.6 * breadth + 0.4 * github
    asx = rs.best_relevant_assessment(c)
    return 0.5 * (asx / 100.0) + 0.5 * base if asx is not None else base


def depth_no_github(c):
    breadth = min(1.0, rs.n_backed_relevant(c) / 4.0)
    asx = rs.best_relevant_assessment(c)
    return 0.6 * (asx / 100.0) + 0.4 * breadth if asx is not None else 0.85 * breadth


def measure(depth_fn, survivors, incoherent, graded):
    rs.depth_score = depth_fn          # monkeypatch the scorer's depth
    scored = rank(survivors, incoherent)
    tiers = [graded[r["candidate_id"]] for _, r in scored if r["candidate_id"] in graded]
    return ndcg_at_k(tiers, 10), ndcg_at_k(tiers, 50), tiers[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--gold", default="gold.csv")
    a = ap.parse_args()
    survivors, incoherent, _ = load_survivors(a.contested, a.coherence)
    gold = load_gold(a.gold)
    graded = {c: t for c, t in gold.items() if t > 2}   # floored, same as shipped pipeline
    g10, g50, gt = measure(depth_with_github, survivors, incoherent, graded)
    n10, n50, nt = measure(depth_no_github, survivors, incoherent, graded)
    print(f"floored gold: {len(graded)} tier-3-5 candidates\n")
    print(f"WITH github:    NDCG@10={g10:.3f}  @50={g50:.3f}   top12 tiers: {gt}")
    print(f"WITHOUT github: NDCG@10={n10:.3f}  @50={n50:.3f}   top12 tiers: {nt}")
    print(f"\ndelta @10 = {g10-n10:+.3f}   delta @50 = {g50-n50:+.3f}")
    print("interpretation: delta near 0 -> github is noise, keep it OUT. "
          "large positive delta -> github helps the genuine ranking (then weigh vs defensibility).")


if __name__ == "__main__":
    main()