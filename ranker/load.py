"""
load.py — read candidates from .json (array), .jsonl, or .jsonl.gz.

The real pool ships as candidates.jsonl.gz (~52 MB / 100k lines). The sample
bundle is a plain JSON array. This loader handles all three transparently so
the same code runs on the sample and on the full pool.
"""

import json
import gzip


def open_text(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def load_candidates(path):
    with open_text(path) as f:
        first = f.read(1)
        f.seek(0)
        if first == "[":                       # JSON array (sample_candidates.json)
            return json.load(f)
        return [json.loads(line) for line in f if line.strip()]   # JSONL


def iter_candidates(path):
    """Streaming version for the full pool — avoids holding 465 MB in RAM
    when you only need one pass. Falls back to array-load for .json."""
    with open_text(path) as f:
        first = f.read(1)
        f.seek(0)
        if first == "[":
            for c in json.load(f):
                yield c
        else:
            for line in f:
                if line.strip():
                    yield json.loads(line)