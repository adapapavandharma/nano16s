"""`nano16s test` checks the directory it actually wrote to.

The command exists to answer one question — does this install work — so a
false "not working correctly" is the worst thing it can print. It printed
exactly that whenever `-o` was given: the flag was forwarded to the run, which
honoured it, while the verification still looked in the temporary directory the
command had made for itself and found nothing there.

A dry run is enough to catch it. The run does no work, so the verification
fails either way; what matters is which directory it names.

Run with:
    python -m pytest test/ -v
"""

import csv
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "nano16s"
DEMO = ROOT / "test" / "demo" / "fastq_pass"


def make_db(tmp_path):
    """The two files the CLI checks for before it starts."""
    db = tmp_path / "db"
    db.mkdir()
    (db / "species_taxid.fasta").write_text(">1:x\nACGT\n")
    with (db / "taxonomy.tsv").open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["tax_id", "species", "genus", "family", "order", "class",
                    "phylum", "clade", "superkingdom", "subspecies",
                    "species subgroup", "species group"])
    return db


# Snakemake is absent from the unit CI job, which installs nothing but pytest.
@pytest.mark.skipif(not CLI.exists() or not DEMO.exists()
                    or shutil.which("snakemake") is None,
                    reason="needs the CLI, the demo data and Snakemake")
class TestOutputDirectory:
    def run_test_cmd(self, tmp_path, *extra):
        """`nano16s test` as a dry run, with TMPDIR under tmp_path.

        TMPDIR is where the command would put a directory of its own, so
        pointing it at tmp_path makes one visible if it is created.
        """
        env = {"TMPDIR": str(tmp_path), "PATH": __import__("os").environ["PATH"],
               "HOME": str(tmp_path)}
        return subprocess.run(
            [str(CLI), "test", "--db", str(make_db(tmp_path)), "-n", *extra],
            capture_output=True, text=True, env=env,
        )

    def test_verifies_the_directory_given_with_o(self, tmp_path):
        """REGRESSION: the verification used to name the temporary directory,
        reporting every output missing from a run that had written them all to
        the directory asked for."""
        out = tmp_path / "persist"
        r = self.run_test_cmd(tmp_path, "-o", str(out))
        assert f"Checking {out}" in r.stdout, r.stdout + r.stderr

    def test_no_temporary_directory_when_o_is_given(self, tmp_path):
        out = tmp_path / "persist"
        self.run_test_cmd(tmp_path, "-o", str(out))
        assert not list(tmp_path.glob("nano16s_test_*"))

    def test_makes_its_own_directory_when_o_is_not_given(self, tmp_path):
        r = self.run_test_cmd(tmp_path)
        made = list(tmp_path.glob("nano16s_test_*"))
        assert len(made) == 1, r.stdout + r.stderr
        assert f"Checking {made[0]}" in r.stdout

    def test_other_options_still_reach_the_run(self, tmp_path):
        """-o is the only flag read here; everything else is passed through."""
        out = tmp_path / "persist"
        r = self.run_test_cmd(tmp_path, "-o", str(out), "--min-quality", "12")
        assert "min_quality=12" in r.stdout + r.stderr, r.stdout + r.stderr

    def test_o_without_a_value_is_refused(self, tmp_path):
        r = self.run_test_cmd(tmp_path, "-o")
        assert r.returncode != 0
        assert "requires a value" in r.stderr
