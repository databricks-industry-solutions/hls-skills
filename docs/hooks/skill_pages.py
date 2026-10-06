"""MkDocs hook: build the skill catalog and one page per skill from skills/*/SKILL.md.

Pages are generated at build time, so the site always matches the skills on the
branch being built and nothing under docs/ has to be kept in sync by hand.
"""

import re
from pathlib import Path

import yaml
from mkdocs.structure.files import File
from repo_links import BRANCH, REPO, absolute_links

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)

_skills = []


def _load_skills():
    skills = []
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        meta = yaml.safe_load(match.group(1)) if match else {}
        body = text[match.end() :] if match else text
        folder = path.parent
        eval_dir = folder / "eval"
        skills.append(
            {
                "folder": folder.name,
                "name": meta.get("name", folder.name),
                "description": " ".join(str(meta.get("description", "")).split()),
                "version": meta.get("version", ""),
                "author": meta.get("author", ""),
                "license": meta.get("license", ""),
                "body": body,
                "has_report": (eval_dir / "eval_report.md").is_file(),
                "has_eval": eval_dir.is_dir() and any(eval_dir.iterdir()),
            }
        )
    return skills


def _eval_link(skill):
    """(label, url) for the skill's evaluation, or None when nothing is committed."""
    if skill["has_report"]:
        return (
            "Report",
            f"{REPO}/blob/{BRANCH}/skills/{skill['folder']}/eval/eval_report.md",
        )
    if skill["has_eval"]:
        return "Evidence", f"{REPO}/tree/{BRANCH}/skills/{skill['folder']}/eval"
    return None


def _summary(description, limit=160):
    first = description.split(". ")[0].rstrip(".")
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first.replace("|", "\\|")


def _skill_page(skill):
    folder = skill["folder"]
    details = " · ".join(
        f"**{label}** {skill[key]}"
        for label, key in (
            ("Version", "version"),
            ("Author", "author"),
            ("License", "license"),
        )
        if skill[key]
    )
    links = [
        f"[Browse on GitHub]({REPO}/tree/{BRANCH}/skills/{folder})",
        f"[Raw SKILL.md]({REPO}/blob/{BRANCH}/skills/{folder}/SKILL.md)",
    ]
    if evaluation := _eval_link(skill):
        links.append(f"[Evaluation {evaluation[0].lower()}]({evaluation[1]})")
    box = f'!!! abstract "Skill details"\n    {details}\n\n    {" · ".join(links)}\n\n'

    body = absolute_links(skill["body"], f"skills/{folder}").lstrip("\n")
    title, _, rest = body.partition("\n")
    if title.startswith("# "):
        rest = rest.lstrip("\n")
        body = f"{title}\n\n{box}{rest}"
    else:
        body = f"# {skill['name']}\n\n{box}{body}"
    description = skill["description"].replace('"', "'")
    return f'---\ndescription: "{description}"\n---\n\n{body}'


def _catalog(skills):
    def eval_cell(skill):
        evaluation = _eval_link(skill)
        return f"[{evaluation[0]}]({evaluation[1]})" if evaluation else "Pending"

    rows = "\n".join(
        f"| [{s['name']}]({s['folder']}.md) | {_summary(s['description'])} | {s['version']} | {eval_cell(s)} |"
        for s in skills
    )
    return (
        "# Skill catalog\n\n"
        "Each skill is a folder with a `SKILL.md` that an agent loads when a task matches its description. "
        "This page is generated from each skill's frontmatter when the site is built.\n\n"
        "| Skill | What it does | Version | Evaluation |\n"
        "|-------|--------------|---------|------------|\n"
        f"{rows}\n\n"
        "**Evaluation:** *Report* links a paired with/without-skill comparison, *Evidence* links benchmark files "
        "without a report yet, and *Pending* means no evaluation has been committed. "
        "See [Evaluation](../evaluation.md).\n"
    )


def on_config(config):
    _skills[:] = _load_skills()
    for i, item in enumerate(config.nav):
        if isinstance(item, dict) and "Skills" in item:
            config.nav[i] = {
                "Skills": ["guide/skills/index.md"]
                + [{s["name"]: f"guide/skills/{s['folder']}.md"} for s in _skills]
            }
    return config


def on_files(files, config):
    files.append(
        File.generated(config, "guide/skills/index.md", content=_catalog(_skills))
    )
    for skill in _skills:
        files.append(
            File.generated(
                config, f"guide/skills/{skill['folder']}.md", content=_skill_page(skill)
            )
        )
    return files
