#!/usr/bin/env python3
"""Build semantic cloud months in bounded deterministic partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

from archive import read_manifest, read_shard
from cloud import (
    MAGIC,
    MODEL_REVISION,
    SCOPES,
    embed_records,
    load_anchors,
    valid_asset,
    validate_cloud,
    write_month,
    write_reused,
)
from embed import MODEL, MODEL_DIGEST
from files import atomic_write_bytes, atomic_write_text
from omit import (
    archive_text,
    cloud_cover,
    cloud_manifest,
    foreground_hash,
    ids_hash,
    load_foreground,
    read_cloud,
    reuse_bytes,
)


MONTH = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SHARD = re.compile(
    r"^(?P<month>[0-9]{4}-(?:0[1-9]|1[0-2]))(?:-[0-9a-f]{16})?\.json\.gz$"
)
COUNT_KEYS = {"all", *SCOPES}


def file_hash(path: Path) -> str:
    """Hash one bounded pipeline artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_rows(source: dict) -> list[dict]:
    """Require exact ordered source identities and reconciled counts."""
    if not isinstance(source, dict):
        raise ValueError("Cloud source manifest is invalid")
    shards = source.get("shards")
    counts = source.get("counts")
    if (
        source.get("schema_version") != 1
        or not isinstance(shards, list)
        or not isinstance(counts, dict)
        or set(counts) != COUNT_KEYS
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts.values()
        )
    ):
        raise ValueError("Cloud source manifest is invalid")
    months = []
    totals = {key: 0 for key in COUNT_KEYS}
    for row in shards:
        month = row.get("month") if isinstance(row, dict) else None
        path = row.get("path") if isinstance(row, dict) else None
        digest = row.get("sha256") if isinstance(row, dict) else None
        row_counts = row.get("counts") if isinstance(row, dict) else None
        match = SHARD.fullmatch(path or "")
        if (
            not isinstance(month, str)
            or not MONTH.fullmatch(month)
            or match is None
            or match.group("month") != month
            or not isinstance(digest, str)
            or not DIGEST.fullmatch(digest)
            or not isinstance(row_counts, dict)
            or set(row_counts) != COUNT_KEYS
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in row_counts.values()
            )
            or row_counts["all"] != sum(row_counts[scope] for scope in SCOPES)
        ):
            raise ValueError("Cloud source shard is invalid")
        months.append(month)
        for key in COUNT_KEYS:
            totals[key] += row_counts[key]
    if months != sorted(set(months)) or totals != counts:
        raise ValueError("Cloud source counts are not reconciled")
    return shards


def read_plan(path: Path) -> dict:
    """Read and validate one deterministic partition plan."""
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Cloud partition plan is unreadable") from error
    if not isinstance(plan, dict):
        raise ValueError("Cloud partition plan is invalid")
    parts = plan.get("partitions")
    foreground = plan.get("foreground")
    if (
        plan.get("schema_version") != 1
        or not isinstance(plan.get("source_sha256"), str)
        or not DIGEST.fullmatch(plan["source_sha256"])
        or not isinstance(plan.get("source_count"), int)
        or isinstance(plan.get("source_count"), bool)
        or plan["source_count"] < 0
        or not isinstance(plan.get("changed_count"), int)
        or isinstance(plan.get("changed_count"), bool)
        or plan["changed_count"] < 0
        or plan["changed_count"] > plan["source_count"]
        or not isinstance(plan.get("foreground_sha256"), str)
        or not DIGEST.fullmatch(plan["foreground_sha256"])
        or not isinstance(foreground, dict)
        or any(
            not isinstance(month, str)
            or not MONTH.fullmatch(month)
            or not isinstance(ids, list)
            or ids != sorted(set(ids))
            or any(
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 128
                or any(character.isspace() for character in identifier)
                for identifier in ids
            )
            for month, ids in foreground.items()
        )
        or not isinstance(parts, list)
        or len(parts) > 32
        or any(
            not isinstance(part, dict)
            or part.get("id") != index
            or not isinstance(part.get("months"), list)
            or not isinstance(part.get("count"), int)
            or isinstance(part.get("count"), bool)
            or part["count"] < 0
            for index, part in enumerate(parts)
        )
    ):
        raise ValueError("Cloud partition plan is invalid")
    months = [month for part in parts for month in part["months"]]
    if (
        len(months) != len(set(months))
        or sum(part["count"] for part in parts) != plan["changed_count"]
        or any(
            not isinstance(month, str) or not MONTH.fullmatch(month) for month in months
        )
        or any(part["months"] != sorted(part["months"]) for part in parts)
        or plan["foreground_sha256"]
        != foreground_hash({month: set(ids) for month, ids in foreground.items()})
    ):
        raise ValueError("Cloud partition months are invalid")
    return plan


def row_changed(
    row: dict, prior: dict | None, output: Path, foreground: set[str]
) -> bool:
    """Return whether one source month needs new browser assets."""
    if (
        not isinstance(prior, dict)
        or prior.get("source_sha256") != row.get("sha256")
        or prior.get("foreground_sha256") != ids_hash(foreground)
    ):
        return True
    try:
        point_path = output / prior["points"]["path"]
        meta_path = output / prior["meta"]["path"]
    except (KeyError, TypeError):
        return True
    return not (
        valid_asset(point_path, prior.get("points"))
        and valid_asset(meta_path, prior.get("meta"))
    )


def make_plan(
    archive: Path,
    output: Path,
    limit: int,
    foreground: dict[str, set[str]] | None = None,
) -> dict:
    """Balance changed months without splitting any monthly cache."""
    if not 1 <= limit <= 32:
        raise ValueError("Cloud partition limit must be between 1 and 32")
    source = read_manifest(archive)
    foreground = foreground or {}
    rows = source_rows(source)
    try:
        prior = read_cloud(output / "index.json")
    except RuntimeError:
        prior = {"schema_version": 1, "shards": []}
    prior_rows = {row.get("month"): row for row in prior["shards"]}
    changed = [
        row
        for row in rows
        if row_changed(
            row,
            prior_rows.get(row.get("month")),
            output,
            foreground.get(row["month"], set()),
        )
    ]
    total = min(limit, len(changed))
    parts = [{"id": index, "count": 0, "months": []} for index in range(total)]
    ranked = sorted(changed, key=lambda row: (-row["counts"]["all"], row["month"]))
    for row in ranked:
        part = min(parts, key=lambda item: (item["count"], item["id"]))
        part["months"].append(row["month"])
        part["count"] += row["counts"]["all"]
    for part in parts:
        part["months"].sort()
    return {
        "schema_version": 1,
        "source_sha256": file_hash(archive / "index.json"),
        "source_count": source["counts"]["all"],
        "changed_count": sum(row["counts"]["all"] for row in changed),
        "foreground_sha256": foreground_hash(foreground),
        "foreground": {
            month: sorted(identifiers)
            for month, identifiers in sorted(foreground.items())
        },
        "partitions": parts,
    }


def build_part(
    archive: Path,
    anchors: Path,
    cache: Path,
    output: Path,
    plan_path: Path,
    part_id: int,
    batch_size: int,
    provider: str,
    prior: Path | None = None,
) -> dict:
    """Build every month assigned to one isolated worker."""
    plan = read_plan(plan_path)
    if file_hash(archive / "index.json") != plan["source_sha256"]:
        raise ValueError("Cloud partition source changed after planning")
    try:
        part = plan["partitions"][part_id]
    except IndexError as error:
        raise ValueError("Cloud partition ID is invalid") from error
    if part["id"] != part_id:
        raise ValueError("Cloud partition ID is misaligned")
    source = read_manifest(archive)
    source_map = {row["month"]: row for row in source_rows(source)}
    prior_rows = {
        row.get("month"): row
        for row in read_cloud((prior or output) / "index.json")["shards"]
    }
    anchor_rows = load_anchors(anchors)
    output.mkdir(parents=True, exist_ok=True)
    shards = []
    for month in part["months"]:
        row = source_map.get(month)
        if row is None:
            raise ValueError(f"Cloud partition source is missing {month}")
        path = archive / row["path"]
        if not path.is_file() or file_hash(path) != row["sha256"]:
            raise ValueError(f"Cloud partition shard drifted: {month}")
        source_papers = read_shard(path)["papers"]
        counts = {
            "all": len(source_papers),
            **{
                scope: sum(paper.get("scope") == scope for paper in source_papers)
                for scope in SCOPES
            },
        }
        if counts != row["counts"]:
            raise ValueError(f"Cloud partition counts drifted: {month}")
        papers, coverage = cloud_cover(
            source_papers, set(plan["foreground"].get(month, []))
        )
        reused = reuse_bytes(
            prior or output,
            prior_rows.get(month, {}),
            [paper["id"] for paper in papers],
            MAGIC,
            row["sha256"],
        )
        if reused is not None:
            shards.append(
                write_reused(month, row["sha256"], papers, reused, output, coverage)
            )
            continue
        records = [(paper["id"], archive_text(paper)) for paper in papers]
        vectors = embed_records(month, records, cache, batch_size, 1, provider)
        shards.append(
            write_month(
                month,
                row["sha256"],
                papers,
                vectors,
                anchor_rows,
                output,
                coverage,
            )
        )
    fragment = {
        "schema_version": 1,
        "source_sha256": plan["source_sha256"],
        "part": part_id,
        "count": sum(row["count"] for row in shards),
        "shards": shards,
    }
    atomic_write_text(
        output / f"part-{part_id:02d}.json",
        json.dumps(fragment, ensure_ascii=False, indent=2) + "\n",
    )
    return fragment


def read_parts(root: Path, plan: dict) -> dict[str, tuple[dict, Path]]:
    """Validate and index every expected worker fragment."""
    rows: dict[str, tuple[dict, Path]] = {}
    expected = {part["id"] for part in plan["partitions"]}
    found = set()
    for path in sorted(root.glob("part-??.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Cloud worker fragment is invalid")
        part = value.get("part")
        if (
            value.get("schema_version") != 1
            or value.get("source_sha256") != plan["source_sha256"]
            or part not in expected
            or part in found
            or not isinstance(value.get("shards"), list)
        ):
            raise ValueError("Cloud worker fragment is invalid")
        found.add(part)
        planned = plan["partitions"][part]["months"]
        actual = [row.get("month") for row in value["shards"]]
        if actual != planned or value.get("count") != sum(
            row.get("count", -1) for row in value["shards"]
        ):
            raise ValueError("Cloud worker fragment is incomplete")
        for row in value["shards"]:
            month = row["month"]
            if month in rows:
                raise ValueError("Cloud worker month is duplicated")
            rows[month] = (row, path.parent)
    if found != expected:
        raise ValueError("Cloud worker fragments are missing")
    return rows


def cloud_floor(output: Path, cloud: dict) -> int:
    """Return a prior source count only when its local assets reconcile."""
    rows = cloud.get("shards")
    count = cloud.get("source_count")
    if (
        not isinstance(rows, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or count != sum(row.get("source_count", -1) for row in rows)
        or cloud.get("count") != sum(row.get("count", -1) for row in rows)
        or cloud.get("omitted_count")
        != sum(row.get("omitted_count", -1) for row in rows)
    ):
        return 0
    months = [row.get("month") for row in rows]
    if months != sorted(set(months)):
        return 0
    for row in rows:
        if row.get("source_count") != row.get("count", -1) + row.get(
            "omitted_count", -1
        ) or any(
            not valid_asset(output / row.get(key, {}).get("path", ""), row.get(key))
            for key in ("points", "meta")
        ):
            return 0
    return count


def join_parts(
    archive: Path,
    output: Path,
    plan_path: Path,
    parts: Path,
    allow_shrink: bool = False,
) -> dict:
    """Publish one manifest only after every worker fragment validates."""
    plan = read_plan(plan_path)
    if file_hash(archive / "index.json") != plan["source_sha256"]:
        raise ValueError("Cloud join source changed after planning")
    source = read_manifest(archive)
    source_list = source_rows(source)
    foreground = {month: set(ids) for month, ids in plan["foreground"].items()}
    try:
        prior = read_cloud(output / "index.json")
    except RuntimeError:
        prior = {"schema_version": 1, "shards": []}
    floor = cloud_floor(output, prior)
    if source["counts"]["all"] < floor and not allow_shrink:
        raise ValueError(
            f"Cloud source regression: {source['counts']['all']:,} is below {floor:,}; "
            "use --allow-shrink only for a reviewed migration"
        )
    shards = {row.get("month"): row for row in prior["shards"]}
    changed = read_parts(parts, plan)
    for month, (row, _root) in changed.items():
        shards[month] = row
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        stage = Path(directory)
        ordered = []
        for source_row in source_list:
            month = source_row["month"]
            row = shards.get(month)
            root = changed[month][1] if month in changed else output
            if (
                not isinstance(row, dict)
                or row.get("source_sha256") != source_row["sha256"]
                or row.get("source_count") != source_row["counts"]["all"]
                or row.get("foreground_sha256")
                != ids_hash(foreground.get(month, set()))
            ):
                raise ValueError(f"Cloud join is missing {month}")
            for key in ("points", "meta"):
                meta = row.get(key)
                path = root / meta.get("path", "") if isinstance(meta, dict) else root
                if not valid_asset(path, meta):
                    raise ValueError(f"Cloud join asset drifted: {month}")
                atomic_write_bytes(stage / path.name, path.read_bytes())
            ordered.append(row)
        manifest = cloud_manifest(
            ordered, foreground, MODEL, MODEL_DIGEST, MODEL_REVISION
        )
        atomic_write_text(
            stage / "index.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        result = validate_cloud(archive, stage, foreground)
        output.mkdir(parents=True, exist_ok=True)
        for row in ordered:
            for key in ("points", "meta"):
                name = row[key]["path"]
                atomic_write_bytes(output / name, (stage / name).read_bytes())
        atomic_write_bytes(output / "index.json", (stage / "index.json").read_bytes())
    return result


def parse_args() -> argparse.Namespace:
    """Parse one parallel-cloud command."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--archive", type=Path, required=True)
    plan.add_argument("--cloud", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--parts", type=int, default=16)
    plan.add_argument("--atlas", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("--archive", type=Path, required=True)
    build.add_argument("--anchors", type=Path, required=True)
    build.add_argument("--cache", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--part", type=int, required=True)
    build.add_argument("--batch-size", type=int, default=4096)
    build.add_argument("--provider", choices=("native", "ollama"), default="native")
    build.add_argument("--prior", type=Path)
    join = commands.add_parser("join")
    join.add_argument("--archive", type=Path, required=True)
    join.add_argument("--cloud", type=Path, required=True)
    join.add_argument("--plan", type=Path, required=True)
    join.add_argument("--parts", type=Path, required=True)
    join.add_argument("--allow-shrink", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run one parallel-cloud command."""
    args = parse_args()
    if args.command == "plan":
        plan = make_plan(
            args.archive, args.cloud, args.parts, load_foreground(args.atlas)
        )
        atomic_write_text(args.output, json.dumps(plan, indent=2) + "\n")
        print(json.dumps(plan, separators=(",", ":")))
    elif args.command == "build":
        result = build_part(
            args.archive,
            args.anchors,
            args.cache,
            args.output,
            args.plan,
            args.part,
            args.batch_size,
            args.provider,
            args.prior,
        )
        print(json.dumps(result, separators=(",", ":")))
    else:
        result = join_parts(
            args.archive,
            args.cloud,
            args.plan,
            args.parts,
            args.allow_shrink,
        )
        print(json.dumps({"count": result["count"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
