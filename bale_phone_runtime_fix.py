"""Scoped Bale intake fix for Persian/Arabic-digit mobile numbers.

Bale job extraction already supports a name+phone fallback, but the canonical
PHONE_RE only recognized ASCII 0/9 in the prefix. As a result, ordinary work
messages using Persian/Arabic digits could be classified as ``not_work`` unless
they also contained one of the narrow service keywords. Keep the existing
parser behavior and only widen phone recognition.
"""
from __future__ import annotations

import re

import bale_bridge


# Preserve the canonical accepted forms (+98, 0098, 0, or no prefix) while
# accepting ASCII, Persian, and Arabic-Indic digits in those positions.
ZERO = r"[0۰٠]"
NINE = r"[9۹٩]"
EIGHT = r"[8۸٨]"
DIGIT = r"[0-9۰-۹٠-٩]"

bale_bridge.PHONE_RE = re.compile(
    rf"(?:(?:\+{NINE}{EIGHT})|(?:{ZERO}{ZERO}{NINE}{EIGHT})|{ZERO})?{NINE}{DIGIT}{{9}}"
)
