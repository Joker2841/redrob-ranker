"""
coherence_check.py — re-tasked LLM audit. NOT "score 0-5" (the LLM failed at
keyword-tiering). Instead: "is this profile internally coherent — does the
described work match where they claim to have done it?" This catches the subtle
semantic honeypots that structural rules miss (e.g. an e-commerce search product
built at a payments company; 50M recruiter queries at a fintech).

Run it on the SURVIVORS (profiles that already passed the structural honeypot
gate). Survivors that are also COHERENT are our real tier-5 candidates.

Usage:
  python coherence_check.py --in contested_set.json --out coherence.jsonl \
      --model qwen2.5:7b-instruct --limit 500
"""

import argparse
import json
import os
import sys
from datetime import date

from ranker.consistency import analyze
from label import condense, ask_ollama   # reuse the condenser + Ollama call

PROMPT = """You are auditing ONE candidate profile for INTERNAL COHERENCE. The data
is synthetic and some profiles are deliberately incoherent traps. Judge ONLY
plausibility/consistency, NOT how impressive the candidate is.

Check every role:
- Does the described work match the COMPANY and its INDUSTRY? Examples of INCOHERENT:
  "built an e-commerce search product" at a payments/fintech company; "candidate-JD
  matching for recruiters" at a computer-vision or language-model company; a consumer
  app feature at a pure B2B infrastructure firm.
- Is the claimed SCALE plausible for that company/product? (e.g. "50M queries/month
  for an INTERNAL recruiter tool" is not.)
- Do named tools/models fit the dates? (using GPT-4 before 2023, BGE before late 2023.)
- Any other logical contradiction (impossible timelines, mismatched domains).

If every role is plausible and consistent, answer coherent=true.

Return ONLY JSON:
{"coherent": true or false, "contradiction": "<single clearest contradiction, or 'none'>"}"""


def build(c):
    return PROMPT + "\n\nCANDIDATE:\n" + condense(c) + "\n\nJSON:"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="contested_set.json")
    ap.add_argument("--out", default="coherence.jsonl")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--resume", action="store_true",
                    help="resume from an existing output file by skipping already-checked candidates")
    args = ap.parse_args()

    recs = json.load(open(args.inp))
    recs.sort(key=lambda r: r.get("first_pass_score", 0), reverse=True)
    dd = date(2026, 5, 27)

    done = skipped = incoherent = errs = 0
    seen = set()
    mode = "a" if args.resume else "w"

    if args.resume and os.path.exists(args.out):
        with open(args.out) as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get("candidate_id"))
                except Exception:
                    continue
    elif os.path.exists(args.out):
        print(f"Output file {args.out} exists and --resume not specified; overwriting.", file=sys.stderr)

    with open(args.out, mode) as f:
        for rec in recs[:args.limit]:
            c = rec["candidate"]
            candidate_id = c["candidate_id"]
            if candidate_id in seen:
                continue
            if analyze(c, dd)["hard"]:        # already a structural honeypot -> skip
                skipped += 1
                continue
            try:
                j = json.loads(ask_ollama(args.model, build(c)))
                coherent = bool(j.get("coherent", True))
                out = {"candidate_id": candidate_id, "coherent": coherent,
                       "contradiction": j.get("contradiction", ""),
                       "first_pass_score": rec.get("first_pass_score")}
                if not coherent:
                    incoherent += 1
            except Exception as e:
                out = {"candidate_id": candidate_id, "coherent": None,
                       "error": str(e)[:120], "first_pass_score": rec.get("first_pass_score")}
                errs += 1
            f.write(json.dumps(out) + "\n")
            f.flush()
            done += 1
            if done % 25 == 0:
                print(f"  checked {done} ({incoherent} incoherent, {errs} err)", file=sys.stderr)
    print(f"checked {done} survivors -> {args.out} | incoherent={incoherent} "
          f"skipped_honeypots={skipped} errors={errs}")


if __name__ == "__main__":
    main()