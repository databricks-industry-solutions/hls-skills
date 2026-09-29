#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["databricks-sdk>=0.40"]
# ///
"""Publish this repo's skills to a Unity Catalog schema from a local checkout.

Reads every skills/<name>/SKILL.md folder, publishes the skills whose content
changed since their last publish, and appends one row per skill (published and
skipped alike) to {catalog}.{schema}.skill_sync_audit. That table is both the
history of what each run did and how the next run detects changes.

    # List what would ship; no Databricks calls
    uv run sync_skills_git2unity.py --dry-run

    # Publish
    uv run sync_skills_git2unity.py --catalog hls_amer_catalog --schema vital_skills \\
        --warehouse-id <id> [--profile <databrickscfg-profile>]

Auth follows the Databricks SDK's default chain: --profile, DATABRICKS_* env
vars, or ~/.databrickscfg. The identity needs Unity Catalog skills enabled in the
workspace, USE CATALOG on the catalog, USE SCHEMA, CREATE SCHEMA, CREATE TABLE and
CREATE VOLUME on the schema, and CAN USE on the SQL warehouse.

Only files git knows about are published (tracked, or untracked but not ignored),
so local caches and results never ship. A dirty skills/ tree is refused unless
--allow-dirty, so commit_sha in the audit table is the content that shipped.

Nothing is ever deleted: a skill removed from the repo stays in the schema until
you drop it yourself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_REPO_URL = "https://github.com/databricks-industry-solutions/hls-skills"
SKILLS_API = "/api/2.1/unity-catalog/skills"
FILES_API = "/api/2.0/fs/files"

# Skill names are lowercase alphanumerics and inner hyphens, up to 64 characters.
SKILL_LEAF_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")

# A skill's eval/ folder holds its benchmark answer key (expectations, arm outputs):
# an agent that loads the published skill must not be able to read the ground truth
# it is graded on. tests/ is dev-only (unit tests, test deps). Both stay in git.
EXCLUDED_DIRS = frozenset({"eval", "tests"})


@dataclass
class AuditRow:
    leaf_name: str
    action: str
    skill_dir: str = ""
    bundle_hash: str = ""
    error: str = ""


# --- Bundle: what a skill publishes -------------------------------------------------


def _git(repo_dir: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args], capture_output=True, text=True, check=True
    ).stdout


def is_published(rel_path: str | Path) -> bool:
    """True if a path relative to the skill folder ships in the published bundle."""
    return Path(rel_path).parts[0] not in EXCLUDED_DIRS


def read_bundle(skill_dir: Path) -> dict[str, bytes]:
    """Maps each published path (relative to skill_dir) to its bytes."""
    listed = _git(skill_dir, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
    return {
        rel: (skill_dir / rel).read_bytes()
        for rel in sorted(set(listed.split("\0")))
        if rel and is_published(rel) and (skill_dir / rel).is_file()
    }


def bundle_hash(bundle: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for rel_path in sorted(bundle):
        digest.update(rel_path.encode())
        digest.update(bundle[rel_path])
    return digest.hexdigest()


def discover_skills(repo_root: Path) -> tuple[dict[str, Path], list[AuditRow]]:
    """Finds publishable skills under <repo_root>/skills/<name>/SKILL.md.

    Returns the publishable skills by leaf name, plus a skipped row for every
    folder that is not one.
    """
    skills_root = repo_root / "skills"
    skills: dict[str, Path] = {}
    skipped: list[AuditRow] = []
    if not skills_root.is_dir():
        print(f"WARNING: no skills/ directory at {skills_root}")
        return skills, skipped

    for skill_dir in sorted(d for d in skills_root.iterdir() if d.is_dir()):
        leaf, rel_dir = skill_dir.name, str(skill_dir.relative_to(repo_root))
        if not (skill_dir / "SKILL.md").is_file():
            skipped.append(AuditRow(leaf, "skipped_no_skill_md", rel_dir))
        elif not SKILL_LEAF_PATTERN.match(leaf):
            skipped.append(AuditRow(leaf, "skipped_invalid_name", rel_dir, error=f"fails {SKILL_LEAF_PATTERN.pattern}"))
        else:
            skills[leaf] = skill_dir
    return skills, skipped


# --- Databricks: SQL warehouse, schema, skills API -----------------------------------


def _quote(*parts: str) -> str:
    # A catalog or schema name may contain '-', which SQL would read as minus.
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)


def run_sql(w, warehouse_id: str, statement: str, **params: str) -> list[list[str]]:
    from databricks.sdk.service.sql import StatementParameterListItem, StatementState

    resp = w.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        parameters=[StatementParameterListItem(name=k, value=v) for k, v in params.items()],
        wait_timeout="50s",
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        detail = resp.status.error.message if resp.status.error else resp.status.state
        raise RuntimeError(f"SQL failed: {detail}\n{statement}")
    return (resp.result.data_array or []) if resp.result else []


def ensure_schema(w, catalog: str, schema: str) -> None:
    from databricks.sdk.errors import NotFound

    # A missing catalog is an operator error: it binds a storage root and carries
    # governance decisions, so it is never created here. Schemas are.
    w.catalogs.get(catalog)
    try:
        w.schemas.get(f"{catalog}.{schema}")
    except NotFound:
        w.schemas.create(name=schema, catalog_name=catalog)
        w.schemas.get(f"{catalog}.{schema}")  # re-read: create can be silently denied
        print(f"schema {catalog}.{schema} created")


def ensure_audit_table(w, warehouse_id: str, audit_table: str) -> None:
    run_sql(
        w,
        warehouse_id,
        f"""CREATE TABLE IF NOT EXISTS {audit_table} (
            sync_run_id STRING, event_time TIMESTAMP, repo_url STRING, commit_sha STRING,
            full_name STRING, leaf_name STRING, skill_dir STRING, action STRING,
            bundle_hash STRING, error STRING, run_by STRING)""",
    )


def last_published_hashes(w, warehouse_id: str, audit_table: str) -> dict[str, str]:
    rows = run_sql(
        w,
        warehouse_id,
        f"""SELECT full_name, bundle_hash FROM {audit_table}
            WHERE action IN ('created', 'updated')
            QUALIFY row_number() OVER (PARTITION BY full_name ORDER BY event_time DESC) = 1""",
    )
    return {full_name: h for full_name, h in rows}


def append_audit(w, warehouse_id: str, audit_table: str, rows: list[AuditRow], full_prefix: str, **run: str) -> None:
    # Rows travel as one JSON parameter so no value is ever spliced into the SQL text.
    payload = json.dumps([{"full_name": f"{full_prefix}.{r.leaf_name}", **asdict(r)} for r in rows])
    run_sql(
        w,
        warehouse_id,
        f"""INSERT INTO {audit_table}
            (sync_run_id, event_time, repo_url, commit_sha, full_name, leaf_name,
             skill_dir, action, bundle_hash, error, run_by)
            SELECT :sync_run_id, current_timestamp(), :repo_url, :commit_sha, full_name, leaf_name,
                   skill_dir, action, bundle_hash, error, :run_by
            FROM (SELECT inline(from_json(:rows,
                'ARRAY<STRUCT<full_name: STRING, leaf_name: STRING, action: STRING,
                              skill_dir: STRING, bundle_hash: STRING, error: STRING>>')))""",
        rows=payload,
        **run,
    )


def publish_skill(w, catalog: str, schema: str, leaf: str, bundle: dict[str, bytes]) -> str:
    """Creates (or re-publishes), uploads every file, and finalizes. Returns the audit action.

    Finalizing reads the uploaded SKILL.md, so its `name:` must match the folder
    and its `description:` must be at most 1024 bytes.
    """
    from databricks.sdk.errors import AlreadyExists

    api = w.api_client
    try:
        api.do("POST", SKILLS_API, query={"parent": f"schemas/{catalog}.{schema}", "skill_id": leaf}, body={})
        action = "created"
    except AlreadyExists:
        action = "updated"
    for rel_path, content in bundle.items():
        api.do(
            "PUT",
            f"{FILES_API}/Skills/{catalog}/{schema}/{leaf}/{rel_path}",
            headers={"Content-Type": "application/octet-stream"},
            data=content,
        )
    api.do("POST", f"{SKILLS_API}/{catalog}.{schema}.{leaf}/finalize")
    return action


# --- CLI -----------------------------------------------------------------------------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--catalog", default="hls_amer_catalog", help="Target UC catalog (must exist)")
    p.add_argument("--schema", default="vital_skills", help="Target UC schema (created if absent)")
    p.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""),
                   help="SQL warehouse for the audit table (default: $DATABRICKS_WAREHOUSE_ID)")
    p.add_argument("--profile", default=None, help="~/.databrickscfg profile")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Local checkout to publish from")
    p.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="Repo URL recorded in the audit table")
    p.add_argument("--dry-run", action="store_true", help="List what would ship; make no Databricks calls")
    p.add_argument("--allow-dirty", action="store_true", help="Publish uncommitted changes under skills/")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()

    skills, audit_rows = discover_skills(repo_root)
    bundles = {leaf: read_bundle(d) for leaf, d in skills.items()}
    hashes = {leaf: bundle_hash(b) for leaf, b in bundles.items()}
    rel_dirs = {leaf: str(d.relative_to(repo_root)) for leaf, d in skills.items()}
    for row in audit_rows:
        print(f"  {row.action:24} {row.skill_dir} {row.error}")

    if args.dry_run:
        for leaf in sorted(bundles):
            print(f"{leaf}  {hashes[leaf][:12]}  {len(bundles[leaf])} file(s)")
            for rel in bundles[leaf]:
                print(f"    {rel}")
        return 0

    if not args.warehouse_id:
        sys.exit("--warehouse-id (or DATABRICKS_WAREHOUSE_ID) is required unless --dry-run")
    commit_sha = _git(repo_root, "rev-parse", "HEAD").strip()
    if _git(repo_root, "status", "--porcelain", "--", "skills").strip():
        if not args.allow_dirty:
            sys.exit("skills/ has uncommitted changes; commit them or pass --allow-dirty")
        commit_sha += "-dirty"

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(profile=args.profile)
    catalog, schema, wh = args.catalog, args.schema, args.warehouse_id
    audit_table = _quote(catalog, schema, "skill_sync_audit")
    run = {
        "sync_run_id": str(uuid.uuid4()),
        "repo_url": args.repo_url,
        "commit_sha": commit_sha,
        "run_by": w.current_user.me().user_name,
    }
    print(f"run_id  {run['sync_run_id']}")
    print(f"source  {repo_root} @ {commit_sha}")
    print(f"target  {catalog}.{schema}")

    ensure_schema(w, catalog, schema)
    ensure_audit_table(w, wh, audit_table)
    published = last_published_hashes(w, wh, audit_table)

    for leaf in sorted(skills):
        row = AuditRow(leaf, "skipped_unchanged", rel_dirs[leaf], hashes[leaf])
        if published.get(f"{catalog}.{schema}.{leaf}") != hashes[leaf]:
            # Deliberately broad: one malformed bundle must not abort the rest of the sync.
            try:
                row.action = publish_skill(w, catalog, schema, leaf, bundles[leaf])
            except Exception as e:
                row.action, row.error = "error", str(e)
        audit_rows.append(row)
        print(f"  {row.action:24} {leaf} {row.error}")

    append_audit(w, wh, audit_table, audit_rows, f"{catalog}.{schema}", **run)

    for action, count in sorted(Counter(r.action for r in audit_rows).items()):
        print(f"  {action:24} {count}")
    errors = [r.leaf_name for r in audit_rows if r.action == "error"]
    if errors:
        print(f"{len(errors)} skill(s) failed to publish: {', '.join(errors)}", file=sys.stderr)
        return 1
    print(f"Synced {catalog}.{schema} to {args.repo_url} @ {commit_sha[:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
