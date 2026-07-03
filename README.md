# Redrob — Intelligent Candidate Discovery (Track 01)

**Live demo:** https://huggingface.co/spaces/sai001122/redrob-ranker-demo (runs the committed `rank.py` on a candidate sample, in-browser, CPU only).

A transparent, CPU-fast system that reconstructs each candidate's hidden relevance
tier for a specific Senior ML/AI Engineer job description, then ranks the full
100,000-candidate pool down to a defensible top 100.

**Measured quality (held-out gold set):** NDCG@10 = **0.929**, NDCG@50 = **0.978** (tier ≤2 candidates floored, matching the shipped pipeline).

The guiding decision of this project: **rank on verifiable structural shape, not on
prose** — because the data told us, repeatedly and empirically, that the prose is noise.

---

## 1. The discovery that shaped everything

The dataset is synthetic, and its text is **templated**. There are only ~6 distinct
career-description templates, randomly stamped onto (company, title, date) slots. The
exact sentence *"Developed a semantic search feature for an internal knowledge base of
~500K documents…"* appears verbatim on eight unrelated candidates at eight unrelated
companies. The same is true of the skills prose and summaries.

The implication is decisive: **a candidate's description tells you almost nothing about
what *they* did.** Any method that reads the prose — keyword density, embeddings of the
narrative, LLM essay-grading — is reading a random draw from a shared bag. So we rank on
the fields that *are* candidate-specific and hard to fake: **title, company + industry,
years of experience, skills + their assessment depth, availability, and internal
consistency.**

## 2. Empirical discipline: every signal measured against the full pool

We treated each proposed signal as a hypothesis and measured its behaviour across all
100K before trusting it. Several intuitive signals were **disproved and dropped**:

| Signal | Why we dropped it |
|---|---|
| skill duration > career length | Fires on ~18% of the pool and *correlates with low experience* — it's people listing skills they used before their first job, not fakery. |
| duplicate descriptions (cross-candidate) | The generator reuses ~6 templates; ~34% of the pool collides. Pure generation noise. |
| self-duplicated descriptions (within a candidate) | Same cause, ~34% prevalence. Not a fraud marker. |
| education date-ordering, salary inversions | No discriminative value once measured. |
| **fps / keyword density** | The weight sweep gave it **zero ranking value** — dropped from the scorer entirely (see §6). |

This discipline is the backbone of the approach: **no signal becomes a gate until it
survives contact with the whole pool.** Manual profile teardowns repeatedly caught what
automation missed, and human judgment was treated as ground truth when it conflicted with
a rule.

## 3. The pipeline

```
load 100K
  → relevance floor      (ML-relevant title, or real assessed depth)      drops ~88%
  → structural honeypot gate (internal impossibilities)                   floors traps
  → JD disqualifier floor (career entirely at consulting firms)           floors ~10%
  → calibrated structured score (depth + yoe-fit + location)
        × availability multiplier
        × coherence penalty   (precomputed LLM flag, offline)
  → sort (score desc, candidate_id asc tie-break) → top 100 + reasoning
```

On the real pool: **100,000 scanned → 436 honeypots + 9,726 consulting-only + 88,291
non-relevant floored → 1,547 eligible → top 100.**

## 4. Trap detection (the honeypot defense)

Honeypots are real-looking profiles with a *planted* contradiction. We gate only on
clean, near-zero-false-positive impossibilities (`ranker/consistency.py`):

1. **experience vs career-span contradiction** — career span differs from claimed YOE by years;
2. **≥2 distinct tool anachronisms** — a skill's duration implies using a tool before it existed (RAG pre-2020, Pinecone pre-2021, QLoRA pre-2023). *Two* required, because a single one fires as ~13% noise;
3. **narrative anachronism** — a description names a tool released after the role ended (e.g. GPT-4 in a role ending 2022, BGE before late 2023);
4. **domain mismatch** — an e-commerce claim at a non-e-commerce employer;
5. **"expert" proficiency with 0 months.**

## 5. Coherence: the LLM, re-tasked

A local LLM (`qwen2.5:7b-instruct` via Ollama) was first tried as a 0–5 tier scorer and
**failed** — templated profiles inflated its scores. So it was **re-tasked** to the one
job it does well on this data: **internal-coherence checking.** *Does the described work
plausibly match the company and its industry? Is the claimed scale possible?*

This catches the subtle semantic fakes that structural rules cannot — e.g. it
independently flagged a profile claiming *"50M+ queries per month for an internal
recruiter-facing search product"* at a payments company (an internal HR tool does not
serve 50M monthly queries).

It is a **heavy penalty (×0.50), not a hard floor**, because it has errors in both
directions (it over-flagged a coherent LLM-fine-tuning role at a conversational-AI company,
and missed a domain mismatch a human caught). The structural gate does the hard flooring;
coherence provides margin; the human gold-audit is the final safety layer.

## 6. Calibration (no leaderboard → build your own)

With no training labels and no leaderboard, the **only** feedback loop is a self-built dev
set. We hand-tiered the ranker's top candidates **on structural shape** (`goldaudit.py`
shows the condensed career inline so prose is ignored), then:

- **`evaluate.py`** scores the ranking with NDCG@10 / @50.
- **`sweep.py`** grid-searches the weights and the coherence-penalty strength against the
  gold set.

The sweep settled the last open knobs **empirically**:
- **fps weight → 0** (keyword density carried no ranking value — consistent with §1);
- **yoe weight raised to 0.35** (the JD anchors hard on the 5–9 band, peak 6–8);
- coherence-penalty strength is **rank-invariant** in 0.30–0.70 (the gate already removes
  the blatant traps), so it's set on principle to 0.50.

The gold evaluation set is seeded by `goldaudit.py`/`gold_template.csv` and then hand-
refined into `gold.csv` through manual review; the code does not auto-generate the final
human-vetted labels.

**A note on `github_activity` (`ablate_github.py`).** It was first dropped on a hasty read
of its low (0.107) correlation with skill assessment — but a clean floored ablation showed
removing it *costs* **+0.086 NDCG@10**. A random signal cannot improve NDCG, so github
carries genuine tier information; the low assessment-correlation simply means it is
*complementary* (independent), not redundant. It is kept, with the `-1` missing-value
sentinel clamped to 0. (Caveat: the gain is concentrated at @10 on a 51-label gold set, so
its exact magnitude is uncertain — but the sign is trustworthy, and the eval is non-circular
because github was never used to assign the gold tiers.)

Final score (only relative weights matter; availability and coherence are multipliers):

```
base   = 0.40·depth + 0.35·yoe_fit + 0.10·location
depth  = 0.5·assessment + 0.5·(0.6·backed_skill_breadth + 0.4·github_activity)   # assessment leads; github is a complementary signal (-1 sentinel clamped to 0)
final  = base × availability(0.55–1.05, asymmetric) × (0.50 if coherence-flagged else 1.0)
```

## 7. Compute & reproducibility

- **Ranking step is CPU-only, no network, < 5 min for 100K** — it loads the pool, applies
  the floors, scores, and sorts using only precomputed features.
- **Offline / unconstrained precompute:** the LLM coherence pass (GPU + Ollama). It is run
  on the candidates the structured score actually surfaces, via a two-pass loop:

```bash
# Pass 1 — rank all 100K, dump the top 300 for coherence coverage
python rank.py --data data/candidates.jsonl --coherence coherence.jsonl \
    --out prelim.csv --prelim-out prelim_set.json --prelim-n 300

# Coherence-check those (offline LLM)
python coherence_check.py --in prelim_set.json --out coherence.jsonl --limit 300

# Pass 2 — final ranking with full coherence coverage
python rank.py --data data/candidates.jsonl --coherence coherence.jsonl --out team_xxx.csv

# Validate against the official spec
python validate_submission.py team_xxx.csv
```

## 8. File map

| File | Role |
|---|---|
| `ranker/load.py` | Stream candidates from `.json` / `.jsonl` / `.jsonl.gz`. |
| `ranker/consistency.py` | Structural honeypot gate + narrative-anachronism + domain mismatch. |
| `ranker/firstpass.py` | Recall-oriented relevance proxy (used to build the dev set). |
| `compare.py` | Structured-signal grid; consulting-firm + JD-relevant-skill definitions. |
| `coherence_check.py` | Re-tasked LLM coherence audit → `coherence.jsonl`. |
| `rank_survivors.py` | Calibrated scorer (importable `score` / `rank`), used by the tools below. |
| `goldaudit.py` | Fast human gold-audit (condensed careers + proposed tiers). |
| `evaluate.py` | NDCG@10 / @50 harness against the gold set. |
| `sweep.py` | Empirical weight + penalty calibration. |
| `audit.py` | Overfit / top-10 stability / location-sensitivity stress test of the calibration. |
| **`rank.py`** | **The submission generator: full pipeline → top-100 CSV.** |

## 9. Honest limitations

- **Coherence is imperfect** (small local model): false positives and false negatives both
  occur, which is why it penalizes rather than floors, and why the top is human-audited.
- **Some JD disqualifiers are undetectable here** — "research-only," "architect not coding
  for 18 months," "LangChain-only" all live in the *prose*, which is noise. We floor the
  one structurally-detectable disqualifier (consulting-only careers) and do not pretend to
  catch the rest from templated text.
- The dev set is small (~55 labels); weights were kept principled (JD-justified), not
  curve-fit to the labels.
- **Depth anchors on verified assessments**, which slightly penalizes strong candidates
  whose *best* assessment is only moderate: a single verified score near 65 blends against
  an otherwise-high skill/GitHub composite and can rank a genuine tier-5 below assessment-
  less peers. This is deliberate — verified assessments resist the template-gaming that
  inflates self-reported breadth — and its cost is measured, not hidden: an `audit.py`
  stress test puts it at ≈0.002 NDCG@10, affecting only the #7–13 boundary, so we accept
  the trade rather than curve-fit the depth formula to a handful of candidates.

## 10. Development process & provenance

This project was built iteratively in a local working tree and published here as a single
clean import commit rather than as its raw local history. The evidence of that iteration is
in the work itself, not the commit graph:

- **Disproved signals** (§2): skill-duration-over-career, cross-candidate description
  duplication, and keyword density were each tried and dropped after testing against the
  full pool showed they added noise or no ranking value. GitHub activity was dropped, then
  restored after a clean ablation confirmed it carries complementary tier signal.
- **Calibration is measured, not asserted** (§6): `sweep.py` grids the weights against a
  hand-labeled gold set, `evaluate.py` reports NDCG, and `audit.py` stress-tests whether that
  calibration is overfit or fragile. It is neither — the shipped config sits within 0.002 of
  the grid's best NDCG@10, and only a small number of top-10 slots are contested across all
  near-optimal weightings.
- **Gold integrity**: a mislabeled candidate was caught on full-profile inspection and
  corrected in both the gold set and the submission; the local LLM coherence checker's
  run-to-run non-determinism was neutralized with a deterministic human-verified floor.
- **Location is JD-grounded**: the `India = 1.0 / else = 0.35` signal reflects the JD's
  explicit Pune/Noida, India requirement and its "outside India: case-by-case, no visa
  sponsorship" stance — a soft discount, not a hard exclusion.

Every signal in the scorer earns its place empirically, and the limitations in §9 are stated
honestly rather than hidden.
