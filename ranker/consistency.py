"""
consistency.py — precise honeypot detection.

The honeypot signature in this dataset is an INTERNAL CONTRADICTION between the
stated experience and the rest of the profile — not any single noisy field.
We gate only on clean, near-zero-false-positive impossibilities:

  1. experience vs career-span contradiction  (career spans years longer/shorter
     than years_of_experience claims)
  2. tool anachronism  (a skill used before the tool/term existed)
  3. role dates impossible (ends before starts / starts in the future)
  4. "expert" with 0 months

Confirmed NOISE we deliberately ignore: a single skill running longer than the
career (real juniors do this), education date-ordering, duplicate descriptions
(the generator reuses text across candidates).
"""

from collections import Counter
from datetime import date

# Year a tool/term became usable. Conservative; we add a 1-year grace buffer
# before flagging, so only clear anachronisms trip.
TOOL_ERA = {
    "rag": 2020, "langchain": 2022, "llamaindex": 2022, "llama-2": 2023,
    "llama2": 2023, "mistral": 2023, "qlora": 2023, "lora": 2021, "peft": 2022,
    "pinecone": 2021, "weaviate": 2019, "qdrant": 2021, "pgvector": 2021,
    "milvus": 2019, "bge": 2023, "haystack": 2020, "stable diffusion": 2022,
    "prompt engineering": 2021, "chatgpt": 2022, "gpt-4": 2023,
    "sentence transformers": 2019, "sbert": 2019, "instructor embeddings": 2023,
}


def parse_date(s):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def analyze(c, data_date):
    hard = []
    profile = c.get("profile", {}) or {}
    yoe = float(profile.get("years_of_experience") or 0)
    exp_months = yoe * 12.0
    career = c.get("career_history", []) or []
    skills = c.get("skills", []) or []
    data_year = data_date.year + (data_date.month - 1) / 12.0

    # ---- career span (use today for current roles) ----
    starts, ends = [], []
    sum_months = 0
    for h in career:
        sd, ed = parse_date(h.get("start_date")), parse_date(h.get("end_date"))
        sum_months += h.get("duration_months") or 0
        if sd:
            starts.append(sd)
            if sd > data_date:
                hard.append(f"role '{h.get('title')}' starts in the future ({sd})")
        end = ed if ed else (data_date if h.get("is_current") else None)
        if end:
            ends.append(end)
            if sd and end < sd:
                hard.append(f"role '{h.get('title')}' ends before it starts")
    span = _months(min(starts), max(ends)) if (starts and ends) else 0

    # (1) experience vs timeline contradiction
    if exp_months > 0 and span > 0:
        if span > exp_months + 24:
            hard.append(f"career spans {span/12:.1f}yr but yoe claims {yoe:.1f}yr")
        elif exp_months > span + 60:
            hard.append(f"claims {yoe:.1f}yr experience but career spans only {span/12:.1f}yr")

    # (2) tool anachronism — require >=2 distinct tools (a single recent tool like
    #     QLoRA trips ~13% of real fits on duration-noise; two tools predating their
    #     existence is essentially impossible by chance -> deliberate planting).
    anach = []
    for s in skills:
        name = (s.get("name") or "").lower().strip()
        era = TOOL_ERA.get(name)
        dm = s.get("duration_months")
        if era and dm:
            start_year = data_year - dm / 12.0
            if start_year < era - 1.0:
                anach.append((s.get("name"), int(start_year)))
    if len(anach) >= 2:
        hard.append("anachronistic skills (used before they existed): "
                    + ", ".join(f"{n}~{y}" for n, y in anach))

    # (4) expert with 0 months
    for s in skills:
        if (s.get("proficiency") or "").lower() == "expert" and s.get("duration_months") == 0:
            hard.append(f"'expert' {s.get('name')} with 0 months")

    # Fold in the CLEAN narrative contradictions — narrative anachronism (0.05%
    # of pool) and domain mismatch (0.3%) are surgically rare planted traps.
    # We deliberately EXCLUDE self-duplication: at ~34% of the pool it is
    # pervasive generation noise, not a deliberate honeypot marker.
    _nf = narrative_flags(c, data_date)
    hard.extend(_nf["narr_anachronism"])
    hard.extend(_nf["domain_mismatch"])

    # ---- measured signals (reported, not gated) ----
    skill_excess = [s.get("duration_months", 0) - exp_months for s in skills
                    if s.get("duration_months") is not None and exp_months > 0]
    return {
        "hard": len(hard) > 0,
        "hard_reasons": hard,
        "anach_tools": [n for n, _ in anach],
        "exp_vs_span_gap": round(span - exp_months, 1),
        "n_anachronism": len(anach),
        "max_skill_excess": round(max(skill_excess), 1) if skill_excess else 0,
        "n_skill_over": sum(1 for x in skill_excess if x > 0),
        "sum_excess": round(sum_months - exp_months, 1),
        "self_dup": _nf["self_dup"],  # reported only — NOT gated (pervasive noise)
    }


def check_consistency(c, data_date):
    a = analyze(c, data_date)
    return {"hard": a["hard"], "penalty": 0.0,
            "reasons": a["hard_reasons"], "n_hard": len(a["hard_reasons"]),
            "n_soft": 0, "signals": a}


# ---------------------------------------------------------------------------
# Narrative-level contradiction detectors (operate on career DESCRIPTIONS, not
# just the skills array). These target the honeypot signature the manual audit
# surfaced: descriptions assembled with temporal / logical impossibilities.
# Kept SEPARATE from analyze() until we've measured their pool-wide flag rate.
# ---------------------------------------------------------------------------

# Tools/models with confident first-availability years (for role-predates-tool).
NARRATIVE_ERA = {
    "gpt-4": 2023, "gpt-4o": 2024, "gpt-3.5": 2022, "chatgpt": 2022,
    "bge-large": 2023, "bge-base": 2023, "bge-small": 2023, "bge ": 2023,
    "llama-2": 2023, "llama 2": 2023, "llama-3": 2024, "mistral": 2023,
    "mixtral": 2023, "qlora": 2023, "llamaindex": 2022, "langchain": 2022,
    "claude": 2023, "gemini": 2023, "whisper": 2022, "instructor embedding": 2023,
}
ECOMM_TERMS = ("e-commerce", "ecommerce", "e commerce")
ECOMM_OK_INDUSTRY = ("commerce", "retail", "marketplace", "fashion", "consumer",
                     "food delivery", "shopping", "grocery")


def narrative_flags(c, data_date):
    """Clean narrative contradictions. Returns dict of lists/bools (NOT gated yet)."""
    career = c.get("career_history", []) or []

    # (a) role-predates-tool: a description names a tool whose release is AFTER the
    #     role ended entirely (current roles can't trip this).
    narr_anachronism = []
    for h in career:
        desc = (h.get("description") or "").lower()
        ed = parse_date(h.get("end_date"))
        end_year = ed.year if ed else (data_date.year if h.get("is_current") else None)
        if end_year is None:
            continue
        for tool, year in NARRATIVE_ERA.items():
            if tool in desc and end_year < year:
                narr_anachronism.append(f"{tool.strip()} in role ending {end_year} (pre-{year})")

    # (b) self-duplication: identical description across the person's OWN different companies.
    seen = {}
    self_dup = False
    for h in career:
        d = (h.get("description") or "").strip()
        comp = (h.get("company") or "").strip().lower()
        if not d:
            continue
        if d in seen and seen[d] != comp:
            self_dup = True
        seen.setdefault(d, comp)

    # (c) domain mismatch: description claims e-commerce but the role's industry isn't.
    domain_mismatch = []
    for h in career:
        desc = (h.get("description") or "").lower()
        ind = (h.get("industry") or "").lower()
        if any(t in desc for t in ECOMM_TERMS) and not any(k in ind for k in ECOMM_OK_INDUSTRY):
            domain_mismatch.append(f"'e-commerce' claim in {h.get('industry')} role")

    return {
        "narr_anachronism": narr_anachronism,
        "self_dup": self_dup,
        "domain_mismatch": domain_mismatch,
        "any": bool(narr_anachronism or self_dup or domain_mismatch),
    }