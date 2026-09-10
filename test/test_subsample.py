"""Subsampling before classification.

Emu's cost scales with read count and its thread setting is already optimal,
so on a large run this is the only lever that shortens classification. It also
changes results, which is why it is off by default and why these tests care as
much about the sampler being unbiased as about it being fast.
"""

import gzip
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "workflow" / "scripts" / "subsample_reads.py"


def write_fastq(path: Path, n: int) -> Path:
    """n reads, each named for its position, so a subset can be traced back."""
    with gzip.open(path, "wt") as fh:
        for i in range(n):
            fh.write(f"@r{i:06d}\nACGT\n+\n!!!!\n")
    return path


def run(src: Path, dst: Path, k: int, seed: int = 1):
    subprocess.run([sys.executable, str(SCRIPT), str(src), str(dst), str(k), str(seed)],
                   check=True, capture_output=True)
    ids = []
    with gzip.open(dst, "rt") as fh:
        while True:
            head = fh.readline()
            if not head:
                break
            ids.append(int(head[2:].strip()))
            for _ in range(3):
                fh.readline()
    return ids


def test_keeps_exactly_the_requested_number(tmp_path):
    src = write_fastq(tmp_path / "in.fastq.gz", 1000)
    assert len(run(src, tmp_path / "out.fastq.gz", 100)) == 100


def test_fewer_reads_than_asked_for_are_all_kept(tmp_path):
    """Not an error, and must not truncate: a small barcode keeps everything."""
    src = write_fastq(tmp_path / "in.fastq.gz", 50)
    assert len(run(src, tmp_path / "out.fastq.gz", 5000)) == 50


def test_output_is_in_file_order(tmp_path):
    """Selection order is random; the file should still read like a FASTQ."""
    src = write_fastq(tmp_path / "in.fastq.gz", 1000)
    ids = run(src, tmp_path / "out.fastq.gz", 100)
    assert ids == sorted(ids)


def test_same_seed_gives_the_same_reads(tmp_path):
    """A published abundance table has to be reproducible from the same input."""
    src = write_fastq(tmp_path / "in.fastq.gz", 1000)
    a = run(src, tmp_path / "a.fastq.gz", 100, seed=42)
    b = run(src, tmp_path / "b.fastq.gz", 100, seed=42)
    assert a == b


def test_different_seed_gives_different_reads(tmp_path):
    src = write_fastq(tmp_path / "in.fastq.gz", 1000)
    a = run(src, tmp_path / "a.fastq.gz", 100, seed=1)
    b = run(src, tmp_path / "b.fastq.gz", 100, seed=2)
    assert a != b


def test_every_part_of_the_file_is_equally_likely(tmp_path):
    """The one that matters.

    Nanopore writes reads in the order the pores produced them and pore quality
    drifts across a run, so a sampler biased toward the start of the file would
    skew every abundance estimate toward early reads -- silently, since the
    output would still look like a valid FASTQ. Taking the first N would fail
    this outright; reservoir sampling should be flat.
    """
    src = write_fastq(tmp_path / "in.fastq.gz", 1000)
    buckets = Counter()
    trials = 200
    for seed in range(trials):
        for i in run(src, tmp_path / "out.fastq.gz", 100, seed=seed):
            buckets[i // 100] += 1          # ten equal slices of the file
    counts = [buckets[b] for b in range(10)]
    expected = sum(counts) / 10
    worst = max(abs(c - expected) for c in counts) / expected
    assert worst < 0.15, f"slice counts uneven: {counts}"


# --- the option must be invisible when it is off ---------------------------

SNAKEFILE = ROOT / "workflow" / "Snakefile"
CONFIGFILE = ROOT / "config" / "config.yaml"


def make_run(root: Path):
    d = root / "fastq_pass" / "barcode01"
    d.mkdir(parents=True)
    write_fastq(d / "barcode01_0.fastq.gz", 20)
    return root / "fastq_pass"


def dag(tmp_path, extra_config):
    return subprocess.run(
        [sys.executable, "-m", "snakemake", "--snakefile", str(SNAKEFILE),
         "--configfile", str(CONFIGFILE), "--cores", "1", "-n", "--config",
         f"input_dir={make_run(tmp_path)}", f"output_dir={tmp_path / 'out'}",
         f"emu_db={tmp_path / 'db'}"] + extra_config,
        capture_output=True, text=True, cwd=tmp_path,
    )


@pytest.mark.skipif(
    subprocess.run(["which", "snakemake"], capture_output=True).returncode != 0,
    reason="snakemake not installed")
def test_the_stage_is_absent_by_default(tmp_path):
    """With max_reads at 0 the graph must be the one that ran before."""
    r = dag(tmp_path, [])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "subsample" not in r.stdout


@pytest.mark.skipif(
    subprocess.run(["which", "snakemake"], capture_output=True).returncode != 0,
    reason="snakemake not installed")
def test_the_stage_appears_when_asked_for(tmp_path):
    r = dag(tmp_path, ["max_reads=10"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "subsample" in r.stdout
