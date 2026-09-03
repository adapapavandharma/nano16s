"""The results report's QC claim, against the performance report's floors.

The two reports ask different questions of the same run. This one catches
barcodes that clearly failed: no reads, nothing left after filtering, under a
quarter retained. `make_perf_report` applies absolute floors -- 80% retention,
1,000 reads, Q12, and the configured length window.

A barcode at 78% retention is therefore quiet here and flagged there, and the
CLI sends people to this report first. An unqualified "nothing unusual" read
as the two contradicting each other, so the claim is qualified and points at
the stricter report. The thresholds themselves are deliberately not changed:
which floor is right for 16S is a judgement about the science.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow" / "scripts"))

import make_report  # noqa: E402


class Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self._items = list(kw.values())

    def __getitem__(self, i):
        return self._items[i]


def write_inputs(tmp_path, raw, filtered):
    """A one-barcode run with the given read counts."""
    summary = tmp_path / "preprocessing_summary.csv"
    with open(summary, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["barcode", "raw_reads", "filtered_reads"])
        w.writerow(["barcode01", raw, filtered])

    paths = {}
    for rank, taxon in (("species", "Escherichia coli"), ("genus", "Escherichia")):
        p = tmp_path / f"{rank}.tsv"
        p.write_text(f"{rank}\tbarcode01\n{taxon}\t1.0\n", encoding="utf-8")
        paths[rank] = str(p)
    return str(summary), paths


def render(tmp_path, raw, filtered):
    summary, paths = write_inputs(tmp_path, raw, filtered)
    out = tmp_path / "nano16s_report.html"
    make_report.snakemake = Stub(
        input=Stub(summary=summary, species=paths["species"], genus=paths["genus"]),
        params=Stub(db=str(tmp_path / "db"), min_length=1000, max_length=2000,
                    min_quality=10, version="1.2.0"),
        output=[str(out)],
    )
    try:
        make_report.main()
    finally:
        del make_report.snakemake
    return out.read_text(encoding="utf-8")


def test_a_clean_run_does_not_claim_more_than_it_checked(tmp_path):
    """REGRESSION: 'Nothing unusual' contradicted the performance report.

    78% retention clears this report's 25% floor and fails the performance
    report's 80% one. Both ran on the same data.
    """
    html = render(tmp_path, raw=10_000, filtered=7_830)
    assert "Nothing unusual" not in html
    assert "nothing obviously wrong" in html.lower()
    # The reader has to be told where the stricter check lives.
    assert "performance_report.html" in html


def test_an_obviously_broken_barcode_is_still_flagged(tmp_path):
    """The qualified wording must not soften the failures it does catch."""
    html = render(tmp_path, raw=10_000, filtered=0)
    assert "lost every read" in html
    assert "nothing obviously wrong" not in html.lower()
