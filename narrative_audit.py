"""
narrative_audit.py — measure the narrative contradiction signals across the pool
(clean signal vs pervasive noise) and surface the SURVIVORS: candidates that pass
every check we have. Survivors are our real tier-5 candidates — or their absence
tells us the real fits aren't keyword-dense and our first-pass is surfacing traps.

Usage:
  python narrative_audit.py --path candidates.jsonl --top 500
"""

import argparse
from datetime import date

from ranker.load import load_candidates
from ranker.consistency import analyze, narrative_flags, parse_date
from ranker.firstpass import first_pass_score
from compare import best_relevant_assessment


def data_reference_date(cands):
    mx = None
    for c in cands:
        d = parse_date((c.get("redrob_signals", {}) or {}).get("last_active_date", ""))
        if d and (mx is None or d > mx):
            mx = d
    return mx or date(2026, 6, 1)


def rates(rows, label):
    n = len(rows)
    honey = sum(1 for r in rows if r["honey"])
    narr = sum(1 for r in rows if r["nf"]["narr_anachronism"])
    dup = sum(1 for r in rows if r["nf"]["self_dup"])
    dom = sum(1 for r in rows if r["nf"]["domain_mismatch"])
    surv = sum(1 for r in rows if r["survivor"])
    p = lambda x: f"{x} ({100*x/max(1,n):.1f}%)"
    print(f"\n===== {label}  (n={n}) =====")
    print(f"  honeypot (existing gate) : {p(honey)}")
    print(f"  narrative anachronism    : {p(narr)}   <- clean if low")
    print(f"  self-duplication         : {p(dup)}")
    print(f"  domain mismatch (e-comm) : {p(dom)}   <- noise if very high")
    print(f"  SURVIVORS (pass all)     : {p(surv)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="/mnt/project/sample_candidates.json")
    ap.add_argument("--top", type=int, default=500)
    args = ap.parse_args()

    cands = load_candidates(args.path)
    dd = data_reference_date(cands)
    rows = []
    for c in cands:
        nf = narrative_flags(c, dd)
        honey = analyze(c, dd)["hard"]   # now includes narr-anach + domain mismatch
        rows.append({"id": c["candidate_id"], "fps": first_pass_score(c)[0],
                     "c": c, "nf": nf, "honey": honey,
                     "survivor": not honey})   # self-dup is noise -> ignored

    rates(rows, "WHOLE POOL")
    top = sorted(rows, key=lambda r: r["fps"], reverse=True)[:args.top]
    rates(top, f"TOP {args.top}")

    print(f"\n===== TOP 45 detail (H=honeypot N=narr-anach D=dup M=domain) =====")
    for r in top[:45]:
        p = r["c"].get("profile", {})
        marks = "".join([("H" if r["honey"] else "."),
                         ("N" if r["nf"]["narr_anachronism"] else "."),
                         ("D" if r["nf"]["self_dup"] else "."),
                         ("M" if r["nf"]["domain_mismatch"] else ".")])
        tag = "  <-- SURVIVOR" if r["survivor"] else ""
        print(f"  {r['fps']:5.1f} [{marks}] {r['id']:12} "
              f"{(p.get('current_title','') or '')[:26]:26} {p.get('country','')}{tag}")

    survivors = [r for r in top if r["survivor"]]
    print(f"\n===== SURVIVORS in top {args.top}: {len(survivors)} (our real tier-5 candidates) =====")
    for r in sorted(survivors, key=lambda r: r["fps"], reverse=True)[:30]:
        p = r["c"].get("profile", {})
        asx = best_relevant_assessment(r["c"])
        print(f"  {r['fps']:5.1f} {r['id']:12} yoe={p.get('years_of_experience',0):>4} "
              f"{'IN' if p.get('country')=='India' else '  '} asx={'' if asx is None else int(asx):>3} "
              f"{(p.get('current_title','') or '')[:30]}")


if __name__ == "__main__":
    main()