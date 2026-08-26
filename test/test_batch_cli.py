"""Tests for `nano16s batch`.

These cover what the command decides before it starts any work: which
subdirectories are runs, and which mistakes it should refuse rather than
half-execute. They invoke the real CLI, but every case here exits during
validation, so none of them needs a database, Snakemake, or a minute.

The one case that is not about refusing is discovery. Batch is the command
people will point at a directory of runs they cannot afford to re-do, so what
it decides to process — and what it silently ignores — is worth pinning down.

Run with:
    python -m pytest test/ -v
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "nano16s"


def run(*args, cwd=None):
    return subprocess.run(
        [str(CLI), "batch", *args],
        capture_output=True, text=True, cwd=cwd,
    )


def make_run(parent: Path, name: str, barcodes=("barcode01", "barcode02")):
    """A run in the layout MinKNOW writes: <name>/fastq_pass/barcode*/."""
    for bc in barcodes:
        d = parent / name / "fastq_pass" / bc
        d.mkdir(parents=True)
        (d / "reads.fastq.gz").write_bytes(b"")
    return parent / name


@pytest.mark.skipif(not CLI.exists(), reason="CLI not present")
class TestValidation:
    def test_needs_input_dir(self):
        r = run("-o", "out")
        assert r.returncode != 0
        assert "-d" in r.stderr

    def test_needs_output_dir(self, tmp_path):
        r = run("-d", str(tmp_path))
        assert r.returncode != 0
        assert "-o" in r.stderr

    def test_missing_input_dir(self, tmp_path):
        r = run("-d", str(tmp_path / "nope"), "-o", str(tmp_path / "out"))
        assert r.returncode != 0
        assert "not found" in r.stderr

    def test_single_run_is_refused(self, tmp_path):
        """A fastq_pass passed directly is one run, not a batch.

        Reporting "no runs found" inside it would be true and useless; the
        user wants to be told which command they meant.
        """
        make_run(tmp_path, "run_a")
        r = run("-d", str(tmp_path / "run_a" / "fastq_pass"),
                "-o", str(tmp_path / "out"))
        assert r.returncode != 0
        assert "single run" in r.stderr
        assert "nano16s -d" in r.stderr

    def test_empty_parent(self, tmp_path):
        (tmp_path / "in").mkdir()
        r = run("-d", str(tmp_path / "in"), "-o", str(tmp_path / "out"))
        assert r.returncode != 0
        assert "no runs found" in r.stderr


@pytest.mark.skipif(not CLI.exists(), reason="CLI not present")
class TestDiscovery:
    """What batch decides to process, checked via the banner it prints."""

    def _runs_listed(self, parent: Path, out: Path):
        r = run("-d", str(parent), "-o", str(out), "-n")
        line = next((ln for ln in r.stdout.splitlines()
                     if ln.strip().startswith("runs")), "")
        return line.split(maxsplit=1)[1].split() if line else []

    def test_finds_fastq_pass_layout(self, tmp_path):
        make_run(tmp_path / "in", "Flongle_Demo01")
        make_run(tmp_path / "in", "MinION_Demo01")
        found = self._runs_listed(tmp_path / "in", tmp_path / "out")
        assert found == ["Flongle_Demo01", "MinION_Demo01"]

    def test_finds_bare_barcode_layout(self, tmp_path):
        """Some people unpack the barcodes straight into the run directory."""
        for bc in ("barcode01", "barcode02"):
            d = tmp_path / "in" / "run_a" / bc
            d.mkdir(parents=True)
            (d / "reads.fastq.gz").write_bytes(b"")
        assert self._runs_listed(tmp_path / "in", tmp_path / "out") == ["run_a"]

    def test_ignores_non_runs(self, tmp_path):
        """A stray notes folder or an old analysis must not become a run."""
        make_run(tmp_path / "in", "real_run")
        (tmp_path / "in" / "notes").mkdir(parents=True)
        (tmp_path / "in" / "old_analysis" / "07_emu_combined").mkdir(parents=True)
        (tmp_path / "in" / "readme.txt").write_text("hello")
        assert self._runs_listed(tmp_path / "in", tmp_path / "out") == ["real_run"]

    def test_discovers_symlinked_runs(self, tmp_path):
        """Symlinking runs under one parent is how a batch gets assembled
        without copying gigabytes, so discovery has to see through them."""
        real = make_run(tmp_path / "store", "Flongle_Demo01")
        (tmp_path / "in").mkdir()
        (tmp_path / "in" / "Flongle_Demo01").symlink_to(real)
        assert self._runs_listed(tmp_path / "in", tmp_path / "out") == \
            ["Flongle_Demo01"]


@pytest.mark.skipif(not CLI.exists(), reason="CLI not present")
def test_symlinked_fastq_pass_is_not_empty(tmp_path):
    """REGRESSION: a symlinked fastq_pass counted as zero barcodes.

    Discovery finding a run is only half of it — each run is then handed to
    the single-run path, which counted barcodes with `find` and not `find -L`.
    A symlink is not a directory to find, so the count came back zero and the
    run stopped saying there were no barcode directories while `ls` listed
    them. Batch makes this the common case rather than the odd one, because
    assembling runs under one parent by symlink is how you avoid copying
    gigabytes.

    Asserted on the single-run path, which is where the count lives.
    """
    real = make_run(tmp_path / "store", "run_a")
    link = tmp_path / "linked_fastq_pass"
    link.symlink_to(real / "fastq_pass")

    r = subprocess.run(
        [str(CLI), "-d", str(link), "-o", str(tmp_path / "out"), "-n"],
        capture_output=True, text=True,
    )
    # It may still stop for want of a database, which is a different problem
    # and not this test's business. It must not stop for want of barcodes.
    assert "no barcode" not in r.stderr, r.stderr
