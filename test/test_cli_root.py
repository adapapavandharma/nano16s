"""Where the CLI looks for the workflow, across every way it can be invoked.

`bin/nano16s` has to find workflow/, config/ and test/ from wherever it is run.
They sit one level up in a source checkout and under $PREFIX/share/nano16s in a
packaged install, and either can be reached directly or through a symlink on
PATH -- four combinations.

The version before this decided which layout it was in by testing whether the
script was a symlink, on the assumption that a symlink meant install.sh had
made one. A packaged CLI symlinked onto PATH broke that assumption: it took the
checkout branch, ROOT lost its share/nano16s component, and every path built
from it pointed at a layout that does not exist. Nothing warned; the run simply
reported a missing file somewhere plausible.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "nano16s"

pytestmark = pytest.mark.skipif(not CLI.exists(), reason="CLI not present")


def layouts(tmp_path):
    """A checkout-shaped tree and a package-shaped tree, plus symlinks to both."""
    chk, pkg, bin_ = tmp_path / "chk", tmp_path / "pkg", tmp_path / "onpath"
    for d in ((chk / "bin"), (chk / "workflow"), (chk / "config"),
              (pkg / "bin"), (pkg / "share/nano16s/workflow"),
              (pkg / "share/nano16s/config"), bin_):
        d.mkdir(parents=True, exist_ok=True)
    for dst in (chk / "bin/nano16s", pkg / "bin/nano16s"):
        dst.write_text(CLI.read_text())
        dst.chmod(0o755)
    (chk / "workflow/Snakefile").write_text("# stand-in\n")
    (pkg / "share/nano16s/workflow/Snakefile").write_text("# stand-in\n")
    (chk / "config/config.yaml").write_text("{}\n")
    (pkg / "share/nano16s/config/config.yaml").write_text("{}\n")
    (bin_ / "chk").symlink_to(chk / "bin/nano16s")
    (bin_ / "pkg").symlink_to(pkg / "bin/nano16s")
    return chk, pkg, bin_


def resolved_root(entry: Path) -> str:
    """The ROOT the CLI derives, read back out of a path it reports."""
    r = subprocess.run([str(entry), "test"], capture_output=True, text=True)
    text = r.stdout + r.stderr
    marker = "/test/demo/fastq_pass"
    assert marker in text, f"unexpected output: {text[:200]}"
    line = next(x for x in text.splitlines() if marker in x)
    return line.split("not found at ")[1].replace(marker, "")


def test_checkout_direct(tmp_path):
    chk, _, _ = layouts(tmp_path)
    assert resolved_root(chk / "bin/nano16s") == str(chk)


def test_checkout_through_a_symlink(tmp_path):
    """What install.sh creates, and the case the old code was written for."""
    chk, _, bin_ = layouts(tmp_path)
    assert resolved_root(bin_ / "chk") == str(chk)


def test_package_direct(tmp_path):
    _, pkg, _ = layouts(tmp_path)
    assert resolved_root(pkg / "bin/nano16s") == str(pkg / "share/nano16s")


def test_package_through_a_symlink(tmp_path):
    """REGRESSION: this one dropped share/nano16s and reported $PREFIX.

    Reachable as soon as the conda recipe is published and anyone runs
    `ln -s "$(which nano16s)" ~/bin/`, or uses an environment-module setup, or
    any package manager that links rather than copies.
    """
    _, pkg, bin_ = layouts(tmp_path)
    assert resolved_root(bin_ / "pkg") == str(pkg / "share/nano16s")


def test_no_workflow_anywhere_says_so(tmp_path):
    """Better than a missing-file error naming a path that never existed."""
    bare = tmp_path / "bare" / "bin"
    bare.mkdir(parents=True)
    cli = bare / "nano16s"
    cli.write_text(CLI.read_text())
    cli.chmod(0o755)
    r = subprocess.run([str(cli), "test"], capture_output=True, text=True)
    assert r.returncode != 0
    assert "cannot find the workflow" in r.stdout + r.stderr
