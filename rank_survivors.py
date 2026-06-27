"""
rank_survivors.py — rank survivors (passed the structural gate) by signals that
CANNOT be faked by boilerplate: verified depth, yoe-fit, availability, location.
fps is only a weak topical prior (it got gamed). Coherence-flagged survivors take
a heavy penalty. Scoring is exposed as importable functions for goldaudit/evaluate.

Weights are provisional — calibrated against the gold set via evaluate.py.

Usage:
  python rank_survivors.py --contested contested_set.json --coherence coherence.jsonl --top 25
"""

import argparse
import json
from datetime import date

from ranker.consistency import analyze, parse_date
from compare import best_relevant_assessment, RELEVANT

# Calibrated against the gold set via sweep.py. prior=0.0 because fps (keyword
# density) measured zero ranking value on this templated data; yoe weight is high
# because the JD anchors hard on the 5-9 band. Only relative weights matter
# (availability + coherence are multipliers).
W = dict(depth=0.40, yoe=0.35, loc=0.10, prior=0.00)
COH_PENALTY = 0.50   # halve a coherence-flagged score; sweep-indifferent in 0.30-0.70
TODAY = date(2026, 5, 27)


def yoe_fit(y):
    if 6 <= y <= 8: return 1.0
    if 5 <= y < 10: return 0.85
    if 4 <= y < 11: return 0.65
    if 3 <= y < 12: return 0.45
    return 0.25


def n_backed_relevant(c):
    assess = (c.get("redrob_signals", {}) or {}).get("skill_assessment_scores", {}) or {}
    n = 0
    for s in c.get("skills", []) or []:
        name = (s.get("name") or "").lower()
        if any(t in name for t in RELEVANT):
            if (s.get("name") in assess or (s.get("endorsements") or 0) >= 10
                    or (s.get("duration_months") or 0) >= 24):
                n += 1
    return n


def depth_score(c):
    # github_activity KEPT: the ablation (ablate_github.py) shows it adds +0.086 to
    # floored NDCG@10. A random signal can't improve NDCG, so it carries real tier
    # information; its low 0.107 correlation with assessment means it's COMPLEMENTARY
    # (independent signal), not redundant. The -1 missing-value sentinel is clamped to 0.
    sig = c.get("redrob_signals", {}) or {}
    breadth = min(1.0, n_backed_relevant(c) / 4.0)
    github = max(0.0, min(1.0, (sig.get("github_activity_score") or 0) / 100.0))
    base = 0.6 * breadth + 0.4 * github
    asx = best_relevant_assessment(c)
    if asx is not None:
        return 0.5 * (asx / 100.0) + 0.5 * base
    return base


def availability_mult(sig, today=TODAY):
    la = parse_date(sig.get("last_active_date"))
    act_mo = ((today.year - la.year) * 12 + (today.month - la.month)) if la else 12
    recency = max(0.4, 1.0 - act_mo / 24.0)
    resp = sig.get("recruiter_response_rate")
    resp = 0.5 if resp is None else float(resp)
    otw = 1.0 if sig.get("open_to_work_flag") else 0.8
    raw = 0.45 * recency + 0.35 * resp + 0.20 * otw
    return max(0.55, min(1.05, 0.55 + 0.5 * raw))


def load_survivors(contested_path, coherence_path):
    """Return (survivor recs, incoherent id set, fps_max). Survivors pass the gate."""
    recs = json.load(open(contested_path))
    incoherent = set()
    try:
        for l in open(coherence_path):
            r = json.loads(l)
            if r.get("coherent") is False:
                incoherent.add(r["candidate_id"])
    except FileNotFoundError:
        pass
    fps_max = max((r.get("first_pass_score", 0) for r in recs), default=1) or 1
    survivors = [r for r in recs if not analyze(r["candidate"], TODAY)["hard"]]
    return survivors, incoherent, fps_max


def score(rec, incoherent, weights=W, coh_penalty=COH_PENALTY):
    """Score one survivor record. Returns dict with final + component breakdown."""
    c = rec["candidate"]
    p = c.get("profile", {}) or {}
    sig = c.get("redrob_signals", {}) or {}
    depth = depth_score(c)
    yf = yoe_fit(float(p.get("years_of_experience") or 0))
    loc = 1.0 if p.get("country") == "India" else 0.35
    prior = max(0.0, min(1.0, (rec.get("first_pass_score", 0) - 18) / 22.0))
    base = (weights["depth"] * depth + weights["yoe"] * yf
            + weights["loc"] * loc + weights["prior"] * prior)
    amult = availability_mult(sig)
    coh = c["candidate_id"] not in incoherent
    final = base * amult * (1.0 if coh else coh_penalty)
    return {"final": final, "depth": depth, "yf": yf, "loc": loc,
            "amult": amult, "coh": coh, "asx": best_relevant_assessment(c)}


def rank(survivors, incoherent, weights=W, coh_penalty=COH_PENALTY):
    scored = [(score(r, incoherent, weights, coh_penalty), r) for r in survivors]
    scored.sort(key=lambda t: t[0]["final"], reverse=True)
    return scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    scored = rank(survivors, incoherent)
    print(f"ranked {len(scored)} survivors | top {args.top}\n")
    print(f"{'#':>3} {'score':>5} {'id':12} {'yoe':>4} {'IN':>2} {'asx':>3} {'dep':>4} "
          f"{'yf':>4} {'avl':>4} {'coh':>3} title")
    print("-" * 100)
    for i, (s, r) in enumerate(scored[:args.top], 1):
        p = r["candidate"].get("profile", {})
        print(f"{i:>3} {s['final']:5.2f} {r['candidate_id']:12} "
              f"{p.get('years_of_experience',0):>4.1f} "
              f"{'IN' if p.get('country')=='India' else '  ':>2} "
              f"{('' if s['asx'] is None else int(s['asx'])):>3} {s['depth']:>4.2f} "
              f"{s['yf']:>4.2f} {s['amult']:>4.2f} {'Y' if s['coh'] else 'x':>3} "
              f"{(p.get('current_title','') or '')[:30]}")


if __name__ == "__main__":
    main()