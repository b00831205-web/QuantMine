# quantmine

An equity factor research library built around one principle: **statistical
honesty**. Every step that commonly inflates backtest results — survivorship
bias, overlapping-return autocorrelation, multiple testing, look-ahead in
orthogonalization, unrealistic transaction costs — is explicitly addressed,
and conclusions are reported with their uncertainty, not just their point
estimates.

The repo doubles as a full S&P 500 research case study: the library
(`quantmine/`), the daily Airflow pipeline (`pipelines/`), and the findings
below were produced by the same code you can `pip install`.

## Install

```bash
pip install quantmine          # library only
pip install "quantmine[data]"  # + yfinance download stack
```

For development (repo checkout, Python ≥ 3.13, [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
python -m pytest test
```

## Quick start

Bring your own price data — any wide DataFrame (index = trading days,
columns = tickers) works; nothing is hard-wired to yfinance or the S&P 500:

```python
import pandas as pd
import quantmine as qm

# 1) Wrap your data (or use qm.ParquetSource / qm.YFinanceSource)
data = qm.MarketData(close=close_df, volume=volume_df)

# 2) Register a custom factor — built-in factors register automatically
@qm.factor_register("my_reversal")
def my_reversal(close: pd.DataFrame, tickers: list) -> pd.DataFrame:
    return -close[tickers].pct_change(5)

# 3) Compute all registered factors (dependencies resolve automatically)
pool = qm.build_param_pool(data, day=5, halflife=10, period=20)
failed, factors = qm.calculate_all_factors(pool)

# 4) Cross-sectional IC with Newey-West t-stats and multiple-testing control
fwd = qm.forward_return(data.close, periods=[1, 5, 20])
cs_ic = qm.CS_Information_Correlation(factors, fwd, output_path="cs_ic.parquet")
report = qm.multiple_testing(qm.newey_west_summary(cs_ic))

# 5) Quantile backtest on a point-in-time universe, turnover-based costs
universe = qm.MembershipTableSource(membership_df)   # or qm.StaticUniverse([...])
results, history = qm.quantile_backtest(universe, factors, ["my_reversal"], fwd)
daily = qm.expand_all_to_daily_returns(history, data.close)

# 6) Carhart four-factor attribution of the long-short returns (daily, HAC)
french = qm.load_french_factors("ff3_daily.csv", "momentum_daily.csv")
model = qm.carhart_attribution(daily[("my_reversal", 20)]["long_short"], french)
```

### Extension points

| Protocol / hook | Purpose | Ships with |
|---|---|---|
| `DataSource.load(...) -> MarketData` | plug in any price/volume source | `ParquetSource`, `CSVSource`, `ExcelSource`, `YFinanceSource` |
| `ConstituentsSource.get_constituents(date) -> set` | point-in-time universe from any provider | `MembershipTableSource` (interval table), `StaticUniverse` |
| `@factor_register(name)` | add factors; params injected by name, factor-on-factor dependencies resolved | 8 built-in factors |
| `config.example.yaml` | every pipeline parameter as validated dataclasses via `qm.load_configs` | defaults documented in-file |

## Headline result (S&P 500 case study)

The 20-day average volume factor (`TwentyDayAvgVol`) is the only candidate
that survives the full testing gauntlet:

| Stage | Result |
|---|---|
| Train IC (2015–2023, Newey-West) | t = 3.78 (20d holding), passes Bonferroni & Benjamini-Hochberg across all 18 factor × horizon tests |
| Out-of-sample quintiles (2024–2026) | Monotonic (Spearman 0.9); long-short gross ~14 %/yr (Sharpe ~1.5), ~1.4 Sharpe net of turnover-based costs |
| Carhart 4-factor attribution (daily, HAC, net of costs) | Market beta 0.24 (significant), large-cap tilt (SMB −0.13); momentum & value loadings insignificant |
| Net alpha | ~10 %/yr net of costs (t = 1.78, p ≈ 0.07, n = 603 daily obs) — economically meaningful, **marginally short of the 5 % significance bar** on 2.4 years of out-of-sample data |

The honest conclusion: the factor's IC is robustly significant in-sample under
conservative testing; its out-of-sample net alpha is economically meaningful
but does not clear conventional significance. Live verification over a longer
window is required — and that is exactly what a research report should say.
(A low-power period-level regression, n ≈ 30, says nothing either way —
p ≈ 0.38 with a confidence interval wide enough to hold any conclusion. Test
power and test bookkeeping move the verdict as much as the signal does.)

The remaining seven candidate factors (momentum, short-term reversal,
volatility, downside volatility, volume-price correlation, …) fail the
corrected significance tests. Documenting *why* they fail is part of the
point.

## Methodology highlights

- **Survivorship-bias correction** — the universe is rebuilt from historical
  S&P 500 membership (764 tickers over 2015–2026); 569 were recoverable via
  yfinance, and the residual gap is disclosed rather than hidden.
- **Point-in-time universe** — each backtest cross-section only contains
  stocks that were actually index members on that date.
- **Newey-West IC tests** — daily ICs on overlapping k-day forward returns are
  autocorrelated; plain `t = IR·√n` overstates significance several-fold. NW
  (Bartlett kernel, lag = 2(k−1)) uses all daily observations while correcting
  the standard error. A down-sampled IID test is kept as a robustness control.
- **Multiple-testing control** — Bonferroni and Benjamini-Hochberg across all
  factor × holding-period combinations.
- **Train/test split with embargo** — factors are selected and the
  orthogonalization is fit on 2015–2023 only; a gap of one month before the
  test window prevents overlapping forward returns from leaking across the
  split.
- **Expanding-window orthogonalization** — correlated factors are residualized
  with betas estimated on data available up to each date (no full-sample
  look-ahead).
- **Turnover-based transaction costs** — costs are charged on actual
  membership turnover per rebalance, not on a flat 100 %-turnover assumption.
- **Sanity checks** — factor displacement and cross-sectional shuffling tests
  confirm the backtest machinery itself is not the source of the returns.
- **Tested** — the research chain is covered by a unit + golden-value test
  suite (`test/`), including hand-computed backtest fixtures, determinism
  checks, and point-in-time universe edge cases.

## Pipeline

```
yfinance (batch download, retry, blacklist, checkpoints)
        │  quantmine/data_acquisition.py · pipelines/task_1.py
        ▼
cleaning & merge (ffill, dedup)          Airflow DAG: pipelines/DAG_pipeline.py
        │  pipelines/task_2.py
        ▼
factor computation (registry-driven, vectorized pandas)
        │  quantmine/factor_mining.py · pipelines/task_3.py
        ▼
IC testing: cross-sectional & time-series IC, NW t, BH/Bonferroni,
train/test split, orthogonalization        quantmine/ic_calculator.py
        ▼
quintile backtest: PIT universe, monotonicity, turnover costs,
displacement/shuffle sanity tests          quantmine/back_testing.py
        ▼
Carhart 4-factor attribution (daily, HAC)  quantmine/factor_attribution.py
```

Repository layout:

```
quantmine/          research library (importable package)
pipelines/            Airflow DAG + daily CLI tasks
test/                 pytest suite (unit + golden-value)
config.example.yaml   all pipeline parameters, documented defaults
```

## Reproducing the case study

**Market data is not included** (Yahoo Finance terms of service do not permit
redistribution). To reproduce:

1. Historical S&P 500 membership: seed the `index_membership` table once with
   `.venv/bin/python scripts/import_index_membership.py`. It imports a CSV of `ticker`,
   `start_date`, `end_date` (defaults to a local clone of
   [fja05680/sp500](https://github.com/fja05680/sp500); override with
   `SP500_MEMBERSHIP_CSV`), then reports how far that snapshot has drifted from
   Wikipedia. Review the drift and re-run with `--apply` to close it;
   `pipelines/task_0_universe.py` keeps the table current from then on. The CSV
   remains a fallback for an unseeded database.
2. Prices/volumes: `python pipelines/task_1.py --date <ds> --batch manual`
   downloads in batches with checkpointing, then `pipelines/task_2.py` cleans
   and merges.
3. Fama-French factors: download the daily FF3 and momentum CSVs from the
   [Ken French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
   into `tmp/ff3/`.
4. Run the research chain: `python pipelines/task_3.py ...` for factors, then
   the IC → backtest → attribution steps as in the quick start (or
   `python -m quantmine.ic_calculator` for the packaged train/test workflow).

For the Airflow DAG, set `QUANT_PROJECT_ROOT` and `QUANT_PYTHON_BIN` (see
`DAG_pipeline.py` docstring) and copy `airflow.cfg.example` keys into your own
config — never commit a real `airflow.cfg`.

## Runtime layout (WSL only)

Everything runs inside WSL: Postgres, the webapi, Airflow, and the data
pipeline. Two virtualenvs, both Linux:

| venv | role | sync command |
|---|---|---|
| `.venv` | research library, Airflow, the `pipelines/` tasks | `uv sync --extra data --extra db --group dev --group pipeline` |
| `webapi/.venv` | the FastAPI app | `cd webapi && uv sync --extra webapi` |

Pass those flags every time. A bare `uv sync` prunes to the default set and
silently drops `psycopg2` or `apache-airflow`, which then surfaces far from the
cause — as `permission denied for table` or as an Airflow task dying with
`python: command not found`.

`QUANT_PYTHON_BIN` must point at `.venv/bin/python`. Unset it defaults to
`python`, which does not exist in WSL at all (only `python3`), so every DAG task
fails immediately.

If the host routes traffic through a TUN-mode proxy, WSL will not inherit it and
Yahoo/Wikipedia time out at the TLS handshake while DNS still resolves (to a
`198.18.x.x` FakeIP). Point WSL at the client's HTTP port instead — `.env` here
carries `https_proxy`/`http_proxy` plus `no_proxy=localhost,127.0.0.1,::1` so
local Postgres is never proxied.

## Running it as a service (WSL)

`deploy/install-services.sh` installs four systemd **user** units — the webapi
(which serves the built frontend too, so no vite or nginx is needed) plus the
Airflow api-server, scheduler and dag-processor. `PUT /api/v1/services/{name}/autostart`
toggles each one's boot autostart from the UI.

```bash
bash deploy/install-services.sh --dry-run   # render + verify, change nothing
bash deploy/install-services.sh             # install, enable, start
```

WSL does not start with Windows, so also register the logon trigger that wakes
it: `powershell -File deploy\register-startup-task.ps1`.

**Why user units, and what it costs.** Toggling a *system* unit requires root,
which would mean granting this network-facing API a passwordless sudo rule — a
ready-made foothold if the webapi is ever compromised. User units are owned by
the same account the API runs as, so no privilege escalation is involved at all.

The price is that systemd's system and user instances are isolated: a user unit
**cannot** declare `After=postgresql.service`. Written anyway, it resolves
against a non-existent *user* unit and the ordering silently does nothing. So at
boot these services may start before Postgres is accepting connections, fail,
and be retried by `Restart=on-failure`. In practice that means a handful of
connection errors in the log for the first 10–30 seconds after boot, after which
everything settles. Nothing is lost or corrupted — Airflow simply retries.

Two further deliberate limits: only autostart is exposed, never start/stop
(`quantmine-api` is the process answering the request, so stopping it would kill
the caller with no way back in); and the unit name from the URL is resolved
against a fixed allowlist rather than passed to `systemctl`, since forwarding it
would hand over control of every unit the account owns.

Note that `auth_users` has no role column yet, so **any** logged-in user can
change autostart. That is acceptable for single-user self-hosting; tighten these
routes before adding a second user.

## Known limitations

- ~195 of 764 historical members could not be recovered from yfinance (mostly
  true delistings/acquisitions), so a residual survivorship bias remains and
  likely flatters the results slightly.
- The out-of-sample window (2024–2026) covers a single market regime.
- The long-short portfolio carries a significant 0.24 market beta; a
  beta-hedged variant is on the roadmap.
- Transaction cost model is a flat per-turnover rate; no market-impact or
  borrow-cost modeling.

## Roadmap

- [ ] Migrate storage from parquet files to PostgreSQL/DuckDB
- [ ] REST API + MCP server exposing the research chain as agent-callable tools
- [ ] RAG-based automated research reports (ChromaDB + LLM)
- [ ] Extend the Airflow DAG to cover IC testing → backtest → reporting
- [ ] Rebuild the analytics dashboard (frontend rewrite in progress)
- [ ] Scale the data layer (full US market) with PySpark
- [ ] Beta-hedged long-short variant; GARCH volatility targeting

## License

MIT
