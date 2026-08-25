"""Authoritative boundaries between reviewed source data and generated artifacts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_READINGS_DIR = ROOT / "data/reviewed/readings"
CLAIMS_DIR = REVIEWED_READINGS_DIR / ".claims"
