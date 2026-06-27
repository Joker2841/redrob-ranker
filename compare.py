"""
compare.py — lay the DISCRIMINATING structured signals side-by-side for the top
candidates, so the human gold-audit compares what actually differs (years, company
type, assessment-backed depth, availability, consistency) instead of re-reading
near-identical templated essays.

Usage:
  python compare.py --contested contested_set.json --labels labels.jsonl --top 40
"""

import argparse
import json
from datetime import date

from ranker.consistency import analyze, parse_date

CONSULTING = {"tcs", "tata consultancy", "infosys", "wipro", "accenture", "cognizant",
              "capgemini", "hcl", "tech mahindra", "mindtree", "ltimindtree", "lti",
              "dxc", "mphasis", "hexaware", "birlasoft", "zensar", "igate", "syntel"}
# JD-relevant skills whose assessment score signals real depth
RELEVANT = ("information retrieval", "retrieval", "ranking", "learning to rank",
            "embeddings", "vector", "semantic", "recommendation", "search",
            "faiss", "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch",
            "sentence transformers", "ndcg")


def is_consulting(name):
    n = (name or "").lower()
    return any(k in n for k in CONSULTING)


def best_relevant_assessment(c):
    assess = (c.get("redrob_signals", {}) or {}).get("skill_assessment_scores", {}) or {}
    rel = [v for k, v in assess.items()
           if any(t in (k or "").lower() for t in RELEVANT)]
    return max(rel) if rel else None


def months_since(d, today):
    dt = parse_date(d)
    return ((today.year - dt.year) * 12 + (today.month - dt.month)) if dt else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contested", default="contested_set.json")
    ap.add_argument("--labels", default=None)
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    recs = json.load(open(args.contested))
    recs.sort(key=lambda r: r.get("first_pass_score", 0), reverse=True)
    llm = {}
    if args.labels:
        llm = {l["candidate_id"]: l for l in (json.loads(x) for x in open(args.labels) if x.strip())}
    today = date(2026, 5, 27)

    print(f"{'fps':>5} {'llmT':>4} {'id':12} {'yoe':>4} {'IN':>2} "
          f"{'roles(P/C)':>10} {'asx':>3} {'act_mo':>6} {'resp':>4} {'OTW':>3} flags")
    print("-" * 104)
    for r in recs[:args.top]:
        c = r["candidate"]
        p = c.get("profile", {}) or {}
        sig = c.get("redrob_signals", {}) or {}
        a = analyze(c, today)
        roles = c.get("career_history", []) or []
        nc = sum(1 for h in roles if is_consulting(h.get("company")))
        np_ = len(roles) - nc
        asx = best_relevant_assessment(c)
        act = months_since(sig.get("last_active_date"), today)
        flags = []
        if a["hard"]:
            flags.append("HONEYPOT")
        if a["n_anachronism"] == 1:
            flags.append("1anach:" + a["anach_tools"][0])
        if nc and np_ == 0:
            flags.append("consult-only")
        india = "Y" if (p.get("country") == "India") else ""
        lt = llm.get(c["candidate_id"], {}).get("tier", "")
        print(f"{r.get('first_pass_score',0):5.1f} {str(lt):>4} {c['candidate_id']:12} "
              f"{p.get('years_of_experience',0):>4.1f} {india:>2} {f'{np_}/{nc}':>10} "
              f"{('' if asx is None else int(asx)):>3} {('' if act is None else act):>6} "
              f"{sig.get('recruiter_response_rate','?'):>4} "
              f"{'Y' if sig.get('open_to_work_flag') else 'n':>3} {', '.join(flags)}")


if __name__ == "__main__":
    main()