#!/usr/bin/env python3
"""Per-barcode read accounting: where every read went, and how many taxa it found.

    read_accounting.py <emu_output_dir> <preprocessing_summary.csv> <out.tsv>

The tables the pipeline already writes answer "what is in this sample?" but not
"does this add up?". The counts table holds one row per taxon, plus a row Emu
leaves unnamed that carries the reads it could not place, so a reader who sums
a column gets a number with no obvious relation to the reads that went in --
and a reader who drops the unnamed row silently loses those reads.

This writes one row per barcode:

    raw -> filtered -> given to the classifier -> classified + unclassified

with the number of species and genera found. `check` is `ok` when
classified + unclassified equals the reads the classifier was given, which is
the arithmetic a reader should not have to do themselves.

With --max-reads, the classifier is given fewer reads than passed the filter;
`subsampled_out` is that difference, so the chain still balances.
"""
import csv
import os
import sys

# Emu's own labels for reads it did not place. They appear in the tax_id
# column with every taxonomy field empty.
UNPLACED_IDS = {"unmapped", "mapped_filtered", "mapped_unclassified"}


def count_file(path):
    """One barcode's Emu table -> (classified, unclassified, species, genera)."""
    classified = unclassified = 0.0
    species, genera = set(), set()
    with open(path) as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            try:
                n = float(row.get("estimated counts") or 0)
            except ValueError:
                continue
            if n <= 0:
                continue
            name = (row.get("species") or "").strip()
            tax_id = (row.get("tax_id") or "").strip()
            if tax_id in UNPLACED_IDS or not name:
                unclassified += n
                continue
            classified += n
            species.add(name)
            genus = (row.get("genus") or "").strip()
            if genus:
                genera.add(genus)
    return classified, unclassified, len(species), len(genera)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    emu_dir, summary_csv, out_tsv = sys.argv[1:4]

    pre = {}
    if os.path.exists(summary_csv):
        with open(summary_csv) as fh:
            for r in csv.DictReader(fh):
                pre[r["barcode"]] = r

    rows = []
    for barcode in sorted(pre) or sorted(os.listdir(emu_dir)):
        f = os.path.join(emu_dir, barcode, f"{barcode}_rel-abundance.tsv")
        if not os.path.exists(f) or os.path.getsize(f) == 0:
            # A barcode with no reads is reported with zeros rather than
            # dropped: a missing row reads as an oversight, a zero row as a
            # fact about the run.
            classified = unclassified = 0.0
            n_species = n_genera = 0
        else:
            classified, unclassified, n_species, n_genera = count_file(f)

        def num(key):
            try:
                return int(float(pre.get(barcode, {}).get(key, 0) or 0))
            except ValueError:
                return 0

        raw, filtered = num("raw_reads"), num("filtered_reads")
        to_classifier = int(round(classified + unclassified))
        rows.append({
            "barcode": barcode,
            "raw_reads": raw,
            "removed_by_filter": raw - filtered,
            "filtered_reads": filtered,
            "subsampled_out": max(0, filtered - to_classifier),
            "reads_to_classifier": to_classifier,
            "reads_classified": int(round(classified)),
            "reads_unclassified": int(round(unclassified)),
            "unclassified_pct": (f"{unclassified / to_classifier:.2%}"
                                 if to_classifier else "-"),
            "species_found": n_species,
            "genera_found": n_genera,
            "check": "ok" if to_classifier == int(round(classified)) + int(round(unclassified))
                     else "MISMATCH",
        })

    os.makedirs(os.path.dirname(out_tsv) or ".", exist_ok=True)
    with open(out_tsv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["barcode"],
                           delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    total = sum(r["reads_to_classifier"] for r in rows)
    placed = sum(r["reads_classified"] for r in rows)
    print(f"read accounting: {len(rows)} barcodes, {total:,} reads classified or not, "
          f"{placed:,} placed ({placed / total:.1%})" if total else
          f"read accounting: {len(rows)} barcodes, no classified reads")


if __name__ == "__main__":
    main()
