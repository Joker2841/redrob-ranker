"""
diagnostic.py — count precise honeypot signals + test whether skill durations
respect tool-age reality (the decisive test for tool_anachronism reliability).
"""

import argparse
import statistics
from collections import Counter, defaultdict
from datetime import date

from ranker.load import load_candidates
from ranker.consistency import analyze, parse_date, TOOL_ERA
from ranker.firstpass import first_pass_score


def pct(xs, ps):
    if not xs:
        return {p: 0 for p in ps}
    s = sorted(xs)
    return {p: s[min(len(s) - 1, int(p / 100 * len(s)))] for p in ps}


def hard_category(r):
    if "career spans" in r or "claims" in r: return "exp_contradiction"
    if "anachronistic" in r: return "tool_anachronism"
    if "0 months" in r: return "expert_0mo"
    if "future" in r: return "future_start"
    if "ends before" in r: return "role_end<start"
    return "other"


def data_reference_date(cands):
    mx = None
    for c in cands:
        d = parse_date((c.get("redrob_signals", {}) or {}).get("last_active_date", ""))
        if d and (mx is None or d > mx):
            mx = d
    return mx or date(2026, 6, 1)


def report(rows, label):
    n = len(rows)
    hard = [r for r in rows if r["a"]["hard"]]
    cats = Counter(hard_category(x) for r in hard for x in r["a"]["hard_reasons"])
    print(f"\n===== {label}  (n={n}) =====")
    print(f"  HONEYPOTS: {len(hard)} ({100*len(hard)/max(1,n):.2f}%)  "
          f"| by signal: {dict(cats)}")


def tool_reality_check(cands, data_year):
    durs = defaultdict(list)
    for c in cands:
        for s in c.get("skills", []) or []:
            name = (s.get("name") or "").lower().strip()
            dm = s.get("duration_months")
            if name in TOOL_ERA and dm is not None:
                durs[name].append(dm)
    print("\n===== TOOL DURATION REALITY CHECK =====")
    print("  If a high %% of listers exceed the tool's age, durations are NOISE")
    print("  and single-tool anachronism is unreliable.\n")
    print(f"  {'tool':16} {'era':>4} {'age_mo':>6} {'listers':>7} {'med':>4} {'max':>4} "
          f"{'>age':>5} {'>flag':>6}")
    for tool in ["qlora", "langchain", "rag", "peft", "prompt engineering",
                 "pinecone", "weaviate", "qdrant"]:
        xs = durs.get(tool, [])
        if not xs:
            continue
        age = (data_year - TOOL_ERA[tool]) * 12
        over = 100 * sum(1 for x in xs if x > age) / len(xs)
        flag = 100 * sum(1 for x in xs if x > age + 12) / len(xs)
        print(f"  {tool:16} {TOOL_ERA[tool]:>4} {age:>6.0f} {len(xs):>7} "
              f"{int(statistics.median(xs)):>4} {max(xs):>4} {over:>4.0f}% {flag:>5.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="/mnt/project/sample_candidates.json")
    ap.add_argument("--top", type=int, default=500)
    args = ap.parse_args()

    cands = load_candidates(args.path)
    dd = data_reference_date(cands)
    data_year = dd.year + (dd.month - 1) / 12.0
    rows = [{"id": c["candidate_id"], "fps": first_pass_score(c)[0],
             "a": analyze(c, dd)} for c in cands]

    report(rows, "WHOLE POOL")
    top = sorted(rows, key=lambda r: r["fps"], reverse=True)[:args.top]
    report(top, f"TOP {args.top}")

    # composition of anachronism flags in the top set
    anach = [r for r in top if any("used since" in x for x in r["a"]["hard_reasons"])]
    one = sum(1 for r in anach if sum("used since" in x for x in r["a"]["hard_reasons"]) == 1)
    co = sum(1 for r in anach
             if any(("career spans" in x or "claims" in x) for x in r["a"]["hard_reasons"]))
    print(f"\n  anachronism-flagged in top {args.top}: {len(anach)} "
          f"| exactly 1 bad tool: {one} | 2+ bad tools: {len(anach)-one} "
          f"| ALSO exp_contradiction: {co}")

    tool_reality_check(cands, data_year)


if __name__ == "__main__":
    main()