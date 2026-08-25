"""Reserve paper readings atomically across concurrent reviewers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from paths import CLAIMS_DIR, REVIEWED_READINGS_DIR


ARXIV_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")
KNOWN_ROUTES = {"arxiv", "openreview", "urlhash"}


def normalize(value: str) -> str:
    """Return one canonical stable ID from a marker name or stable ID."""
    name = Path(value).name.removesuffix(".json")
    if ":" in name:
        return name
    if ARXIV_ID.fullmatch(name):
        return f"arxiv:{name}"
    route, separator, suffix = name.partition("_")
    if separator and route in KNOWN_ROUTES and suffix:
        return f"{route}:{suffix}"
    return name


def claim_id(path: Path) -> str:
    """Resolve a marker ID from its payload before its legacy filename."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("stable_id"), str):
        return normalize(payload["stable_id"])
    return normalize(path.name)


def claim_owner(path: Path) -> str:
    """Return the owner recorded by either JSON or legacy text markers."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict) and isinstance(payload.get("agent"), str):
        return payload["agent"].strip()
    return ""


def claim_path(stable_id: str, claims: Path = CLAIMS_DIR) -> Path:
    """Return the sole canonical marker path for a stable ID."""
    safe = normalize(stable_id).replace(":", "_", 1)
    return claims / f"{safe}.json"


def claim_ids(claims: Path = CLAIMS_DIR) -> set[str]:
    """Return normalized IDs from every nonempty marker form."""
    if not claims.exists():
        return set()
    return {
        claim_id(path)
        for path in claims.iterdir()
        if path.is_file() and path.stat().st_size > 0
    }


def read_ids(readings: Path = REVIEWED_READINGS_DIR) -> set[str]:
    """Return stable IDs already present in finalized reading records."""
    stable_ids = set()
    for path in readings.glob("*.json"):
        try:
            reading = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        stable_id = reading.get("stable_id")
        if isinstance(stable_id, str) and stable_id.strip():
            stable_ids.add(normalize(stable_id))
    return stable_ids


def reserve(
    stable_id: str,
    agent: str,
    claims: Path = CLAIMS_DIR,
    readings: Path = REVIEWED_READINGS_DIR,
) -> Path:
    """Create one atomic reservation or raise when work is owned already."""
    stable_id = normalize(stable_id)
    if stable_id in read_ids(readings):
        raise RuntimeError(f"Reading already exists: {stable_id}")
    if stable_id in claim_ids(claims):
        raise RuntimeError(f"Reading already claimed: {stable_id}")
    claims.mkdir(parents=True, exist_ok=True)
    path = claim_path(stable_id, claims)
    payload = json.dumps(
        {"agent": agent, "stable_id": stable_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as error:
        raise RuntimeError(f"Reading already claimed: {stable_id}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def release(
    stable_id: str,
    agent: str,
    claims: Path = CLAIMS_DIR,
) -> int:
    """Remove only markers for the requesting owner and stable ID."""
    stable_id = normalize(stable_id)
    removed = 0
    if not claims.exists():
        return removed
    for path in claims.iterdir():
        if (
            path.is_file()
            and path.stat().st_size > 0
            and claim_id(path) == stable_id
            and claim_owner(path) == agent
        ):
            path.unlink()
            removed += 1
    return removed


def main() -> None:
    """Expose reservation operations to independent reader processes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("reserve", "release", "list"))
    parser.add_argument("stable_id", nargs="?")
    parser.add_argument("--agent")
    args = parser.parse_args()

    if args.action == "list":
        for stable_id in sorted(claim_ids()):
            print(stable_id)
        return
    if not args.stable_id or not args.agent:
        parser.error("reserve and release require stable_id and --agent")
    if args.action == "reserve":
        print(reserve(args.stable_id, args.agent))
        return
    print(release(args.stable_id, args.agent))


if __name__ == "__main__":
    main()
