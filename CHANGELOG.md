# Changelog

Notable changes to nano16s. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Reference database versions are separate from the tool version. A database is
identified by its build month (for example `2026.08`) and recorded in the run
report, so a result can always be traced to the database that produced it.

## [Unreleased]

### Changed
- Porechop reserves two threads per barcode rather than eight, which is a
  change in throughput, not in what the stage does. Measured on a 55,000-read
  barcode, eight threads returns 3.46x the speed of one — so the value decided
  how many barcodes ran at a time far more than how fast each one went, and at
  eight it was one at a time on any machine with fewer than sixteen cores.
  Spending the same eight cores four ways, under real contention: eight
  single-threaded jobs finished in 1884 s, four two-threaded in 1061 s, two
  four-threaded in 650 s, one eight-threaded in 438 s — 1.86x, 1.65x, 1.35x
  and 1.00x the throughput. Two keeps 89% of the gain for less total memory
  than one, since a job needs 505 MB at one thread and 731 MB at two or more.
  A tester's 90-barcode run averaged 1.04 jobs in flight before this.

### Fixed
- A barcode directory whose name contains a space or a bracket no longer ends
  the run. `barcode02 (copy)` — what Finder and Explorer produce when a folder
  is duplicated — was picked up as a sample and killed the workflow in `merge`
  on an unquoted path, with an error that quoted the rule's own comment text
  instead of naming the directory. Sample names are now checked against
  letters, digits, dot, dash and underscore before anything runs, the message
  names each offending directory, and a `wildcard_constraints` stops such a
  name reaching a rule by another route. Paths that carry a single value are
  quoted throughout the rules, including the database path — a macOS home
  directory can contain a space.
- One empty barcode directory no longer discards every other barcode's
  results. `merge` exited 1, Snakemake halted, and because `emu_combine`
  depends on every sample there were then no combined tables and no reports
  at all — for a 90-barcode run, hours of completed work thrown away over one
  empty folder. Every later stage already tolerated a barcode with no reads:
  both NanoStat rules and Emu write an empty-result placeholder and carry on.
  `merge` now does the same and the barcode is reported with zero reads.
  Porechop_ABI needed the same guard, since it exits 1 on an empty input and
  writes nothing, which would have moved the failure one rule later.
- Porechop's working directory under `TMPDIR` is removed whether or not the
  job succeeded. The cleanup ran after the command under `set -e`, so every
  failed job left one behind.

## [1.2.0] — 2026-09-02

### Added
- `nano16s batch -d <dir-of-runs> -o <dir>` processes every run under one
  directory, into `<dir>/<run-name>/`. A run is any subdirectory holding either
  `fastq_pass/` or `barcode*` directories; anything else is ignored. Every
  option a single run takes is passed through to each, so a whole batch shares
  one set of settings — which is what makes runs comparable. Each run writes
  its own log beside its results, one failure does not stop the rest, and the
  command exits non-zero if anything failed. Reports are gathered into
  `<dir>/reports/` named by run, since they are self-contained files and that
  directory can be zipped and sent as it is. Re-running a batch resumes:
  finished work is skipped.
- `test/test_shell_portability.py` checks every rule's shell body for array
  expansions that are not guarded by a count first. It is a static scan, so it
  catches this class on any platform and on every pull request, rather than
  waiting for the weekly macOS run.
- `test/test_report_qc_claim.py` pins what the results report may claim when
  it finds nothing, so its wording cannot drift back out of step with the
  thresholds the performance report applies to the same run.

### Fixed
- The results report no longer reads as an all-clear on a barcode the
  performance report flags. The two ask different questions of the same data —
  this one catches barcodes that clearly failed (no reads, nothing left after
  filtering, under a quarter retained), the other applies absolute floors of
  80% retention, 1,000 reads and Q12. A barcode at 78% retention was quiet in
  one and flagged in the other, and the CLI sends people to the quiet one
  first. The thresholds are unchanged: which floor is right for 16S is a
  judgement about the science, not something to alter quietly. What changed is
  the claim — "nothing unusual" is now "nothing obviously wrong", and the panel
  points at the stricter report.
- The README and guide said per-job timings carry CPU time and peak memory
  without qualification, and told a reader with low core use to retune
  `resources.*.cpus`. Neither holds on macOS, where none of those are
  recorded — the same advice the report itself stopped giving there.
- `README.md` and `CONTRIBUTING.md` pointed contributors at
  `test/test_parsers.py`, 27 of the 87 tests, so a change could pass the
  documented check while breaking the batch CLI, the performance report or the
  shell-portability scan.
- The `-y` flag was described as skipping "confirmation prompts". There is one,
  and it appears only when free disk looks short.
- The bug report template asks for `bash --version` and `command -v bash`.
  Snakemake picks a rule's shell with a PATH lookup, so the version it finds
  changes how a rule behaves, and a report without it cannot be diagnosed.
- `nano16s test` no longer reports a healthy install as broken on macOS.
  Snakemake fills a benchmark's CPU and memory columns by sampling the job's
  process tree, which it cannot do there, so every one of them is `NA` while
  the wall clock it times itself stays correct. Summing those absent values
  gave `0` rather than nothing, which the check read as a measured zero and
  failed on. It is now a note, and only when peak memory is missing too —
  the two come from the same sampling, so CPU time absent on its own is still
  a real fault and still fails.
- The performance report no longer tells macOS users their cores sat idle.
  The same `0` became `0%` core use, which sent the reader to the "under half
  the cores" verdict and advised retuning `resources.*.cpus` over a machine
  that had in fact been busy. CPU time, core use and peak memory now read `-`
  when nothing reported them, and the report says once why they are blank.
  Wall-clock timings are measured directly and were never affected.
- `rule emu` no longer fails on macOS for barcodes that produce no thresholded
  table — which is most of them. The rule expanded `"${THRESH[@]}"` without
  checking the count first, and bash before 4.4 treats that as an unset
  variable when the array is empty. Snakemake runs rule bodies under `set -u`
  and picks its shell with `shutil.which("bash")`, which on a Mac with no newer
  bash installed is `/bin/bash` — still 3.2. Emu writes a thresholded table
  only when some taxon falls below `--min-abundance`, so the failure hit the
  ordinary case and not the unusual one. The neighbouring `REL` and `CNT`
  arrays were already guarded this way.
- The weekly full-pipeline job runs on macOS as well as Linux. It was Linux
  only, and the macOS jobs install the CLI and build the workflow graph without
  ever executing a rule, so no test had run Emu, Porechop or Chopper on a Mac.
  That is how the bug above reached a user. Artifacts are named per platform,
  because `upload-artifact@v4` rejects a repeated name, and one platform
  failing no longer cancels the other.
- The guide said `-y` skips "the confirmation", implying a run normally asks
  for one. There is exactly one prompt and it appears only when free disk looks
  insufficient.
- Section 16 says to match table columns by name. Barcode columns are not in
  sorted order, and the lineage columns before them differ by rank — seven at
  species, six at genus, two at phylum — so anything slicing by position breaks
  on switching rank. The phyloseq note now gives those positions rather than
  saying "the first barcode column".
- A symlinked `fastq_pass` is no longer reported as having no barcode
  directories. The count used `find` without `-L`, so a symlink was not a
  directory to find and the run stopped while `ls` showed the barcodes plainly.
  Collecting runs under one parent by symlink, rather than copying gigabytes,
  is the natural way to prepare a batch.
- The guide documents both ways WSL2 installs on Windows. A `wsl --install`
  blocked from the Microsoft Store — the norm on managed machines — sits at 0%
  rather than reporting an error, and the `--web-download` route that works
  instead launches Ubuntu inside the PowerShell window, so the Linux username
  and password are set there rather than in the separate Ubuntu window
  previously given as the only case.
- The guide can get a user past `Could not resolve host`, which previously
  stopped the setup at the Miniforge download with nothing to work from. It
  distinguishes a blocked network from a broken name lookup, since the two give
  the same error and need different fixes, and gives a single command for
  `.wslconfig` — a hand-typed one usually lands on one line, after which WSL
  ignores the file and the fix reads as tried and ineffective.
- The guide shows how to reach the output files from a file manager. Under WSL
  those files are not on `C:`, and one sentence naming the `\\wsl.localhost`
  path was all the guide offered a user wanting to open, copy or email a report.
- The guide gives working commands for processing several sequencing runs, not
  just a bare loop. Naming the runs to process, discovering them in a directory,
  leaving a long batch running under `nohup`, checking which finished, and
  gathering every report into one folder to share are each a command to copy.
  Per-run logs mean a failure is one file to open rather than a scrollback to
  search, and a failed run no longer takes the rest of the batch with it. It
  also says what the pipeline will not do — merge samples across runs, since
  barcode names collide between them.
- Two cross-references in the guide pointed at the wrong section: keeping track
  of which barcode is which sample is section 8, not 7, and applying that
  mapping to the tables is section 16, not 15.
- The guide gave the disk needed for a demo run as 3× the unpacked reads, where
  section 10 gives the measured 2.0–2.3×. The higher figure is what nano16s
  budgets, not what a run uses.
- Troubleshooting is grouped by where the problem appears — setup, data, during
  the run, opening the reports, WSL2 — rather than being one list of eighteen
  entries, and each entry is formatted the same way. Section 13 says which
  report it is describing, as section 14 already did.

## [1.1.0] — 2026-08-20

### Added
- A performance report, written on every run alongside the existing one:
  `performance_report.html`, `performance_summary.csv` and `performance.json`.
  It reports where the run spent its time, how much of the machine it used,
  and which barcodes fall below the QC floors.
- `benchmark:` records for every per-sample rule, so timings carry CPU time and
  peak memory rather than wall clock alone. These land in `benchmarks/`.
- The performance report records the machine it ran on — CPU model, physical
  cores and threads, memory, operating system, kernel and architecture — since
  a runtime means little without the hardware behind it. WSL is reported as
  both Linux and Windows, because it is both and the distinction affects I/O.
  Detection uses only the standard library, so no dependency is added and a
  machine that will not answer leaves the field blank rather than failing the
  run.
- QC checks with absolute floors — retention, read depth, median quality, and
  whether the filtered median read length falls inside the configured length
  window. A purely relative check cannot fire when a whole run is uniformly
  bad, which is the case most worth catching.
- `CONTRIBUTING.md`, this changelog, `ruff.toml` and pre-commit hooks.
- Issue templates that ask for the version and environment details needed to
  reproduce a problem.
- `.gitattributes` pinning text files to LF, so a Windows checkout cannot break
  the shell scripts and the heredocs inside the Snakemake rules.

### Fixed
- The report's manuscript paragraph now cites nano16s. It previously credited
  Porechop_ABI, Chopper, NanoStat, Emu and Snakemake but not the pipeline
  itself, so a user pasting it into a Methods section cited five other tools and
  not this one.
- Tool versions no longer render as `Emu vv3.6.2`. Emu reports its version with
  a leading `v` where the other tools do not; that prefix is now stripped at
  capture, for every tool rather than as a special case.
- The performance report now says when it has no timings, instead of quietly
  dropping the sections that would have held them. A run into an output
  directory that already holds finished results gives Snakemake nothing to
  run, so no job records a benchmark; the report still rendered its read
  counts and quality — which come from NanoStat — while the timing sections
  vanished and every timing column read `-`, with nothing to explain why.
  Directories built by 1.0.0 hit this the first time they are re-used.
- A barcode whose reads were all filtered out is no longer reported as having
  a median quality of Q0.0. NanoStat writes zeros for an empty file rather
  than omitting the fields, so an emptied barcode read as a measurement of
  zero and drew a second flag beside the retention one that already gave the
  real reason. A run whose length window does not match the amplicon puts
  every barcode into this state, so it doubled the flags exactly when the
  report most needed to be readable.
- On macOS, a system version file that will not open no longer takes the whole
  performance report down. Reading the OS name goes through
  `platform.mac_ver()`, which parses a plist under `/System/Library`; every
  other hardware lookup in the report already tolerated its source being
  unreadable, and this one did not.
- The CLI names the performance report in `--help` and after a run, rather
  than writing it on every run without mentioning it anywhere.
- A clean run that produced no `nano16s_report.html` no longer reports failure.
  The final line was a `[[ -f ... ]] && echo` list, so its own false branch
  became the script's exit status.
- Barcodes appear in the same order in every chart of the report. The funnel
  chart reads `preprocessing_summary.csv`, which is sorted; the composition
  charts read Emu's combined table, whose column order is whatever its input
  directory listing happened to be. Two runs of the same data produced
  differently ordered tables, and within one page the two charts could not be
  read against each other.
- A `MANIFEST.json` missing one key no longer costs the whole database
  description. The `,` format spec raises on a string, so the `'?'` default
  could never be rendered and the Methods entry fell back to a directory name.
- `nano16s -d` no longer exits with no output at all when part of the input is
  unreadable. The disk-space estimate ran under `set -euo pipefail` with
  stderr suppressed, so a `du` that could not read one subdirectory ended the
  run before the banner printed. The estimate now degrades to "size unknown".
- Numeric options are validated before the run starts, and a `--min-length`
  above `--max-length` is refused. That window filters out every read, so the
  run used to complete with empty tables and no error.
- `nano16s db build` no longer deletes a working database before rebuilding it.
  The directory is named after the current month, so a second build in the same
  month removed the old database and an Emu failure or Ctrl-C then left
  neither. The new database is built alongside and swapped in once complete.
- Database downloads have a timeout and are verified against `Content-Length`.
  A stalled connection hung the build indefinitely, and a truncated file was
  cached as valid, so every later build failed in `gzip.open` with nothing
  pointing at `~/.nano16s/cache`.
- CI runs the whole test suite rather than one file, and enforces `ruff` and
  `shellcheck`. Naming `test/test_parsers.py` explicitly meant 31 of the 53
  tests never ran, and the linters were configured but only in the opt-in
  pre-commit hook.
- The weekly CI artifact contains the performance report, its CSV and JSON, and
  the benchmark records. It had listed only the files that existed before 1.1.0,
  so every weekly artifact was quietly incomplete.
- Emu's full abundance table is delivered, not its thresholded one. Emu writes
  a second table whenever any taxon falls below `--min-abundance` (default
  0.0001), and the pattern used to pick the result matched both — with the
  thresholded name sorting first. A barcode with any taxon under 0.01% shipped a
  re-normalised table of fewer taxa while its neighbours shipped full ones, so
  barcodes within one run were not comparable. Eight of 24 barcodes were
  affected in one demo run.
- A file left behind by an interrupted run is no longer counted as an extra
  sample. Emu names its output after the input, and a run stopped between that
  and the rename left the original in place; the combine step then read it as a
  second barcode. A 24-barcode run could produce a 32-column table in which
  eight barcodes appeared twice with different values, with nothing to say so.
- A barcode that loses every read to the filter is named in the report instead
  of quietly vanishing. Its Emu output is empty, so it is absent from the
  combined tables and the composition charts while the read counts above still
  include it — which a script reading the TSV downstream cannot see.
- Run timings are measured over the time the machine was working rather than
  the calendar. Only stages that re-run write new benchmark records, so a
  resumed directory reported the gap between two sittings: a 39-minute resume of
  a week-old directory showed 144 hours elapsed and 0.5% core use. The report now
  excludes idle time between runs, says how much it excluded, and marks each
  restart on the timeline.
- `nano16s test` writes its output under the home directory instead of `/tmp`.
  Ubuntu's default Firefox is a snap and has its own private `/tmp`, so the
  browser reported "File not found" for a report the terminal was listing in the
  same window.
- Barcode directories with no `.fastq.gz` are named before the run starts, and
  distinguished from ones holding uncompressed `.fastq`. This previously
  surfaced from the merge rule after Snakemake had begun work, naming only the
  first barcode it reached.
- Chopper reserves one core instead of four. Measured at 0.86 to 1.14 cores
  across every demo run; the stage is bound by single-threaded compression, so
  the other three blocked Porechop and Emu jobs queued behind them.
- The install footprint in the guide and README was wrong in both directions:
  the environment is 1.8 GB rather than ~1 GB, the database 45 MB rather than
  ~150 MB, and run output 2.0-2.3x the input rather than 3x. The ~100 MB
  download cache left in `~/.nano16s/cache` is now documented.

## [1.0.0]

First release.

### Added
- Snakemake workflow: merge per barcode, QC with NanoStat, adapter trimming with
  Porechop_ABI, length and quality filtering with Chopper, QC again, then
  taxonomic classification with Emu.
- Combined abundance tables at species, genus and phylum level, as relative
  abundance and as read counts.
- Self-contained HTML report — one file, no external assets, safe to email.
  Records tool versions, parameters and database version.
- `nano16s db build`, which builds an Emu database from the current NCBI 16S
  RefSeq Targeted Loci collection. Emu's own database has not been refreshed
  since September 2020. Databases install side by side and never overwrite each
  other, so re-running an old analysis against its original database stays
  possible.
- `nano16s test`, an end-to-end run on bundled demo data that verifies an actual
  installation.
- Unit tests for the parsing functions, and CI covering Linux and Apple Silicon.
- One-command install via `install.sh`.
