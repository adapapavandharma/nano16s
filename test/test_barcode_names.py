"""Barcode directory names, and barcodes with nothing in them.

Both were run-ending. A directory named `barcode02 (copy)` -- what Finder and
Explorer produce when you duplicate a folder -- was picked up as a sample and
killed the workflow in `merge`, on an unquoted path, with an error quoting the
rule's own comment text rather than naming the directory. A directory holding
no FASTQ exited 1, and since `emu_combine` depends on every sample that threw
away the combined tables and both reports for every other barcode in the run.

These drive Snakemake directly rather than the CLI, so they need no database
and no installed pipeline: a dry run resolves the DAG, which is where sample
discovery and the wildcard constraints live.
"""

import gzip
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAKEFILE = ROOT / "workflow" / "Snakefile"
CONFIGFILE = ROOT / "config" / "config.yaml"

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "snakemake"], capture_output=True).returncode != 0,
    reason="snakemake not installed",
)


def make_barcode(root: Path, name: str, *, reads: int = 2) -> Path:
    """A barcode directory holding one gzipped FASTQ, or none at all."""
    d = root / name
    d.mkdir(parents=True)
    if reads:
        body = "".join(
            f"@r{i}\nACGT\n+\n!!!!\n" for i in range(reads)
        )
        with gzip.open(d / f"{name}_0.fastq.gz", "wt") as fh:
            fh.write(body)
    return d


def dry_run(tmp_path, inputs: Path):
    return subprocess.run(
        [sys.executable, "-m", "snakemake",
         "--snakefile", str(SNAKEFILE), "--configfile", str(CONFIGFILE),
         "--cores", "1", "-n", "--config",
         f"input_dir={inputs}", f"output_dir={tmp_path / 'out'}",
         f"emu_db={tmp_path / 'db'}"],
        capture_output=True, text=True, cwd=tmp_path,
    )


def test_a_name_the_shell_cannot_carry_is_refused_by_name(tmp_path):
    """REGRESSION: `barcode02 (copy)` died in merge on an unquoted path."""
    inputs = tmp_path / "fastq_pass"
    make_barcode(inputs, "barcode01")
    make_barcode(inputs, "barcode02 (copy)")

    r = dry_run(tmp_path, inputs)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    # The directory has to be named: the point is that the user can act on it.
    assert "barcode02 (copy)" in out
    assert "Rename them" in out
    # And it must not be the old failure, which surfaced deep inside a rule.
    assert "cannot stat" not in out


def test_ordinary_names_still_pass(tmp_path):
    """Guards the check above: it must not reject the names people use."""
    inputs = tmp_path / "fastq_pass"
    for name in ("barcode01", "barcode_07", "barcode-12", "barcode.3", "BARCODE99"):
        make_barcode(inputs, name)

    r = dry_run(tmp_path, inputs)
    assert r.returncode == 0, r.stdout + r.stderr


def run_target(tmp_path, inputs: Path, target: Path):
    """Actually execute the rules needed for one file, not just plan them."""
    return subprocess.run(
        [sys.executable, "-m", "snakemake",
         "--snakefile", str(SNAKEFILE), "--configfile", str(CONFIGFILE),
         "--cores", "1", str(target), "--config",
         f"input_dir={inputs}", f"output_dir={tmp_path / 'out'}",
         f"emu_db={tmp_path / 'db'}"],
        capture_output=True, text=True, cwd=tmp_path,
    )


def test_an_empty_barcode_does_not_stop_the_run(tmp_path):
    """REGRESSION: one empty directory discarded every other barcode's results.

    merge exited 1, Snakemake halted, and because emu_combine depends on every
    sample that meant no combined tables and no reports for any barcode. This
    runs merge for real -- a dry run would not reach the shell body where the
    old `exit 1` lived.
    """
    inputs = tmp_path / "fastq_pass"
    make_barcode(inputs, "barcode01")
    make_barcode(inputs, "barcode02", reads=0)      # directory, no FASTQ

    merged = tmp_path / "out" / "01_merged" / "barcode02.fastq.gz"
    r = run_target(tmp_path, inputs, merged)
    assert r.returncode == 0, r.stdout + r.stderr
    assert merged.exists(), "merge produced nothing for the empty barcode"
    # A real, readable, empty gzip -- the later rules open it with gzip.open.
    with gzip.open(merged, "rt") as fh:
        assert fh.read() == ""
    # The user is told, and told it is not fatal.
    assert "empty barcode" in (r.stdout + r.stderr)


def test_a_barcode_with_reads_still_merges(tmp_path):
    """Guards the test above: the tolerant path must not swallow real data."""
    inputs = tmp_path / "fastq_pass"
    make_barcode(inputs, "barcode01", reads=3)

    merged = tmp_path / "out" / "01_merged" / "barcode01.fastq.gz"
    r = run_target(tmp_path, inputs, merged)
    assert r.returncode == 0, r.stdout + r.stderr
    with gzip.open(merged, "rt") as fh:
        assert fh.read().count("@r") == 3
