# Databricks notebook source
# MAGIC %md
# MAGIC # Sync a plugin-marketplace Git repo to a Unity Catalog schema
# MAGIC
# MAGIC Publishes the skills from every plugin in a plugin-marketplace Git repository
# MAGIC into a single Unity Catalog schema, so the schema tracks a branch of your repo.
# MAGIC Run it on a schedule to keep the two in sync.
# MAGIC
# MAGIC A marketplace repository holds many plugins, each with its own `skills/`
# MAGIC directory. Each run finds them by looking for `.claude-plugin/marketplace.json`
# MAGIC files, resolves the `source` path of every plugin they declare, and publishes all
# MAGIC of their skills into your target schema.
# MAGIC
# MAGIC A skill name has to be unique within a schema. If two plugins ship a skill with
# MAGIC the same name, the first one wins and the other is recorded as skipped rather
# MAGIC than published, so you can find and rename it.
# MAGIC
# MAGIC Every run appends one row per skill — published and skipped alike — to
# MAGIC `{catalog}.{schema}.skill_sync_audit`. That table is both the history of what the
# MAGIC notebook did and how it detects changes on the next run.
# MAGIC
# MAGIC **What you need before running**
# MAGIC - Unity Catalog skills enabled in your workspace.
# MAGIC - `USE CATALOG` on the target catalog, `USE SCHEMA` and `CREATE SCHEMA` on the
# MAGIC   target schema, and `CREATE VOLUME` on that schema.
# MAGIC - For a private repo, a Git credential configured for the identity that runs
# MAGIC   this notebook (**Settings > Linked accounts**), and its ID in the
# MAGIC   `git_credential_id` widget.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

dbutils.widgets.text("git_url", "https://github.com/databricks-industry-solutions/hls-skills.git", "Skills repo HTTPS clone URL")
dbutils.widgets.text("catalog", "hls_amer_catalog", "Target UC catalog (must exist)")
dbutils.widgets.text("schema", "vital_skills", "Target UC schema (created if absent)")
dbutils.widgets.text("branch", "dev", "Branch to track")
dbutils.widgets.text("git_credential_id", "", "Git credential ID (blank for public repos)")

# COMMAND ----------

GIT_URL = dbutils.widgets.get("git_url").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
BRANCH = dbutils.widgets.get("branch").strip()
GIT_CREDENTIAL_ID = dbutils.widgets.get("git_credential_id").strip()
CATALOG, SCHEMA, BRANCH

# COMMAND ----------

for widget, value in [("git_url", GIT_URL), ("catalog", CATALOG), ("schema", SCHEMA), ("branch", BRANCH)]:
    if not value:
        raise ValueError(f"Widget '{widget}' is required")

AUDIT_TABLE = f"{CATALOG}.{SCHEMA}.skill_sync_audit"
# Backtick-quoted for the SQL parser: a catalog or schema name may legally contain
# characters like '-' that would otherwise be read as operators (e.g. das-0806 -> das - 0806).
AUDIT_TABLE_SQL = f"`{CATALOG}`.`{SCHEMA}`.`skill_sync_audit`"

# COMMAND ----------

import hashlib
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import AlreadyExists, NotFound
from pyspark.sql.functions import current_timestamp, lit

w = WorkspaceClient()
api = w.api_client

SKILLS_API = "/api/2.1/unity-catalog/skills"
FILES_API = "/api/2.0/fs/files"

# Skill names are lowercase alphanumerics and inner hyphens, up to 64 characters.
SKILL_LEAF_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")

SYNC_RUN_ID = str(uuid.uuid4())
RUN_BY = dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
REPO_NAME = GIT_URL.rstrip("/").split("/")[-1].removesuffix(".git")
REPO_PATH = f"/Workspace/Users/{RUN_BY}/skills-sync/{REPO_NAME}"

print(f"run_id  {SYNC_RUN_ID}")
print(f"repo    {GIT_URL} @ {BRANCH} -> {REPO_PATH}")
print(f"target  {CATALOG}.{SCHEMA}")
print(f"audit   {AUDIT_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Check out the repo as a Workspace Git folder
# MAGIC
# MAGIC A Git folder never updates on its own, so every run pulls the branch explicitly.
# MAGIC The Repos REST API is called directly here because it accepts a Git credential ID
# MAGIC and returns the checked-out commit, which the SDK's typed helpers do not.
# MAGIC
# MAGIC This notebook only reads from the folder, never writes to it. If a pull ever
# MAGIC conflicts with local edits, the run fails rather than discarding them: the API's
# MAGIC force-discard option deletes uncommitted work permanently.
# MAGIC
# MAGIC The pull is not immediately consistent with your push. A run that starts seconds
# MAGIC after a commit may still check out the previous one, skip everything as unchanged,
# MAGIC and pick the change up on the next run. `commit_sha` in the audit table is
# MAGIC therefore the commit the run actually synced, not necessarily the branch tip at
# MAGIC the time it started.

# COMMAND ----------

# git helper functions
import subprocess

def _has_git_cli(repo_dir) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--git-dir"],
            capture_output=True, text=True, check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def _git(repo_dir, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()

# COMMAND ----------

def checkout_repo() -> str:
    """Clones or pulls the repo at REPO_PATH and returns its HEAD commit SHA."""
    repo_dir = Path(REPO_PATH)

    if not repo_dir.exists():
        # Creating a Git folder fails unless its parent directory already exists.
        w.workspace.mkdirs(str(repo_dir.parent))
        body = {"url": GIT_URL, "provider": "gitHub", "path": REPO_PATH, "branch": BRANCH}
        if GIT_CREDENTIAL_ID:
            body["git_credential_id"] = int(GIT_CREDENTIAL_ID)
        created = api.do("POST", "/api/2.0/repos", body=body)
        print(f"cloned {REPO_PATH} @ {BRANCH}")
        return created.get("head_commit_id", "")

    # --- Auto-detect: Git CLI or Repos PATCH API ---
    # CLI-enabled Git folders (common on serverless) are invisible to the
    # Repos API, so we probe for a .git directory first and pick the
    # matching strategy.
    if _has_git_cli(repo_dir):
        _git(repo_dir, "fetch", "origin")
        _git(repo_dir, "checkout", BRANCH)
        _git(repo_dir, "reset", "--hard", f"origin/{BRANCH}")
        sha = _git(repo_dir, "rev-parse", "HEAD")
        print(f"pulled {REPO_PATH} @ {BRANCH}  (git cli)")
        return sha

    # Repos PATCH API: works for standard (non-CLI) Git folders.
    existing = next(
        (r for r in w.repos.list(path_prefix=REPO_PATH) if r.path == REPO_PATH),
        None,
    )
    if existing is None:
        raise RuntimeError(
            f"Repo at {REPO_PATH} is invisible to both Git CLI and the "
            "Repos API \u2014 cannot switch branch."
        )
    updated = api.do("PATCH", f"/api/2.0/repos/{existing.id}", body={"branch": BRANCH})
    print(f"pulled {REPO_PATH} @ {BRANCH}  (repos api)")
    return updated.get("head_commit_id", "")


COMMIT_SHA = checkout_repo()
print(f"head   {COMMIT_SHA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Ensure the target schema exists
# MAGIC
# MAGIC A missing catalog is an operator error, not something to fix silently — it
# MAGIC binds a storage root and carries governance decisions. Schemas we create.

# COMMAND ----------

w.catalogs.get(CATALOG)  # raises NotFound if the operator hasn't created/granted it

try:
    w.schemas.get(f"{CATALOG}.{SCHEMA}")
    print(f"schema {CATALOG}.{SCHEMA} exists")
except NotFound:
    w.schemas.create(name=SCHEMA, catalog_name=CATALOG)
    w.schemas.get(f"{CATALOG}.{SCHEMA}")  # re-read: create can be silently denied
    print(f"schema {CATALOG}.{SCHEMA} created")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Discover plugins, then their skills
# MAGIC
# MAGIC A plugin's `source` is relative to the **marketplace root** — the parent of
# MAGIC `.claude-plugin/`, not `.claude-plugin/` itself. So
# MAGIC `team-a/.claude-plugin/marketplace.json` with `source: "./analytics/.claude"`
# MAGIC resolves to `team-a/analytics/.claude`, whose skills are at
# MAGIC `.../.claude/skills/<skill>/SKILL.md`.
# MAGIC
# MAGIC `source` comes in two forms. A plain string is a marketplace-relative path. An
# MAGIC object (`{"source": "git-subdir"|"github", "path": ...}`) points at a subdirectory
# MAGIC of a repo; when that repo is the one already checked out, its `path` is relative to
# MAGIC the repo root and resolves locally. An object naming a *different* repo would need
# MAGIC a second clone, which this notebook does not do, so those are skipped.
# MAGIC
# MAGIC Skill files are read with ordinary `pathlib` calls against the `/Workspace` path,
# MAGIC which works the same on classic and serverless compute.

# COMMAND ----------

@dataclass(frozen=True)
class DiscoveredSkill:
    leaf: str
    dir: Path


@dataclass
class AuditRow:
    full_name: str
    leaf_name: str
    action: str
    bundle_hash: str = ""
    skill_dir: str = ""
    error: str = ""


audit_rows: list[AuditRow] = []


def record(action: str, leaf: str, skill_dir: str = "", bundle_hash: str = "", error: str = "") -> None:
    audit_rows.append(
        AuditRow(
            full_name=f"{CATALOG}.{SCHEMA}.{leaf}" if leaf else "",
            leaf_name=leaf,
            action=action,
            bundle_hash=bundle_hash,
            skill_dir=skill_dir,
            error=error,
        )
    )


def discover_skills_from_repo() -> dict[str, DiscoveredSkill]:
    """Discovers skills from a flat `skills/` folder at the repo root.

    Expects the layout:
        <repo>/skills/<skill-name>/SKILL.md

    Returns a dict mapping each publishable skill leaf name to its DiscoveredSkill.
    """
    skills_root = Path(REPO_PATH) / "skills"
    winners: dict[str, DiscoveredSkill] = {}

    if not skills_root.is_dir():
        print(f"WARNING: no skills/ directory found at {skills_root}")
        return winners

    for skill_dir in sorted(d for d in skills_root.iterdir() if d.is_dir()):
        leaf = skill_dir.name
        context = {"skill_dir": str(skill_dir)}
        if not (skill_dir / "SKILL.md").is_file():
            record("skipped_no_skill_md", leaf, **context)
        elif not SKILL_LEAF_PATTERN.match(leaf):
            record("skipped_invalid_name", leaf, **context, error=f"'{leaf}' fails {SKILL_LEAF_PATTERN.pattern}")
        elif leaf in winners:
            record("skipped_name_collision", leaf, **context, error=f"already published from {winners[leaf].dir}")
        else:
            winners[leaf] = DiscoveredSkill(leaf, skill_dir)

    return winners


skills = discover_skills_from_repo()

print(f"Found {len(skills)} publishable skill(s).")
for leaf in sorted(skills):
    print(f"  skill  {leaf}  ({skills[leaf].dir})")
for row in audit_rows:
    print(f"  {row.action}  {row.leaf_name or row.skill_dir}: {row.error}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Compare against the last published bundle hash
# MAGIC
# MAGIC A published skill does not carry a content hash you can compare against, so this
# MAGIC notebook tracks changes itself: hash each bundle locally and compare it with the
# MAGIC most recent audit row for that skill. Skills whose hash is unchanged are skipped,
# MAGIC so a scheduled run re-uploads only what actually changed in the repo.

# COMMAND ----------

def read_bundle(skill_dir: Path) -> dict[str, bytes]:
    return {str(f.relative_to(skill_dir)): f.read_bytes() for f in sorted(skill_dir.rglob("*")) if f.is_file()}


def bundle_hash(bundle: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for rel_path in sorted(bundle):
        digest.update(rel_path.encode())
        digest.update(bundle[rel_path])
    return digest.hexdigest()


def last_published_hashes() -> dict[str, str]:
    if not spark.catalog.tableExists(AUDIT_TABLE_SQL):
        return {}
    rows = spark.sql(
        f"""
        SELECT full_name, bundle_hash FROM {AUDIT_TABLE_SQL}
        WHERE action IN ('created', 'updated')
        QUALIFY row_number() OVER (PARTITION BY full_name ORDER BY event_time DESC) = 1
        """
    ).collect()
    return {r.full_name: r.bundle_hash for r in rows}


published_hashes = last_published_hashes()
bundles = {leaf: read_bundle(s.dir) for leaf, s in skills.items()}
hashes = {leaf: bundle_hash(b) for leaf, b in bundles.items()}

changed = sorted(leaf for leaf, h in hashes.items() if published_hashes.get(f"{CATALOG}.{SCHEMA}.{leaf}") != h)
for leaf in sorted(set(hashes) - set(changed)):
    skill = skills[leaf]
    record("skipped_unchanged", leaf, leaf, str(skill.dir), hashes[leaf])

print(f"{len(changed)} changed, {len(hashes) - len(changed)} unchanged")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Publish the changed skills
# MAGIC
# MAGIC Each changed skill takes three steps: create the skill (an "already exists" error
# MAGIC just means this is a re-publish), upload every file in its bundle, then finalize.
# MAGIC Finalizing is what reads the uploaded `SKILL.md` and records its frontmatter, so
# MAGIC `name:` must match the skill's directory name and `description:` must be at most
# MAGIC 1024 bytes.
# MAGIC
# MAGIC Failures are contained per skill: a skill that fails is recorded and the run moves
# MAGIC on, so one malformed bundle cannot block the rest of the repo.

# COMMAND ----------

def create_skill(leaf: str) -> str:
    """Creates the skill entity, returning the audit action. Re-publishes are expected."""
    try:
        api.do("POST", SKILLS_API, query={"parent": f"schemas/{CATALOG}.{SCHEMA}", "skill_id": leaf}, body={})
        return "created"
    except AlreadyExists:
        return "updated"


def upload_bundle(leaf: str, bundle: dict[str, bytes]) -> None:
    for rel_path, content in bundle.items():
        api.do(
            "PUT",
            f"{FILES_API}/Skills/{CATALOG}/{SCHEMA}/{leaf}/{rel_path}",
            headers={"Content-Type": "application/octet-stream"},
            data=content,
        )


def finalize_skill(leaf: str) -> None:
    api.do("POST", f"{SKILLS_API}/{CATALOG}.{SCHEMA}.{leaf}/finalize")


for leaf in changed:
    skill = skills[leaf]
    try:
        action = create_skill(leaf)
        upload_bundle(leaf, bundles[leaf])
        finalize_skill(leaf)
        record(action, leaf, leaf, str(skill.dir), hashes[leaf])
        print(f"  {action:8} {leaf}  ({skill.dir})")
    # Deliberately broad: any failure across create/upload/finalize must stay contained to
    # this skill, so one malformed bundle can't abort the rest of the repo's sync.
    except Exception as e:
        record("error", leaf, leaf, str(skill.dir), hashes[leaf], error=str(e))
        print(f"  {'error':8} {leaf}  ({skill.dir}): {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Append to the audit table
# MAGIC
# MAGIC Rows are only ever appended, so the table keeps the full history of what each run
# MAGIC did. The newest row per skill is what the next run compares against.

# COMMAND ----------

audit_df = (
    spark.createDataFrame([vars(r) for r in audit_rows])
    .withColumn("sync_run_id", lit(SYNC_RUN_ID))
    .withColumn("event_time", current_timestamp())
    .withColumn("repo_url", lit(GIT_URL))
    .withColumn("commit_sha", lit(COMMIT_SHA))
    .withColumn("run_by", lit(RUN_BY))
    .select(
        "sync_run_id",
        "event_time",
        "repo_url",
        "commit_sha",
        "full_name",
        "leaf_name",
        "skill_dir",
        "action",
        "bundle_hash",
        "error",
        "run_by",
    )
)
audit_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(AUDIT_TABLE_SQL)

# COMMAND ----------

display(spark.table(AUDIT_TABLE_SQL))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC The run fails if any skill failed to publish, so a scheduled job shows up as
# MAGIC failed even when the other skills went through. Skipped skills are the normal
# MAGIC steady state, not failures.

# COMMAND ----------

counts = Counter(r.action for r in audit_rows)
for action, count in sorted(counts.items()):
    print(f"  {action:24} {count}")

errors = [r for r in audit_rows if r.action == "error"]
if errors:
    raise RuntimeError(f"{len(errors)} skill(s) failed to publish: {', '.join(r.leaf_name for r in errors)}")

print(f"\nSynced {CATALOG}.{SCHEMA} to {GIT_URL} @ {COMMIT_SHA[:8]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Schedule it
# MAGIC
# MAGIC To keep the schema tracking your repo, add this notebook as a single task in a
# MAGIC job, pass the widget values as job parameters, and give the job a schedule.
# MAGIC
# MAGIC Two things to keep in mind:
# MAGIC
# MAGIC - Because a run can start before your push is visible to the Git folder, a run
# MAGIC   triggered directly by a push may not include that commit. The following run
# MAGIC   picks it up.
# MAGIC - Nothing is ever deleted. A skill removed from the repo stays in the schema
# MAGIC   until you drop it yourself.