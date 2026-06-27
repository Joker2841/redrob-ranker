"""
rank.py — the submission generator. Runs the full pipeline over the entire pool
and writes the top-100 CSV in the exact format validate_submission.py requires.

Pipeline (CPU-only, no network — fits the ranking-step budget):
  load all -> structural honeypot gate (floor traps) -> JD disqualifier floor
  (consulting-only careers) -> relevance floor (ML role/skill) -> calibrated
  structured score (depth + yoe + location, x availability, x coherence penalty
  where a precomputed flag exists) -> sort -> top 100 -> grounded reasoning.

Coherence flags are precomputed offline (coherence_check.py); candidates with no
flag get no penalty. For full safety, coherence-check rank.py's preliminary top
~200 offline and re-run.

Usage:
  python rank.py --data data/candidates.jsonl --coherence coherence.jsonl --out team_xxx.csv
"""

import argparse
import csv
import json

from ranker.load import iter_candidates
from ranker.consistency import analyze
from compare import is_consulting, best_relevant_assessment, RELEVANT
from rank_survivors import score, n_backed_relevant, TODAY

RELEVANT_TITLE = ("machine learning", "ml engineer", "ml ", "applied scientist",
                  "applied ml", "ai engineer", "ai specialist", "data scientist",
                  "nlp", "search engineer", "recommendation", "research engineer",
                  "information retrieval", "ranking", "mlops")


def consulting_only(c):
    hist = c.get("career_history", []) or []
    return bool(hist) and all(is_consulting(h.get("company")) for h in hist)


def ml_relevant(c):
    title = (c.get("profile", {}) or {}).get("current_title", "") or ""
    if any(t in title.lower() for t in RELEVANT_TITLE):
        return True
    # non-ML title qualifies only with REAL assessed depth (rare genuine crossover),
    # not one tangential skill name — that was letting frontend/cloud roles through.
    return best_relevant_assessment(c) is not None and n_backed_relevant(c) >= 2


def reason(c, s):
    """Grounded reasoning from STRUCTURED signals only — descriptions are noise."""
    p = c.get("profile", {}) or {}
    hist = c.get("career_history", []) or []
    comps = [f"{h.get('company')} ({h.get('industry')})" for h in hist[:2] if h.get("company")]
    parts = [f"{p.get('current_title')}, {p.get('years_of_experience')} yrs experience"]
    if comps:
        parts.append("roles at " + ", ".join(comps))
    if s["asx"] is not None:
        parts.append(f"verified skill assessment {int(s['asx'])} on ranking/retrieval")
    else:
        parts.append("backed ranking/retrieval skills")
    if p.get("country") == "India":
        parts.append("India-based")
    if s["amult"] >= 0.97:
        parts.append("actively available")
    elif s["amult"] < 0.7:
        parts.append("limited availability")
    if not s["coh"]:
        parts.append("coherence-flagged — scale/domain claims need interview verification")
    return "; ".join(parts) + "."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/candidates.jsonl")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--out", default="submission.csv")
    ap.add_argument("--prelim-out", default=None,
                    help="dump top-N (structured score) as a set for coherence re-checking")
    ap.add_argument("--prelim-n", type=int, default=300)
    ap.add_argument("--gold", default=None,
                    help="human gold labels (csv); candidates labeled tier<=2 are floored "
                         "as human-verified fakes, overriding stochastic coherence")
    args = ap.parse_args()

    incoherent = set()
    try:
        for l in open(args.coherence):
            r = json.loads(l)
            if r.get("coherent") is False:
                incoherent.add(r["candidate_id"])
    except FileNotFoundError:
        print(f"note: {args.coherence} not found — proceeding with no coherence penalty")

    human_floor = set()
    if args.gold:
        for row in csv.DictReader(open(args.gold)):
            try:
                if int(float(row["gold_tier"])) <= 2:
                    human_floor.add(row["candidate_id"].strip())
            except (ValueError, KeyError):
                pass
        print(f"human-verified floor: {len(human_floor)} candidate(s) excluded (gold tier<=2)")

    n_seen = n_honey = n_consult = n_irrel = n_human = 0
    rows = []
    for c in iter_candidates(args.data):
        n_seen += 1
        if c["candidate_id"] in human_floor:
            n_human += 1
            continue
        if analyze(c, TODAY)["hard"]:
            n_honey += 1
            continue
        if consulting_only(c):
            n_consult += 1
            continue
        if not ml_relevant(c):
            n_irrel += 1
            continue
        s = score({"candidate": c, "first_pass_score": 0}, incoherent)
        rows.append((round(s["final"], 4), c["candidate_id"], c, s))

    # non-increasing score by rank; ties broken by candidate_id ascending
    rows.sort(key=lambda r: (-r[0], r[1]))
    top = rows[:100]

    if args.prelim_out:
        prelim = [{"candidate_id": cid, "first_pass_score": sc, "candidate": c}
                  for sc, cid, c, s in rows[:args.prelim_n]]
        json.dump(prelim, open(args.prelim_out, "w"))
        print(f"dumped top {len(prelim)} -> {args.prelim_out} (coherence-check these, then re-run)")

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candidate_id", "rank", "score", "reasoning"])
        for i, (sc, cid, c, s) in enumerate(top, 1):
            w.writerow([cid, i, f"{sc:.4f}", reason(c, s)])

    print(f"scanned {n_seen} | floored: {n_human} human-verified, {n_honey} honeypots, "
          f"{n_consult} consulting-only, {n_irrel} non-relevant | eligible {len(rows)} "
          f"| wrote top {len(top)} -> {args.out}")
    if len(rows) < 100:
        print(f"WARNING: only {len(rows)} eligible candidates (<100).")


if __name__ == "__main__":
    main()