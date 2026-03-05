# CHANGELOG

## v2.0.0 (unreleased)

Complete rewrite of the library. Breaking changes from v1.x.

### Breaking changes

- Removed `panzer.limits.BinanceRateLimiter` — replaced by `BinanceFixedWindowLimiter`.
- Removed `panzer.request` module (get/post) — replaced by `panzer.http.client`.
- Removed `panzer.weights.WeightControl` — replaced by `panzer.exchanges.binance.weights`.
- Removed `panzer.keys.CredentialManager` — signed requests not yet reimplemented.
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
