"""
firstpass.py — cheap, recall-oriented relevance proxy.

Job: from 100k candidates, surface the few hundred that *look* relevant to the
JD so we can label/audit that contested set. This is NOT the final ranker.

It favours recall: better to include a keyword-stuffer (a useful labeled
hard-negative) than to miss a real fit. We read the NARRATIVE (titles + career
descriptions + summary + headline), not the gameable skills list. Skills only
contribute when *backed* by assessment / endorsements / duration.

Everything is a transparent weighted count — no model, no labels, defensible.
"""

# JD-relevant vocabulary, weighted by how decisive each term is for THIS role.
DECISIVE = {
    "learning to rank": 3.0, "learning-to-rank": 3.0, "ltr": 2.0,
    "ranking": 2.2, "recommendation": 2.5, "recommender": 2.5,
    "retrieval": 2.5, "information retrieval": 3.0,
    "semantic search": 2.5, "vector search": 2.5, "hybrid search": 2.5,
    "neural search": 2.5, "search ranking": 2.5, "search relevance": 2.5,
    "search system": 2.0, "search quality": 2.0,
    "relevance": 1.2, "embedding": 2.0, "embeddings": 2.0,
}
STRONG = {
    "applied ml": 1.5, "applied scientist": 1.5, "ml engineer": 1.5,
    "machine learning": 1.2, "nlp": 1.2, "deep learning": 1.0,
    "transformer": 1.0, "fine-tun": 0.8, "rag": 1.0, "personalization": 1.2,
}
TOOLS = {
    "pinecone": 1.0, "weaviate": 1.0, "qdrant": 1.0, "milvus": 1.0, "faiss": 1.0,
    "elasticsearch": 0.8, "opensearch": 0.8, "sentence-transformers": 1.2,
    "sentence transformers": 1.2, "sbert": 1.0, "xgboost": 0.8, "lightgbm": 0.8,
    "ndcg": 1.5, "mrr": 1.2, "a/b test": 1.0, "ab test": 1.0,
}
# Areas the JD pushes away from (CV / speech / robotics). Tracked; lightly penalized.
OFF_AREA = {
    "image classification": 1.0, "object detection": 1.0, "computer vision": 1.0,
    "speech recognition": 1.0, "tts": 0.8, "asr": 0.8, "gans": 0.8, "robotics": 1.0,
}

_AI_SKILL_TERMS = (set(DECISIVE) | set(STRONG) | set(TOOLS) |
                   {"pytorch", "tensorflow", "huggingface", "hugging face", "vector",
                    "mlops", "mlflow", "feature engineering", "scikit-learn"})


import re

# Precompile a word-boundary pattern per term so "search" doesn't match
# "research" and "rag" doesn't match "storage". Boundaries are placed around
# the alphanumeric edges of each term; internal punctuation (a/b, learning-to-
# rank) is matched literally.
def _compile(vocab):
    out = []
    for term, w in vocab.items():
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")
        out.append((pat, w))
    return out


def _hits(compiled, text):
    t = text.lower()
    return sum(w for pat, w in compiled if pat.search(t))


def narrative(c):
    p = c.get("profile", {}) or {}
    parts = [p.get("headline", ""), p.get("summary", "")]
    for h in c.get("career_history", []) or []:
        parts.append(h.get("title", ""))
        parts.append(h.get("description", ""))
    return " \n ".join(x for x in parts if x)


def _is_ai_skill(name):
    n = " " + (name or "").lower() + " "
    return any(term in n for term in _AI_SKILL_TERMS)


def skill_backing(s, assess):
    """0..1 trust that a self-claimed skill is real evidence, not stuffing."""
    score = 0.0
    a = assess.get(s.get("name"))
    if a is not None:
        score += min(1.0, a / 70.0) * 0.60          # platform test = strongest signal
    score += min(1.0, (s.get("endorsements") or 0) / 30.0) * 0.25
    score += min(1.0, (s.get("duration_months") or 0) / 24.0) * 0.15
    return min(1.0, score)


_C_DECISIVE = _compile(DECISIVE)
_C_STRONG = _compile(STRONG)
_C_TOOLS = _compile(TOOLS)
_C_OFF = _compile(OFF_AREA)


def first_pass_score(c):
    narr = narrative(c)
    decisive = _hits(_C_DECISIVE, narr)
    strong = _hits(_C_STRONG, narr)
    tools = _hits(_C_TOOLS, narr)
    off = _hits(_C_OFF, narr)

    assess = (c.get("redrob_signals", {}) or {}).get("skill_assessment_scores", {}) or {}
    backed_skill = sum(skill_backing(s, assess)
                       for s in (c.get("skills", []) or []) if _is_ai_skill(s.get("name")))

    score = (1.6 * decisive + 1.0 * strong + 0.7 * tools + 0.5 * backed_skill) - 0.4 * off
    comp = {"decisive": decisive, "strong": strong, "tools": tools,
            "off_area": off, "backed_skill": round(backed_skill, 2)}
    return score, comp