"""Shared by the docs hooks: make repository Markdown render on the site as on GitHub.

Markdown pulled into the site from outside docs/ keeps links relative to its own
folder. Those targets are not part of the site, so they must link to GitHub.
Nested lists also need wider indentation for MkDocs than GitHub requires.
"""

import re

REPO = "https://github.com/databricks-industry-solutions/hls-skills"
BRANCH = "main"
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
EXTERNAL = re.compile(r"^([a-z][a-z0-9+.-]*:|#|/)", re.IGNORECASE)
LIST_ITEM = re.compile(r"( *)([-*+]|\d+[.)]) {1,4}(?=\S)")


def is_fence(line):
    return line.lstrip().startswith(("```", "~~~"))


def _shift(line, by):
    if by >= 0:
        return " " * by + line
    return line[min(-by, len(line) - len(line.lstrip(" "))) :]


def nest_lists(markdown):
    """Indent nested list items and their text four spaces per level.

    GitHub nests a line under a list item when it is indented as far as the item's
    text, which is three spaces under `1.`. Python-Markdown, which MkDocs uses,
    needs four, so a `   - How to avoid` line under `1.` would become an item of
    its own. Fenced code inside an item moves with it and is otherwise unchanged.
    """
    lines, items, by, fenced = [], [], 0, False
    for line in markdown.splitlines(keepends=True):
        if fenced:
            fenced = not is_fence(line)
            lines.append(_shift(line, by))
            continue
        if not line.strip():
            lines.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        # Each open item is (text column in the source, text column on the site).
        while items and indent < items[-1][0]:
            items.pop()
        if item := LIST_ITEM.match(line):
            by = 4 * len(items) - indent
            items.append((item.end(), 4 * len(items) + 4))
        else:
            by = items[-1][1] - items[-1][0] if items else 0
            fenced = is_fence(line)
        lines.append(_shift(line, by))
    return "".join(lines)


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
