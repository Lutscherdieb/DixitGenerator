"""Fail if a print measurement has been typed outside ``dixitgen.spec``.

Run it after any change touching geometry, layout or export:

    python tools/check_geometry_literals.py      # exit 0 means clean

How it works, and why it works this way
---------------------------------------
It **asks the spec module for the numbers** and then greps for each one,
**unit-anchored** -- ``80mm``, ``945px``, ``226.77pt``, never a bare ``80``.
Deriving the list is the whole point: a measurement added to ``CardFormat`` or
``SheetLayout`` is covered the day it exists, with no edit here.

Do not replace this with a hand-written grep over specific numbers.  That form
can only catch drift somebody already thought of, and in the sibling project
``CardGenerator`` it is exactly how ``--road-width: 214px`` sat in a stylesheet
as a second source of truth while the check stayed green -- ``214`` had never
been added to the hardcoded list.

What it deliberately does not scan
----------------------------------
``src/dixitgen/spec/``   the owner of the numbers; literals belong here
``tests/``               the verify gate asserts against **published** figures
                         (A4 at 595.276pt, an MTG card at 178.583pt).  Those
                         literals are the cross-check itself -- deriving them
                         from the module under test would make the gate
                         unfalsifiable, which is the failure PROJECT.md names.
``docs/``, ``*.md``      prose explains the numbers; that is its job.

Small values are skipped as indistinguishable from ordinary styling -- see
``MIN_DISTINCTIVE``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dixitgen.spec import (  # noqa: E402
    A4,
    CARD_FORMATS,
    MM_PER_INCH,
    PRESS_FORMATS,
    PRINT_DPI,
    PT_PER_INCH,
    SHEET,
)

#: Below this, a measurement is indistinguishable from ordinary styling and
#: matching it produces noise rather than findings.  The bleed (3mm), the crop
#: mark (4mm), its gap (1.5mm) and the unprintable edge (5mm) all fall here:
#: a stylesheet saying ``padding: 4px`` is not a second source of truth for the
#: crop-mark length, and flagging it would train people to ignore this tool.
#: The sibling project learned the same thing at 30 (its 16px bleed matched
#: three honest ``font-size: 16px`` rules).
MIN_DISTINCTIVE = 20.0

#: Which files can hold a second copy of a measurement in a way that matters.
SCAN_GLOBS = ("src/**/*.py", "tools/**/*.py", "web/**/*.js", "web/**/*.css",
              "web/**/*.html")

#: Paths excluded, each for the reason given in this module's docstring.
EXCLUDE_PREFIXES = ("src/dixitgen/spec/", "tests/", "docs/")


def measurements() -> Dict[str, List[Tuple[float, str]]]:
    """Every number the spec owns, grouped by the unit it is written in.

    Derived, never enumerated, in both directions: the *fields* come from
    reading the spec objects, and the *objects* come from ``CARD_FORMATS`` and
    ``PRESS_FORMATS`` rather than being named one by one.  Register a new card
    or press format and its measurements are covered on the same commit.

    This was not always true.  Until 2026-09-23 the card row read ``DIXIT``
    directly, so adding ``TAROT_MPC`` and the press profiles left ten new
    measurements -- 897px and 1017px among them -- entirely unwatched while
    this tool still printed "clean".  A checker that enumerates what it checks
    can only ever cover what somebody remembered to add.
    """
    mm: List[Tuple[float, str]] = [
        (A4.w_mm, "paper width"),
        (A4.h_mm, "paper height"),
        (SHEET.block_w_mm, "block width"),
        (SHEET.block_h_mm, "block height"),
        (SHEET.margin_x_mm, "horizontal margin"),
        (SHEET.margin_y_mm, "vertical margin"),
        (SHEET.outer_bleed_mm, "outer bleed"),
        (SHEET.mark_len_mm, "crop mark length"),
        (SHEET.mark_gap_mm, "crop mark gap"),
        (SHEET.unprintable_margin_mm, "unprintable margin"),
        (MM_PER_INCH, "millimetres per inch"),
    ]
    px: List[Tuple[float, str]] = []
    pt: List[Tuple[float, str]] = [
        (A4.w_pt, "paper width in points"),
        (A4.h_pt, "paper height in points"),
        (PT_PER_INCH, "points per inch"),
    ]

    for card in CARD_FORMATS.values():
        mm.append((card.trim_w_mm, "{} trim width".format(card.id)))
        mm.append((card.trim_h_mm, "{} trim height".format(card.id)))
        px.append((card.trim_w_px, "{} width in pixels".format(card.id)))
        px.append((card.trim_h_px, "{} height in pixels".format(card.id)))
        pt.append((card.trim_w_pt, "{} width in points".format(card.id)))
        pt.append((card.trim_h_pt, "{} height in points".format(card.id)))

    for press in PRESS_FORMATS.values():
        mm.append((press.bleed_mm, "{} bleed".format(press.id)))
        mm.append((press.bled_w_mm, "{} bled width".format(press.id)))
        mm.append((press.bled_h_mm, "{} bled height".format(press.id)))
        px.append((press.bleed_px, "{} bleed in pixels".format(press.id)))
        px.append((press.upload_w_px, "{} upload width".format(press.id)))
        px.append((press.upload_h_px, "{} upload height".format(press.id)))

    dpi: List[Tuple[float, str]] = [(PRINT_DPI, "print resolution")]
    return {"mm": mm, "px": px, "pt": pt, "dpi": dpi}


def number_patterns(value: float) -> Set[str]:
    """The ways this value could plausibly be typed by hand.

    ``80`` and ``80.0``; ``226.771653...`` also as ``226.77`` and ``226.772``,
    because a person copying a derived figure rounds it.
    """
    out = {"{:g}".format(value)}
    if float(value).is_integer():
        out.add("{:.1f}".format(value))
    else:
        for places in (1, 2, 3, 4):
            out.add("{:.{}f}".format(value, places).rstrip("0").rstrip("."))
            out.add("{:.{}f}".format(value, places))
    return {p for p in out if p}


def _blank(line: str) -> str:
    """Same length, no content -- so line numbers survive the stripping."""
    return " " * len(line)


def code_lines(text: str, suffix: str) -> List[str]:
    """``text`` with comments and docstrings blanked out, line numbers intact.

    A measurement written in a **comment** is prose explaining the rule, not a
    second source of truth -- this module's own docstring says ``80mm`` three
    times and must not report itself.  A measurement written in **code**,
    including a string literal a template reads, is exactly what this tool is
    for, so strings are left alone outside Python docstrings.
    """
    lines = text.splitlines()

    if suffix == ".py":
        import ast
        import io
        import tokenize

        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type == tokenize.COMMENT:
                    row = token.start[0] - 1
                    lines[row] = lines[row][: token.start[1]] + _blank(
                        lines[row][token.start[1] :]
                    )
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    continue
                body = getattr(node, "body", None)
                if not body:
                    continue
                first = body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    for row in range(first.lineno - 1, (first.end_lineno or 0)):
                        if 0 <= row < len(lines):
                            lines[row] = _blank(lines[row])
        except (SyntaxError, tokenize.TokenError):
            # An unparseable source is a different problem; scan it raw rather
            # than silently skipping a file that might hold a duplicate.
            return text.splitlines()
        return lines

    # JS / CSS / HTML: block comments, then line comments.
    joined = "\n".join(lines)
    joined = re.sub(
        r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), joined, flags=re.S
    )
    joined = re.sub(
        r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), joined, flags=re.S
    )
    out = []
    for line in joined.splitlines():
        # `//` after a colon is a URL scheme, not a comment.
        match = re.search(r"(?<!:)//", line)
        out.append(line[: match.start()] + _blank(line[match.start() :]) if match else line)
    return out


def scan() -> List[str]:
    findings: List[str] = []
    by_unit = measurements()

    files = []
    for pattern in SCAN_GLOBS:
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if any(rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            files.append((rel, code_lines(text, path.suffix)))

    for unit, entries in by_unit.items():
        for value, what in entries:
            if abs(value) < MIN_DISTINCTIVE:
                continue
            for literal in number_patterns(value):
                # Unit-anchored: the number must be immediately followed by the
                # unit, optionally with a space.  A bare 80 is not a finding.
                pattern = re.compile(
                    r"(?<![\w.]){}\s*{}\b".format(re.escape(literal), unit),
                    re.IGNORECASE,
                )
                for rel, lines in files:
                    for lineno, line in enumerate(lines, 1):
                        if pattern.search(line):
                            findings.append(
                                "{}:{}: {!r} -- {} is {}{}, owned by "
                                "dixitgen.spec. Ask the spec object for it.\n"
                                "    {}".format(
                                    rel,
                                    lineno,
                                    literal + unit,
                                    what,
                                    "{:g}".format(value),
                                    unit,
                                    line.strip(),
                                )
                            )
    return findings


def main() -> int:
    findings = scan()
    counted = sum(
        1
        for entries in measurements().values()
        for value, _ in entries
        if abs(value) >= MIN_DISTINCTIVE
    )
    print(
        "checked {} derived measurements (of {} total; the rest are below the "
        "{:g} distinctiveness floor)".format(
            counted,
            sum(len(v) for v in measurements().values()),
            MIN_DISTINCTIVE,
        )
    )
    if not findings:
        print("clean: no print measurement is typed outside dixitgen.spec")
        return 0
    print("\n{} duplicated measurement(s):\n".format(len(findings)))
    for finding in findings:
        print(finding)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
