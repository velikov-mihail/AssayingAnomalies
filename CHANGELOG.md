# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.9.0]

First release of the Python package. It replaces the MATLAB AssayingAnomalies
toolkit, which stays available, unmaintained, on the repository's
`matlab-legacy` branch.

Version numbers start at 0.9.0, the version the paper's revision was run on.
Fixes are 0.9.x. The releases numbered 0.1 to 2.0.6 that PyPI lists under the
same name (2024) are an earlier, unrelated Python implementation; they are
withdrawn, and their numbers say nothing about this package. The installed
version is `assayinganomalies.__version__` and `aa --version`; database builds
and protocol runs record it in their manifests, and the report prints it in
its first footnote.

### What the package contains

- A database build from your own WRDS account into one DuckDB file
  (`aa setup-database`): CRSP monthly and daily, Compustat annual and
  quarterly, the Fama-French factors, the Chen-Zimmerman anomaly zoo, trading
  costs and betas.
- Univariate and bivariate portfolio sorts, factor regressions, Fama-MacBeth
  regressions, trading costs and generalized alphas, as public functions.
- The anomaly-testing protocol of Novy-Marx and Velikov, "Assaying Anomalies",
  with its LaTeX/PDF report (`aa run-protocol`, `aa.test_signal`).
- A JSON run manifest for every database build and protocol run: package
  version, data vintage, sample, input hashes and seeds.

### Differences from the MATLAB toolkit

Results are deliberately not identical to MATLAB's.

- **Held legs.** A sort buys each portfolio in a month in which the signal has
  values and holds it, without rebalancing, until the next such month. Trading
  costs are those of the trades this takes, and the first purchase is reported
  separately and not charged. The Fama-French factor costs are computed the
  same way.
- **Annual Compustat columns are stored in the June they become available
  only**, so a signal built from them trades once a year. `aa.fill_months` and
  `aa.load(..., fill_annual=True)` carry the June value through the following
  May.
- **CRSP's CIZ format (Flat File Format 2.0) is the default.** The legacy SIZ
  format, which ends in December 2024, can still be selected; the two give
  slightly different numbers.
- **Chen-Zimmerman files come from Hugging Face**, for any release from
  2022.03 to 2026.10; pin a release to reproduce a zoo.
- **Randomness is seeded**: tie-breaking noise and cross-validation folds are
  reproducible, and the seed is part of the specification of a result.
- **Bugs in the MATLAB code are corrected**, among them trading-cost inputs
  that dropped NASDAQ spreads for part of the sample, a ranking step that ran
  within stock instead of across stocks, and errors in report tables and
  figure labels.

The README has the quickstart and the known limitations. The tutorial will be
on [assayinganomalies.com](https://assayinganomalies.com).

[0.9.0]: https://github.com/velikov-mihail/AssayingAnomalies/releases/tag/v0.9.0
