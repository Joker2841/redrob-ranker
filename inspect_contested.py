"""
inspect_contested.py — dump full profiles + per-signal score breakdowns for a set
of candidates, aligned to the JD must-haves, so contested top-10 tiers can be
adjudicated from EVIDENCE rather than from the ranker's own opinion.

  python inspect_contested.py --contested contested_set.json --coherence coherence.jsonl --gold gold.csv
  # or inspect any candidates:
  python inspect_contested.py --ids CAND_0052328 CAND_0074735

Defaults to the six contested candidates the audit surfaced. This does NOT change
any tier — it lays out the facts so YOU decide, keeping the gold an independent check.
"""

import argparse
import csv

from rank_survivors import load_survivors, rank, score, W, n_backed_relevant
from compare import RELEVANT

DEFAULT_IDS = ["CAND_0098454", "CAND_0074735", "CAND_0081053",
               "CAND_0052328", "CAND_0000031", "CAND_0053591"]


def load_gold(path):
    g = {}
    for row in csv.DictReader(open(path)):
        try:
            g[row["candidate_id"].strip()] = int(float(row["gold_tier"]))
        except (ValueError, KeyError):
            pass
    return g


def relevant_skills(c):
    """List JD-relevant skills with what backs each (assessment / endorsements / tenure)."""
    assess = (c.get("redrob_signals", {}) or {}).get("skill_assessment_scores", {}) or {}
    out = []
    for s in c.get("skills", []) or []:
        name = s.get("name") or ""
        if any(t in name.lower() for t in RELEVANT):
            tag = []
            if s.get("name") in assess:
                tag.append(f"assessed={assess[s['name']]}")
            if (s.get("endorsements") or 0) >= 10:
                tag.append(f"end={s['endorsements']}")
            if (s.get("duration_months") or 0) >= 24:
                tag.append(f"dur={s['duration_months']}mo")
            out.append(name + (f" [{', '.join(tag)}]" if tag else " [unbacked]"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--coherence", default="coherence.jsonl")
    ap.add_argument("--gold", default="gold.csv")
    ap.add_argument("--ids", nargs="*", default=DEFAULT_IDS)
    args = ap.parse_args()

    survivors, incoherent, _ = load_survivors(args.contested, args.coherence)
    gold = load_gold(args.gold)
    order = [r["candidate_id"] for _, r in rank(survivors, incoherent)]
    rank_of = {c: i + 1 for i, c in enumerate(order)}
    by_id = {r["candidate_id"]: r for r in survivors}

    print("JD must-haves: embeddings / vector-DB / hybrid-retrieval in production + "
          "learning-to-rank; 5-9 yrs (6-8 ideal); India (Pune/Noida, no visa sponsorship).")
    print("Scoring: base = .40*depth + .35*yoe_fit + .10*loc + .00*prior ; "
          "final = base * availability * (coherent? 1 : .50)\n")

    for cid in args.ids:
        r = by_id.get(cid)
        if not r:
            print(f"===== {cid}: not in survivor set (gate-dropped or absent) =====\n")
            continue
        c = r["candidate"]
        p = c.get("profile", {}) or {}
        sig = c.get("redrob_signals", {}) or {}
        s = score(r, incoherent)
        breadth = min(1.0, n_backed_relevant(c) / 4.0)
        github = max(0.0, min(1.0, (sig.get("github_activity_score") or 0) / 100.0))
        wd, wy, wl = W["depth"] * s["depth"], W["yoe"] * s["yf"], W["loc"] * s["loc"]
        base = wd + wy + wl

        print(f"===== {cid}  |  GOLD tier {gold.get(cid, '?')}  |  shipped #{rank_of.get(cid, '?')}"
              f"  |  final {s['final']:.3f} =====")
        print(f"  {p.get('current_title', '?')}  |  {p.get('years_of_experience', '?')} yrs"
              f"  |  {p.get('country', '?')}  |  employer: {p.get('current_company', '?')}")
        asx = "-" if s["asx"] is None else int(s["asx"])
        print(f"  DEPTH {s['depth']:.3f} = 0.5*asx({asx}/100) + "
              f"0.5*[0.6*breadth({breadth:.2f}) + 0.4*github({github:.2f})]")
        print(f"    JD-relevant skills: {', '.join(relevant_skills(c)) or '(none matched)'}")
        print(f"  YOE_FIT {s['yf']:.2f}  |  LOC {s['loc']:.2f}  |  "
              f"AVAIL {s['amult']:.3f}  |  COH {'ok' if s['coh'] else 'FLAGGED x0.50'}")
        print(f"    avail inputs: last_active={sig.get('last_active_date')}  "
              f"response_rate={sig.get('recruiter_response_rate')}  "
              f"open_to_work={sig.get('open_to_work_flag')}")
        print(f"  = depth {wd:.3f} + yoe {wy:.3f} + loc {wl:.3f} = base {base:.3f}"
              f"  ->  x avail {s['amult']:.3f}"
              f"{'  x coh 0.50' if not s['coh'] else ''}  =  final {s['final']:.3f}\n")


if __name__ == "__main__":
    main()