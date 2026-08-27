"""Portability checks on the Snakemake rules' shell bodies.

Snakemake prepends `set -euo pipefail` to every shell body, and on macOS the
shell it runs them with is /bin/bash, which is bash 3.2. Bash before 4.4
treats `"${arr[@]}"` as an unset variable when the array is empty, so under
`set -u` the expansion aborts the rule with `arr[@]: unbound variable`.

That is invisible on Linux, where every bash is 4.4 or newer, and CI runs the
pipeline on Linux only — the macOS jobs install the CLI and build the DAG but
never execute a rule. So this class of bug reaches macOS users without any
test failing first, which is what happened with the thresholded-table loop in
`rule emu`: it failed for every barcode that did not trigger Emu's abundance
threshold, which is the ordinary case.

These are static checks over the rule files. They need no shell, no macOS and
no pipeline run.

Run with:
    python -m pytest test/ -v
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RULES = sorted((ROOT / "workflow" / "rules").glob("*.smk"))

# `"${NAME[@]}"` / `"${NAME[*]}"` as Snakemake writes them, i.e. brace-doubled.
EXPANSION = re.compile(r'"\$\{\{(\w+)\[[@*]\]\}\}"')
# A guard on that same array: `"${#NAME[@]}"` anywhere before the expansion.
GUARD = r'"\$\{{\{{#{name}\[@\]\}}\}}"'


def strip_comments(body: str) -> str:
    """Drop whole-line `#` comments, keeping line numbering intact.

    Only lines whose first non-space character is `#`. An inline `#` cannot be
    assumed to start a comment — `"${#ARR[@]}"` is the very construct these
    checks look for.
    """
    return "\n".join(
        "" if line.lstrip().startswith("#") else line
        for line in body.split("\n")
    )


def shell_bodies(path: Path):
    """(rule_name, body) for every shell block in a rule file, comments removed.

    Comments are stripped because they discuss these constructs by name — this
    file's own fix is explained in a comment quoting the pattern it fixes.
    """
    text = path.read_text()
    out = []
    for m in re.finditer(r'^rule (\w+):', text, re.M):
        start = m.end()
        nxt = re.search(r'^rule \w+:', text[start:], re.M)
        chunk = text[start:start + nxt.start()] if nxt else text[start:]
        s = re.search(r'\n    shell:\s*\n', chunk)
        if s:
            out.append((m.group(1), strip_comments(chunk[s.end():])))
    return out


def test_rule_files_are_present():
    """A refactor that moves the rules must not silently empty this suite."""
    assert RULES, "no .smk files found — did the rules move?"
    assert any(shell_bodies(p) for p in RULES), "no shell bodies parsed"


@pytest.mark.parametrize("path", RULES, ids=lambda p: p.name)
def test_array_expansions_are_guarded(path):
    """REGRESSION: `for t in "${THRESH[@]}"` broke every macOS run.

    An array built from a glob under `shopt -s nullglob` is empty whenever the
    glob matches nothing, which for the thresholded table is the normal case.
    Guard on `"${#NAME[@]}"` before expanding, or the rule dies on bash 3.2.
    """
    problems = []
    for rule, body in shell_bodies(path):
        for m in EXPANSION.finditer(body):
            name = m.group(1)
            preceding = body[:m.start()]
            if not re.search(GUARD.format(name=re.escape(name)), preceding):
                line = body[:m.start()].count("\n") + 1
                problems.append(
                    f"{path.name}: rule {rule}, ~line {line} of the shell body: "
                    f'"${{{name}[@]}}" expanded with no preceding '
                    f'"${{#{name}[@]}}" check'
                )
    assert not problems, "unguarded array expansion:\n  " + "\n  ".join(problems)
