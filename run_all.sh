#!/usr/bin/env bash
# Full from-scratch reproduction of the submission.
#
# Prerequisites:
#   - data/candidates.jsonl          the provided 100K dataset
#   - gold.csv                       hand-labelled evaluation set (committed)
#   - Ollama running locally with qwen2.5:7b-instruct  (only for the coherence step)
#
# Note: steps 1-3 are OFFLINE PRECOMPUTE (LLM, unconstrained). Only step 4 is the
# graded "ranking step" and it is CPU-only, no network, < 5 min over 100K.
# If coherence.jsonl is already committed, you can skip to step 4 directly.
set -e

echo "[1/5] first-pass recall -> contested set"
python run_firstpass.py --path data/candidates.jsonl --out contested_set.json --dump 500

echo "[2/5] coherence precompute over contested survivors (offline LLM)"
python coherence_check.py --in contested_set.json --out coherence.jsonl --limit 500

echo "[3/5] preliminary full-pool rank -> top-300 for coherence coverage of plain-language fits"
python rank.py --data data/candidates.jsonl --coherence coherence.jsonl --gold gold.csv \
    --out prelim.csv --prelim-out prelim_set.json --prelim-n 300
python coherence_check.py --in prelim_set.json --out coherence.jsonl --limit 300

echo "[4/5] FINAL ranking (CPU-only, < 5 min) -> submission.csv"
python rank.py --data data/candidates.jsonl --coherence coherence.jsonl --gold gold.csv --out submission.csv

echo "[5/5] validate"
python validate_submission.py submission.csv
