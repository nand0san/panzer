# CHANGELOG

## v2.2.0 (2026-03-06)

Parallel bulk requests and automatic clock synchronization.

### New features

- `parallel_get(jobs, max_workers)`: generic parallel GET with weight
  pre-reservation and automatic batching across rate limit windows.
- `bulk_trades(symbols)`: trades from multiple symbols in parallel.
- `bulk_klines(symbols, interval)`: klines from multiple symbols in parallel.
- `bulk_depth(symbols)`: order books from multiple symbols in parallel.
- `bulk_agg_trades(symbols)`: aggregate trades from multiple symbols in parallel.
- `auto_sync` parameter on `BinancePublicClient` and `BinanceClient`:
  automatically synchronizes clock with Binance on client creation
  (default True). Pass `auto_sync=False` to disable.
- `effective_limit` and `remaining` properties on `BinanceFixedWindowLimiter`
  for inspecting available weight before launching bulk requests.

### Internal

- Extracted `_execute_get()` and `_acquire()` private methods from `get()`
  to support parallel execution without duplicate acquire calls.
- Educational notebook `examples/05_parallel_bulk.ipynb`.

## v2.1.0 (2026-03-06)

Authenticated endpoints, credential management, and educational notebooks.

### New features

- `BinanceClient`: authenticated client with HMAC-SHA256 signed requests.
  Supports `account()`, `my_trades()`, `new_order()`, `cancel_order()`,
  `open_orders()`, `all_orders()`, and generic `signed_request()`.
- `CredentialManager`: 3-layer credential lookup (memory -> disk -> prompt).
  Sensitive values encrypted with AES-128-CBC tied to machine identity.
- `AesCipher`: machine-derived AES encryption (no master password).
- `BinanceRequestSigner`: automatic timestamp + HMAC-SHA256 signature.
- Auto clock sync in `signed_request()` when time offset not ready.
- Educational notebooks in `examples/`: public endpoints, credentials,
  authenticated trading, and rate limiting.

### Bug fixes

- Fixed `account()` using public endpoint resolver instead of private.
- Fixed signed requests failing with -1021 when clock not synced.
- Fixed mypy errors across all 17 source files (0 errors).
- Fixed futures test failures due to real ID gaps in aggTrades/trades.

### Internal

- All docstrings migrated from Sphinx reST to NumPy style.
- Replaced `assert` with `raise RuntimeError` in property guards.
- Added pytest unit tests for crypto, credentials, and signer modules.

## v2.0.0 (2026-03-05)

Complete rewrite of the library. Breaking changes from v1.x.

### Breaking changes

- Removed `panzer.limits.BinanceRateLimiter` -- replaced by `BinanceFixedWindowLimiter`.
- Removed `panzer.request` module (get/post) -- replaced by `panzer.http.client`.
- Removed `panzer.weights.WeightControl` -- replaced by `panzer.exchanges.binance.weights`.
- Removed `panzer.keys.CredentialManager` -- reimplemented as `panzer.credentials`.
- Single entry point: `from panzer import BinancePublicClient`.

### New features

- `BinancePublicClient`: high-level client for Spot, USDT-M Futures, COIN-M Futures.
- Automatic weight calculation per endpoint via `weights.py` tables.
- `BinanceFixedWindowLimiter`: fixed-window rate limiter synchronized with
  `X-MBX-USED-WEIGHT-1M` header. Sleeps before hitting limits.
- `TimeOffsetEstimator`: clock synchronization with Binance server.
- `LogManager`: rotating file logs per module.
- Dynamic rate limit loading from `/exchangeInfo`.

### Internal

- Flat layout: `panzer/` package with subpackages `exchanges/`, `http/`, `rate_limit/`.
- Dataclasses for models (`RateLimit`, `ExchangeRateLimits`, `BinanceAPIErrorPayload`).
- Type hints on all public functions (Python 3.10+ syntax).
- Empirical verification of rate limiting model in `tests/rate_limits_empirical.ipynb`.

## v1.0.11

- Last release of v1 architecture.
- Added requirements to setup.py.

## v1.0.7

- Basic tests done.

## v1.0.0

- Initial public release on PyPI.

## v0.1.0

- Project skeleton.
