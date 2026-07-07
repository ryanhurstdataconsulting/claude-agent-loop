#!/usr/bin/env python3
"""Machine-prose grammar helpers (Resource Loop Phase 5).

Two functions that project code imports so generated end-user text is correct
at generation time:

- ``indefinite_article(value)`` picks "a" or "an" by the *spoken sound* of the
  following token, and is number-aware ("an 8.1", "a 32.2", "an 11", "a 5.0").
- ``pluralize(count, singular, plural=None)`` renders a count with a correctly
  pluralized noun ("1 officer", "2 officers", "0 goals").

Stdlib only. Pairs with ``prose_grammar_gate.py``, the standalone linter.
"""
from __future__ import annotations

import re

# --- number-to-leading-word tables --------------------------------------------
# The indefinite article depends only on the *first spoken word* of a number,
# so we resolve that word rather than spelling the whole number out.
_ONES = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen",
    16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
}
_TENS = {
    2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
    7: "seventy", 8: "eighty", 9: "ninety",
}

# --- word-sound tables --------------------------------------------------------
_VOWEL_LETTERS = set("aeiou")

# Words that start with a vowel *letter* but a consonant *sound* → take "a".
# "yu"-sound words (university, unit, euro...) and "w"-sound words (one, once).
# Curated whole words are used rather than prefixes because "uni" is ambiguous:
# "uniform" is /juː/ (→ "a") but "uninformed" is /ʌn/ (→ "an").
_A_WORDS = {
    "university", "universities", "universal", "universe", "unicorn",
    "unicycle", "uniform", "uniformed", "unique", "uniquely", "unit", "units",
    "unite", "united", "unity", "union", "unions", "unified", "unify",
    "unilateral", "unison", "unisex", "unanimous", "unanimously", "unanimity",
    "usual", "usually", "use", "used", "usable", "usably", "usability",
    "useful", "useless", "user", "users", "using", "usage", "utensil",
    "utility", "utilities", "utilize", "utilized", "utopia", "ubiquitous",
    "ukulele", "uranium", "euro", "europe", "european", "euphoria",
    "euphemism", "eulogy", "eugenics", "ewe", "one", "once", "oneself",
}

# Words that start with a consonant *letter* (h) but a vowel *sound* → "an".
_AN_WORDS = {
    "hour", "hours", "hourly", "honest", "honestly", "honesty", "honor",
    "honors", "honored", "honour", "honours", "honorable", "honourable",
    "honorary", "heir", "heirs", "heiress", "heirloom",
}

# Letters whose spoken *name* begins with a vowel sound → an initialism that
# starts with one of them takes "an" (an FBI file, an NFL game, an X-ray).
# Vowels A, E, I, O qualify; U does not ("you"). Consonants F, H, L, M, N, R,
# S, X do ("eff", "aitch", "el", "em", "en", "ar", "es", "ex").
_AN_LETTERS = set("AEFHILMNORSX")

# All-caps tokens pronounced as ordinary words, not spelled out letter by
# letter. First letters here are consonant-sounding, so the default vowel rule
# already yields "a"; excluding them from the initialism branch is enough.
_ACRONYM_AS_WORD = {"NASA", "NATO", "NAFTA", "SCUBA", "LASER", "RADAR"}

_LEADING_NUMBER = re.compile(r"^[-+]?(\d[\d,]*)")
_LEADING_ALPHA = re.compile(r"[A-Za-z]+")


def _leading_number_word(n: int) -> str:
    """Return the first spoken word of a non-negative integer.

    Only the most-significant group drives the article, e.g. 18000 speaks as
    "eighteen thousand" → "eighteen", and 180000 as "one hundred eighty
    thousand" → "one".
    """
    n = abs(int(n))
    digits = str(n)
    if len(digits) <= 3:
        group = n
    else:
        lead = len(digits) % 3 or 3
        group = int(digits[:lead])
    if group >= 100:
        return _ONES[group // 100]
    if group >= 20:
        return _TENS[group // 10]
    return _ONES[group]


def _article_for_word(word: str) -> str:
    """Pick "a"/"an" for a single already-spoken word or token."""
    stripped = word.strip()
    letters_only = re.sub(r"[^A-Za-z]", "", stripped)

    # Initialism spelled out letter by letter (FBI, NFL, X-ray), but not the
    # handful of all-caps tokens that are said as words (NASA, NATO).
    if (letters_only.isupper() and len(letters_only) >= 2
            and letters_only not in _ACRONYM_AS_WORD):
        return "an" if letters_only[0] in _AN_LETTERS else "a"

    match = _LEADING_ALPHA.search(stripped)
    if not match:
        return "a"
    base = match.group(0).lower()

    if base in _AN_WORDS:
        return "an"
    if base in _A_WORDS:
        return "a"
    return "an" if base[0] in _VOWEL_LETTERS else "a"


def indefinite_article(value) -> str:
    """Return "a" or "an" for ``value`` by the spoken sound of its first token.

    ``value`` may be an int, a float, or a string. Numbers (given as a number
    type or as a numeric string, with optional commas, decimals, or an ordinal
    suffix such as "11th") are resolved to their leading spoken word first.
    """
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        return _article_for_word(_leading_number_word(int(abs(value))))

    text = str(value).strip()
    if not text:
        return "a"
    token = text.split()[0]
    number = _LEADING_NUMBER.match(token)
    if number:
        integer_part = int(number.group(1).replace(",", ""))
        return _article_for_word(_leading_number_word(integer_part))
    return _article_for_word(token)


# Punctuation the linter strips from a next-token before judging its onset.
_TOKEN_STRIP = ".,;:!?\"'()[]{}"


def article_onset_confident(token) -> str:
    """Return "a"/"an" only when the spoken onset of ``token`` is *certain*.

    The linter uses this to decide whether an article mismatch is safe to
    flag. Guessing wrong here would "correct" already-correct client prose —
    the worst outcome — so this is deliberately conservative: it returns
    ``None`` whenever the onset is ambiguous, and the linter then stays silent.

    Confident (returns "a"/"an"):
      - numbers, resolved by their leading spoken word ("an 8.1", "a 32.2");
      - plain lowercase dictionary-style words with a clear vowel/consonant
        onset ("an hour", "a university", "a match").

    Not confident (returns ``None`` → suppress the flag):
      - ALL-CAPS words that read as words, not letters ("a MATCH", "a ROUTE");
      - hyphenated or mixed-case tokens ("an API-side", "a QA-only");
      - lowercase tool-names whose onset is implausible for English
        ("an ffmpeg", "an sqlite") — no real word opens with such a cluster.
    """
    text = str(token).strip()
    if not text:
        return None
    first = text.split()[0]

    # (a) numbers — reuse the number-aware resolver. Always confident.
    if _LEADING_NUMBER.match(first):
        return indefinite_article(first)

    core = first.strip(_TOKEN_STRIP)
    if not core:
        return None

    # (b) plain lowercase dictionary-style word. Curated onset-exception words
    # (hour, university, ...) are always trusted; otherwise require a vowel
    # within the first three letters, which every ordinary English onset has
    # (up to a 3-consonant cluster like "str-"). Tokens that fail this — e.g.
    # "ffmpeg", "sqlite" — are not real words and their onset is unknown.
    if core.isascii() and core.isalpha() and core.islower():
        if core in _AN_WORDS or core in _A_WORDS:
            return indefinite_article(core)
        if any(ch in _VOWEL_LETTERS for ch in core[:3]):
            return indefinite_article(core)

    # ALL-CAPS words, hyphenated-caps, mixed-case, and implausible lowercase
    # clusters all land here: onset unknown → suppress rather than guess.
    return None


def _naive_plural(singular: str) -> str:
    """Best-effort regular plural. Pass an explicit plural for irregulars."""
    if re.search(r"(s|x|z|ch|sh)$", singular):
        return singular + "es"
    if re.search(r"[^aeiou]y$", singular):
        return singular[:-1] + "ies"
    return singular + "s"


def pluralize(count, singular: str, plural: str = None) -> str:
    """Render ``count`` with a correctly pluralized noun.

    ``pluralize(1, "officer")`` → "1 officer"; ``pluralize(2, "officer")`` →
    "2 officers"; ``pluralize(0, "goal")`` → "0 goals". Supply ``plural`` for
    irregulars, e.g. ``pluralize(2, "person", "people")`` → "2 people".
    """
    if count == 1:
        word = singular
    elif plural is not None:
        word = plural
    else:
        word = _naive_plural(singular)
    return f"{count} {word}"
