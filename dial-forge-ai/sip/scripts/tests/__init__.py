"""Tests for archived SIP/Asterisk voice runtime helpers."""

from __future__ import annotations

import sys
from pathlib import Path


LEGACY_ASTERISK_PATH = Path(__file__).resolve().parents[1] / "archive" / "asterisk_legacy"

if str(LEGACY_ASTERISK_PATH) not in sys.path:
    sys.path.insert(0, str(LEGACY_ASTERISK_PATH))
