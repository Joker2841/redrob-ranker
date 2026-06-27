"""
label.py — produce INDEPENDENT dev-set tier labels with a local Ollama model.

Why independent: we tune our scorer against these labels, so they must come from a
different judgment (an LLM reading raw profiles under our rubric), NOT from our own
scoring code — otherwise tuning is circular and measures nothing.

Pipeline: contested set -> drop honeypots (recomputed fresh) -> condense each
profile -> ask the local model for tier(0-5)+evidence+concerns -> save jsonl.

Usage:
  ollama pull qwen2.5:7b-instruct
  python label.py --in contested_set.json --out labels.jsonl \
      --model qwen2.5:7b-instruct --limit 500
"""

import argparse
import json
import sys
import urllib.request
from datetime import date

from ranker.consistency import analyze

OLLAMA_URL = "http://localhost:11434/api/chat"

RUBRIC = """You are an expert technical recruiter scoring candidates for ONE specific role.

ROLE: Senior ML/AI Engineer who builds PRODUCTION ranking, search, recommendation,
and retrieval systems at a PRODUCT company (not a services/consulting firm).

HOW TO JUDGE (priority order):
1. CAREER HISTORY is the truth — what did they actually BUILD and SHIP? The decisive
   signal is shipping an end-to-end ranking / search / recommendation / retrieval
   system to real users at a product company.
2. SKILLS LISTS are gameable — trust a skill only if the career text or an assessment
   score backs it. Ignore long keyword lists with no supporting work.
3. Read PLAIN LANGUAGE — a real fit may describe building a recommender without ever
   saying "RAG" or "vector search". Reward the work, not the buzzwords.

STRONG POSITIVES: production embeddings/retrieval, vector DBs, ranking evaluation
(NDCG/MRR/MAP, A/B tests), pre-LLM ML depth, 5-9 yrs (best 6-8), India-based or
willing to relocate, currently active.

DISQUALIFIERS (cap tier low): pure research with no production; CV/speech/robotics
with no NLP/IR; career ENTIRELY at consulting firms (TCS/Infosys/Wipro/Accenture/
Cognizant/Capgemini) with no product work; "AI" that is only recent LangChain-calls-
OpenAI with no prior ML; senior who hasn't coded in 18 months.

TIERS:
5 = ideal: shipped ranking/search/rec at a product company + retrieval/eval depth, right seniority, available.
4 = strong fit, shipped relevant systems, missing one ideal element.
3 = relevant/adjacent: real ML/NLP or data->ML engineer, but no clear ranking/retrieval shipping story.
2 = some relevant tech but fundamental mismatch (CV/speech-only, research-only, consulting-only, LangChain-only).
1 = not an AI/ML role at all.
0 = keyword-stuffer: AI-sounding words but no real AI substance.

Return ONLY JSON:
{"tier": <0-5>, "decisive_evidence": "<one phrase>", "concerns": "<one phrase>", "disqualifier": "<name or none>"}"""


def condense(c):
    p = c.get("profile", {}) or {}
    out = [f"TITLE: {p.get('current_title')} | YOE: {p.get('years_of_experience')} "
           f"| LOCATION: {p.get('location')}, {p.get('country')}",
           "SUMMARY: " + (p.get("summary", "") or "")[:500], "CAREER:"]
    for h in (c.get("career_history", []) or [])[:5]:
        out.append(f"- {h.get('title')} @ {h.get('company')} "
                   f"({h.get('industry')}, {h.get('company_size')}), "
                   f"{h.get('duration_months')}mo: {(h.get('description') or '')[:240]}")
    assess = (c.get("redrob_signals", {}) or {}).get("skill_assessment_scores", {}) or {}
    sk = []
    for s in (c.get("skills", []) or [])[:25]:
        a = assess.get(s.get("name"))
        tag = f"assess={a}" if a is not None else f"end={s.get('endorsements')},{s.get('duration_months')}mo"
        sk.append(f"{s.get('name')}({(s.get('proficiency') or '?')[:3]},{tag})")
    out.append("SKILLS: " + ", ".join(sk))
    sig = c.get("redrob_signals", {}) or {}
    out.append(f"AVAILABILITY: last_active={sig.get('last_active_date')}, "
               f"resp_rate={sig.get('recruiter_response_rate')}, "
               f"open_to_work={sig.get('open_to_work_flag')}")
    return "\n".join(out)


def build_prompt(c):
    return RUBRIC + "\n\nCANDIDATE:\n" + condense(c) + "\n\nJSON:"


def ask_ollama(model, prompt):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "stream": False, "format": "json", "options": {"temperature": 0}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="contested_set.json")
    ap.add_argument("--out", default="labels.jsonl")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--start", type=int, default=0, help="Skip first N records")
    args = ap.parse_args()

    data = json.load(open(args.inp))
    data.sort(key=lambda r: r.get("first_pass_score", 0), reverse=True)
    dd = date(2026, 5, 27)
    
    # Determine if appending or starting fresh
    mode = "a" if args.start > 0 else "w"

    done = errs = 0
    with open(args.out, mode) as f:
        for rec in data[args.start:args.start+args.limit]:
            c = rec["candidate"]
            if analyze(c, dd)["hard"]:
                label = {"candidate_id": c["candidate_id"], "tier": 0, "source": "honeypot"}
            else:
                try:
                    response = ask_ollama(args.model, build_prompt(c))
                    j = json.loads(response)
                    label = {"candidate_id": c["candidate_id"], "tier": int(j.get("tier", 1)),
                             "source": "llm", "decisive_evidence": j.get("decisive_evidence", ""),
                             "concerns": j.get("concerns", ""),
                             "disqualifier": j.get("disqualifier", "none")}
                except json.JSONDecodeError as e:
                    if errs < 3:  # Print first 3 errors
                        print(f"DEBUG: JSON decode error: {e}", file=sys.stderr)
                        print(f"DEBUG: Response was: {response[:200]}", file=sys.stderr)
                    label = {"candidate_id": c["candidate_id"], "tier": None,
                             "source": "error", "error": str(e)[:120]}
                    errs += 1
                except Exception as e:
                    if errs < 3:
                        print(f"DEBUG: Error: {type(e).__name__}: {e}", file=sys.stderr)
                    label = {"candidate_id": c["candidate_id"], "tier": None,
                             "source": "error", "error": str(e)[:120]}
                    errs += 1
            label["first_pass_score"] = rec.get("first_pass_score")
            f.write(json.dumps(label) + "\n")
            f.flush()
            done += 1
            if done % 25 == 0:
                print(f"  labeled {done}... ({errs} errors)", file=sys.stderr)
    print(f"wrote {done} labels -> {args.out}  ({errs} errors)")


if __name__ == "__main__":
    main()