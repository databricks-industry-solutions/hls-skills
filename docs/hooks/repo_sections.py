"""MkDocs hook: copy a repository Markdown file, or one section of it, into a docs page.

A line in a page under docs/ such as

    <!-- include: README.md#Setup -->

is replaced at build time by the text under the `Setup` heading of README.md, up
to the next heading of the same or a higher level. Without `#Heading` the whole
file is copied, minus its leading `# Title` because the page has its own:

    <!-- include: CONTRIBUTING.md omit="Contributor License Agreement (CLA)" -->

The source file stays the only copy, so edit it there, not on the site.

- The path is relative to the repository root. Headings are matched without
  case, backticks, or link URLs, so `Optional: Register and sync the skills to
  Unity Gateway` matches a heading that links "Unity Gateway".
- `omit="Heading"` leaves out that heading and the text under it. Repeat it to
  leave out more than one section.
- `replace="Heading=Markdown"` keeps the heading but swaps the text under it for
  the given Markdown, for example a link to the page that already shows it:
  `replace="3. Evaluate with and without skill=See [Evaluation](evaluation.md)."`
  Links in that Markdown are relative to the page, not the source file.
- Headings are shifted so the copied text's top level is `##`. Add `level=N` for
  another level: `<!-- include: README.md#Setup level=3 -->`.
- Relative links point at GitHub, because their targets are not on the site.
- GitHub alerts (`> [!NOTE]`, `> [!WARNING]`, ...) become admonitions, so the
  same box renders on GitHub and on the site.
- A missing file, a missing or repeated heading, or nothing left to copy fails
  the build.
"""

import re
from pathlib import Path

from repo_links import absolute_links, is_fence, nest_lists

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER = re.compile(
    r"^<!--\s*include:\s*(?P<path>[^#\s]+)(?:#(?P<heading>.+?))?"
    r'(?P<options>(?:\s+(?:level=[1-6]|(?:omit|replace)="[^"]+"))*)\s*-->\s*$'
)
OPTION = re.compile(
    r'level=(?P<level>[1-6])|omit="(?P<omit>[^"]+)"|replace="(?P<replace>[^"]+)"'
)
HEADING = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ALERT = re.compile(r"^>\s*\[!(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$", re.IGNORECASE)
ADMONITIONS = {
    "NOTE": "note",
    "TIP": "tip",
    "IMPORTANT": 'info "Important"',
    "WARNING": "warning",
    "CAUTION": 'danger "Caution"',
}

_sources = set()


class SectionError(ValueError):
    pass


def _normalize(heading):
    return " ".join(MD_LINK.sub(r"\1", heading).replace("`", "").split()).casefold()


def _headings(lines):
    """(index, level, text) for each ATX heading outside fenced code."""
    fenced = False
    for i, line in enumerate(lines):
        if is_fence(line):
            fenced = not fenced
        elif not fenced and (m := HEADING.match(line)):
            yield i, len(m["hashes"]), m["text"]


def _span(lines, heading, source):
    """Line range of `heading` and the text under it, up to the next heading of the same or a higher level."""
    headings = list(_headings(lines))
    want = _normalize(heading)
    matches = [(i, level) for i, level, title in headings if _normalize(title) == want]
    if not matches:
        raise SectionError(f"{source}: no heading '{heading}'")
    if len(matches) > 1:
        raise SectionError(f"{source}: heading '{heading}' appears {len(matches)} times")
    start, level = matches[0]
    end = next((i for i, lvl, _ in headings if i > start and lvl <= level), len(lines))
    return start, end


def _nonempty(text, what, source):
    text = text.strip("\n")
    if not text.strip():
        raise SectionError(f"{source}: {what} is empty")
    return text


def extract_section(text, heading, source="source"):
    """Text under `heading`, without the heading line itself."""
    lines = text.splitlines()
    start, end = _span(lines, heading, source)
    return _nonempty("\n".join(lines[start + 1 : end]), f"section '{heading}'", source)


def omit_section(text, heading, source="source"):
    """`text` without `heading` and the text under it."""
    lines = text.splitlines()
    start, end = _span(lines, heading, source)
    return "\n".join(lines[:start] + lines[end:])


def replace_section(text, heading, body, source="source"):
    """`text` with the text under `heading` swapped for `body`; the heading stays."""
    lines = text.splitlines()
    start, end = _span(lines, heading, source)
    return "\n".join(lines[: start + 1] + ["", body, ""] + lines[end:])


def without_title(text):
    """`text` without a leading `# Title` line."""
    lines = text.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None and re.match(r"#[ \t]", lines[first]):
        del lines[first]
    return "\n".join(lines)


def shift_headings(markdown, level):
    """Shift headings outside fenced code so the shallowest one is at `level`."""
    lines = markdown.splitlines()
    found = list(_headings(lines))
    if not found:
        return markdown
    delta = level - min(lvl for _, lvl, _ in found)
    for i, lvl, text in found:
        lines[i] = f"{'#' * min(max(lvl + delta, 1), 6)} {text}"
    return "\n".join(lines)


def alerts_to_admonitions(markdown):
    """Turn GitHub alert blockquotes outside fenced code into Material admonitions."""
    lines, out, fenced, i = markdown.splitlines(), [], False, 0
    while i < len(lines):
        line = lines[i]
        if is_fence(line):
            fenced = not fenced
        elif not fenced and (m := ALERT.match(line)):
            out.append(f"!!! {ADMONITIONS[m['kind'].upper()]}")
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                body = lines[i][1:].removeprefix(" ")
                out.append(f"    {body}" if body.strip() else "")
                i += 1
            if i < len(lines) and lines[i].strip():
                out.append("")
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _source(rel_path):
    path = (REPO_ROOT / rel_path).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise SectionError(f"{rel_path}: outside the repository")
    if not path.is_file():
        raise SectionError(f"{rel_path}: file not found")
    return path


def _include(m):
    """(markdown, source path) for one include marker match."""
    path, source = _source(m["path"]), m["path"]
    level, omit, replace = 2, [], []
    for option in OPTION.finditer(m["options"]):
        if option["level"]:
            level = int(option["level"])
        elif option["omit"]:
            omit.append(option["omit"])
        else:
            heading, _, body = option["replace"].partition("=")
            if not body.strip():
                raise SectionError(f"{source}: replace=\"{heading}\" needs '=Markdown'")
            replace.append((heading.strip(), body.strip()))

    text = path.read_text(encoding="utf-8")
    text = extract_section(text, m["heading"], source) if m["heading"] else without_title(text)
    for heading in omit:
        text = omit_section(text, heading, source)
    text = shift_headings(_nonempty(text, "included text", source), level)
    text = alerts_to_admonitions(text)
    rel_dir = path.parent.relative_to(REPO_ROOT).as_posix()
    text = nest_lists(absolute_links(text, "" if rel_dir == "." else rel_dir))
    for heading, body in replace:
        text = replace_section(text, heading, body, source)
    return text, path


def expand_includes(markdown):
    """Replace every include marker outside fenced code; return (markdown, source paths)."""
    lines, used, fenced = [], set(), False
    for line in markdown.splitlines():
        if is_fence(line):
            fenced = not fenced
        elif not fenced and (m := MARKER.match(line)):
            line, path = _include(m)
            used.add(path)
        lines.append(line)
    tail = "\n" if markdown.endswith("\n") else ""
    return "\n".join(lines) + tail, used


def on_page_markdown(markdown, page, **kwargs):
    # Imported here so tests/ can load this module without MkDocs installed.
    from mkdocs.exceptions import PluginError

    try:
        markdown, used = expand_includes(markdown)
    except SectionError as e:
        raise PluginError(f"{page.file.src_uri}: {e}") from e
    _sources.update(used)
    return markdown


def on_serve(server, **kwargs):
    for path in sorted(_sources):
        server.watch(str(path))
    return server
