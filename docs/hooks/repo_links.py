"""Shared by the docs hooks: point relative links in repository Markdown at GitHub.

Markdown pulled into the site from outside docs/ keeps links relative to its own
folder. Those targets are not part of the site, so they must link to GitHub.
"""

import re

REPO = "https://github.com/databricks-industry-solutions/hls-skills"
BRANCH = "main"
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
EXTERNAL = re.compile(r"^([a-z][a-z0-9+.-]*:|#|/)", re.IGNORECASE)


def is_fence(line):
    return line.lstrip().startswith(("```", "~~~"))


def absolute_links(markdown, rel_dir=""):
    """Rewrite relative links in `markdown`, which lives in `rel_dir` of the repository.

    Links go to the GitHub file view; images go to the raw file so they render.
    Fenced code is left alone.
    """
    prefix = f"{rel_dir.strip('/')}/" if rel_dir.strip("/") else ""

    def rewrite(m):
        target = m.group(2)
        if EXTERNAL.match(target):
            return m.group(0)
        view = "raw" if m.group(1).startswith("!") else "blob"
        url = f"{REPO}/{view}/{BRANCH}/{prefix}{target.removeprefix('./')}"
        return f"{m.group(1)}{url}{m.group(3)}"

    lines, fenced = [], False
    for line in markdown.splitlines(keepends=True):
        if is_fence(line):
            fenced = not fenced
        elif not fenced:
            line = LINK.sub(rewrite, line)
        lines.append(line)
    return "".join(lines)
