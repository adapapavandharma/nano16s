"""The input size the CLI reports before a run, and warns on.

The preflight measures the input directory to estimate the disk a run needs,
prints that size in the startup banner, and warns if the output disk is too
small. It measured with `du -sm`, which counts a symlink as the few bytes of
the link itself. Input assembled from symlinks -- to FASTQ files or to whole
barcode directories -- read as about 1 MB, so the estimate was worthless
exactly when the data lived somewhere else.

These run the real CLI up to the banner. A stand-in `snakemake` on PATH ends
the run the moment it would start, so no database, workflow or minute is
needed.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "nano16s"

pytestmark = pytest.mark.skipif(not CLI.exists(), reason="CLI not present")

MB = 1024 * 1024


def fake_env(tmp_path):
    """A stand-in database and a snakemake that exits at once."""
    db = tmp_path / "db"
    db.mkdir()
    (db / "taxonomy.tsv").write_text("")
    (db / "species_taxid.fasta").write_text("")
    stub = tmp_path / "stub"
    stub.mkdir()
    sm = stub / "snakemake"
    sm.write_text("#!/bin/sh\nexit 0\n")
    sm.chmod(0o755)
    env = dict(os.environ, PATH=f"{stub}{os.pathsep}{os.environ['PATH']}")
    return db, env


def reported_mb(input_dir, tmp_path):
    db, env = fake_env(tmp_path)
    r = subprocess.run(
        [str(CLI), "-d", str(input_dir), "-o", str(tmp_path / "out"),
         "--db", str(db), "--cores", "1", "-y"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    m = re.search(r"barcodes, (\d+) MB\)", r.stdout)
    assert m, f"no input size in the banner:\n{r.stdout}\n{r.stderr}"
    return int(m.group(1))


def big_file(path, mb=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(mb * MB))
    return path


def test_plain_input(tmp_path):
    big_file(tmp_path / "run" / "barcode01" / "reads.fastq.gz")
    assert reported_mb(tmp_path / "run", tmp_path) >= 3


def test_symlinked_fastq(tmp_path):
    """REGRESSION: a 3 MB file behind a symlink read as 1 MB."""
    real = big_file(tmp_path / "elsewhere" / "reads.fastq.gz")
    bc = tmp_path / "run" / "barcode01"
    bc.mkdir(parents=True)
    (bc / "reads.fastq.gz").symlink_to(real)
    assert reported_mb(tmp_path / "run", tmp_path) >= 3


def test_symlinked_barcode_directory(tmp_path):
    """A whole barcode directory linked in from another run."""
    big_file(tmp_path / "other_run" / "barcode07" / "reads.fastq.gz")
    run = tmp_path / "run"
    run.mkdir()
    (run / "barcodePool5").symlink_to(tmp_path / "other_run" / "barcode07")
    assert reported_mb(run, tmp_path) >= 3
