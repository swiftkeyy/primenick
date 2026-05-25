from __future__ import annotations

import re

VOWELS = set("aeiouy")
RARE_BIGRAMS = {"vx", "zx", "qq", "io", "ai", "ox", "ny", "rx", "gg"}
TRENDING = {"ai", "lab", "neo", "void", "byte", "zen", "flux", "nova", "quant", "prime"}


def rarity_score(username: str) -> int:
    u = username.lower().strip("@")
    score = 0
    score += max(0, 36 - len(u) * 4)
    if re.fullmatch(r"[a-z]+", u): score += 12
    if re.fullmatch(r"[a-z0-9]+", u): score += 6
    if "_" not in u: score += 8
    if not re.search(r"(.)\1{2,}", u): score += 7
    vowel_ratio = sum(c in VOWELS for c in u) / max(1, len(u))
    if 0.25 <= vowel_ratio <= 0.55: score += 12
    score += sum(7 for b in RARE_BIGRAMS if b in u)
    score += sum(6 for t in TRENDING if t in u)
    if len(set(u)) >= min(len(u), 5): score += 10
    return max(0, min(100, score))
