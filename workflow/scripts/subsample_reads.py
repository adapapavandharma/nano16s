"""Reservoir-sample a gzipped FASTQ to at most N reads, reproducibly.

Nanopore writes reads in the order the pores produced them, and pore quality
drifts across a run, so the first N reads are the run's beginning rather than
a sample of it. Reservoir sampling takes a genuine random subset in one pass
without holding the whole file, and a fixed seed makes the same input give the
same subset every time -- which a result someone will publish needs.

Usage: subsample_reads.py <in.fastq.gz> <out.fastq.gz> <max_reads> <seed>
"""

import gzip
import random
import sys


def reservoir(handle, k, rng):
    """Return up to k records, uniformly chosen, and the total seen."""
    kept = []          # (original index, record) so file order can be restored
    seen = 0
    while True:
        rec = [handle.readline() for _ in range(4)]
        if not rec[0]:
            break
        if len(kept) < k:
            kept.append((seen, rec))
        else:
            # Standard algorithm R: the i-th record (0-based) replaces a held
            # one with probability k/(i+1), which leaves every record equally
            # likely to survive.
            j = rng.randrange(seen + 1)
            if j < k:
                kept[j] = (seen, rec)
        seen += 1
    return kept, seen


def main() -> int:
    src, dst, k, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    rng = random.Random(seed)
    with gzip.open(src, "rt", errors="replace") as fh:
        kept, seen = reservoir(fh, k, rng)

    # Back into the order they appeared, not the order they were chosen, so
    # the output reads like a FASTQ someone could inspect by hand. Sorting on
    # the stored index; sorting on the header text would be lexical, which is
    # not file order at all.
    kept.sort(key=lambda pair: pair[0])
    with gzip.open(dst, "wt") as out:
        for _, rec in kept:
            out.writelines(rec)

    print(f"subsampled {len(kept):,} of {seen:,} reads", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
