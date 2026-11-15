# Hasbrouck's Gibbs spread estimates

This folder holds the one input file the trading-cost build needs that WRDS does not
provide, and the code that makes it.

| File | What it is |
|---|---|
| `crspgibbs.csv` | Gibbs estimates of the Roll model, one row per stock (`permno`), year and sub-sample: 526,126 rows, 1926–2024, 42 MB |
| `RollGibbsLibrary02.sas` | Joel Hasbrouck's SAS/IML routines for the Gibbs sampler (July 2010) |
| `crspGibbsBuildv01.sas` | Hasbrouck's driver: builds the CRSP sample and runs the sampler over it, then writes `crspgibbs.csv` |

The estimates are the Gibbs effective spreads of Hasbrouck (2009), "Trading Costs and
Returns for U.S. Equities: Estimating Effective Costs from Daily Data", *Journal of
Finance* 64(3). The code is Hasbrouck's; the only changes made here are listed under
[What was changed in the SAS code](#what-was-changed-in-the-sas-code).

## Do I need to do anything?

**No, not for a normal build.** `aa setup-database` finds this file by itself:

- in a clone of the repository it reads `inputs/gibbs/crspgibbs.csv` directly;
- after `pip install` (no clone) it downloads the same file from this repository's
  `gibbs-data-v1` tag into `Data/staging/`, checks its SHA-256, and reuses it afterwards.

Every `tcosts_type` uses it. See the repository's
[README](../../README.md#trading-costs-what-you-need) for the whole picture, including the
optional high-frequency file.

You only need the instructions below if you want Gibbs estimates the shipped file does not
have, for example after changing the CRSP sample.

## Building a fresh file on WRDS Cloud

You need a WRDS account with CRSP access. The program reads three CRSP tables (`crsp.dsf`,
`crsp.dsenames`, `crsp.dsi`), which the WRDS Cloud SAS session already has as the `crsp`
library. Nothing needs to be downloaded to your computer until the end.

> **The shipped file already runs through 2024, and so does this code.** It reads CRSP's
> legacy daily file (Flat File Format 1.0, "SIZ"), which CRSP froze at December 2024. Rerunning
> it as written reproduces the same years. Estimates for 2025 and later need the program
> adapted to the CIZ tables (`crsp.dsf_v2` and friends); that port has not been done.

The run is long: the sampler runs once for each stock-year sub-sample with at least 60 days
with a trade (about 400,000 of them). We have not timed it on WRDS Cloud. Plan for a job that runs many
hours, and see step 6 for how to resume.

1. **Open SAS Studio.** Go to <https://wrds-cloud.wharton.upenn.edu/SASStudio/> and log in.
2. **Make a working folder.** In the left-hand panel, open your institution's folder under
   `/scratch/`, right-click it and create a new folder, for example `gibbs`. The program
   keeps its intermediate tables there and writes the output there. Note the folder's full
   path (right-click → Properties), e.g. `/scratch/youruniversity/gibbs/`.
3. **Upload the two programs.** Right-click the new folder → *Upload Files…* and upload
   `RollGibbsLibrary02.sas` and `crspGibbsBuildv01.sas` from this folder.
4. **Point both programs at your folder.** Open each file (double-click) and change the
   one line near the top,

   ```sas
   %let gibbsdir = /scratch/YOUR_INSTITUTION/gibbs/;
   ```

   to your folder's path from step 2. Keep the trailing slash, and use the same path in both
   files. Save.
5. **Run them, in this order.**
   1. `RollGibbsLibrary02.sas` (press F3, or click *Run*). It compiles the sampler's routines
      into your folder and takes seconds.
   2. `crspGibbsBuildv01.sas`. This is the long run. Its log prints a progress line every 500
      sub-samples (time, count, current `permno` and year).
6. **If the run stops part-way** (a session timeout, say), look at the last `permno` printed in
   the log, set `%let startPermno=<that permno>;` near the top of `crspGibbsBuildv01.sas`, and
   run it again. The program starts its table of estimates afresh on every run, so the CSV
   from a resumed run holds only the stocks from `startPermno` on. Copy the first run's
   `gibbsout` table (in your folder) aside before resuming, and stack the two yourself; or
   simply rerun from the start.
7. **Download the result.** When the run finishes, `crspgibbs.csv` is in your folder.
   Right-click it → *Download File*.
8. **Use it.** Either replace `inputs/gibbs/crspgibbs.csv` in your clone, or keep the
   shipped file and point the build at yours:

   ```bash
   aa set-params --gibbs-path /path/to/your/crspgibbs.csv
   aa setup-database --start-from compute-tcosts
   ```

   The second command recomputes only the trading costs and what follows them, not the
   WRDS downloads. Your own file is used as is: the SHA-256 check applies only to the copy
   the package downloads.

### What was changed in the SAS code

Both programs originally pointed their SAS libraries (`this`, and in the driver also `temp`
and `crsp`) at folders on a local Windows drive. The copies here instead:

- set one `%let gibbsdir = ...;` near the top and point the `this` and `temp` libraries at it;
- leave the `crsp` library to WRDS (the original line is commented out, for use with a local
  copy of the three CRSP tables);
- write `crspgibbs.csv` into `gibbsdir`, not the session's working directory.

The estimation code itself is unchanged.

## Columns

| Column | Meaning |
|---|---|
| `permno` | CRSP permanent number |
| `year` | Calendar year of the sample |
| `kSample` | Sub-sample within the year; a new one starts at a split or a change of listing exchange |
| `c` | Estimated effective cost (half the effective spread); empty when the sub-sample had fewer than 60 days with a trade |
| `beta`, `varu`, `sdu` | The other parameters of the Roll model: market beta, and the variance and standard deviation of the efficient-price innovation |
| `exchcd`, `shrcd`, `CFACPR` | CRSP exchange code, share code and price-adjustment factor for the sub-sample |
| `firstDate`, `lastDate` | First and last date of the sub-sample |
| `nDays`, `nTradeDays` | Days in the sub-sample, and days with a trade |

The build uses `permno`, `year` and `c`: it averages `c` over a year's sub-samples, doubles
it into a full effective spread, and applies that to every month of the year.
