"""Account hash normalization for reliable matching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Compiled once: strip only non-alphanumeric chars (preserve digits, letters, casing)
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def normalize_hash(value: str | None) -> str:
    """Normalize an account hash for comparison.

    - Strips leading/trailing whitespace
    - Removes non-alphanumeric characters
    - Preserves casing and leading zeros
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    return _NON_ALNUM.sub("", s)


def normalize_series(series: "pd.Series") -> "pd.Series":
    """Vectorized hash normalization for a pandas Series."""

    s = series.astype(str).str.strip()
    return s.str.replace(_NON_ALNUM, "", regex=True)
