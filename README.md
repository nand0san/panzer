# Panzer

Python library for managing Binance REST API connections with automatic rate limiting.

## Features

- **Multi-market support**: Spot, USDT-M Futures, COIN-M Futures.
- **Automatic rate limiting**: Fixed-window limiter synchronized with Binance's `X-MBX-USED-WEIGHT-1M` header. Sleeps before hitting limits instead of getting banned.
- **Dynamic weight calculation**: Endpoint weights loaded from `weights.py` and adjusted by parameters (e.g., `depth` limit, `klines` limit).
- **Clock synchronization**: Estimates server time offset via `/time` endpoint samples.
- **Centralized error handling**: `BinanceAPIException` with parsed error codes and messages.
- **Rotating file logs**: One log file per module in `logs/`, with configurable rotation.

## Installation

```bash
pip install panzer
```

Or from source:

```bash
git clone https://github.com/nand0san/panzer.git
cd panzer
pip install -e .
```

Requires Python >= 3.11. Only runtime dependency: `requests`.

## Quick Start

```python
from panzer import BinancePublicClient

# Create a client (loads rate limits from /exchangeInfo automatically)
client = BinancePublicClient(market="spot", safety_ratio=0.9)

# Synchronize clock with Binance server (recommended before heavy usage)
client.ensure_time_offset_ready(min_samples=3)

# Public endpoints — weights are calculated automatically
klines = client.klines("BTCUSDT", "1m", limit=500)
trades = client.trades("BTCUSDT", limit=100)
book = client.depth("BTCUSDT", limit=100)
info = client.exchange_info()
```

### Supported Markets

```python
spot = BinancePublicClient(market="spot")    # https://api.binance.com
um   = BinancePublicClient(market="um")      # https://fapi.binance.com
cm   = BinancePublicClient(market="cm")      # https://dapi.binance.com
```

## Available Endpoints

All wrapper methods share `timeout` (seconds, default 10) and return parsed JSON.

| Method | Description | Key parameters |
|--------|-------------|----------------|
| `ping()` | Test connectivity | |
| `server_time()` | Server time (also updates clock sync) | |
| `exchange_info(symbol=)` | Exchange metadata and rate limits | `symbol`: optional, single symbol filter |
| `klines(symbol, interval)` | Candlestick data | `limit` (default 500), `start_time`, `end_time` (ms) |
| `trades(symbol)` | Recent trades | `limit` (default 500) |
| `agg_trades(symbol)` | Compressed/aggregate trades | `limit`, `from_id`, `start_time`, `end_time` |
| `depth(symbol)` | Order book | `limit` (default 100; affects weight) |

### Using `get()` for any endpoint

The wrapper methods above cover the most common endpoints. For anything else
(e.g., `historicalTrades`, `openInterest`, `ticker/24hr`), use `get()` directly
with the endpoint path:

```python
# Spot 24h ticker — no wrapper needed
ticker = client.get("/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"})

# Futures mark price
mark = client.get("/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"})
```

Weights are calculated automatically from `weights.py` tables. If an endpoint
is not in the table, it defaults to weight 1. You can also override manually:

```python
data = client.get("/api/v3/depth", params={"symbol": "BTCUSDT", "limit": 5000}, weight=250)
```

## Rate Limiting

The limiter works **transparently**. When accumulated weight approaches the limit
(controlled by `safety_ratio`), the client **sleeps** until the next minute window.
This means your code may block for up to ~60 seconds — it won't raise an error,
it just waits.

```python
# safety_ratio=0.9 means sleep when reaching 90% of the limit (e.g., 5400/6000 for spot)
client = BinancePublicClient(market="spot", safety_ratio=0.9)

# Inspect limiter state at any time
print(client.limiter.used_local)        # Weight used in current window
print(client.limiter.last_server_used)  # Last value from X-MBX-USED-WEIGHT-1M
print(client.limiter.max_per_minute)    # Limit from /exchangeInfo (e.g., 6000)
```

The limiter synchronizes with Binance's `X-MBX-USED-WEIGHT-1M` response header
after every request, so it stays accurate even if other processes share the same IP.

## Clock Synchronization

`ensure_time_offset_ready()` calls `/time` multiple times to estimate the offset
between your local clock and Binance's server. This is recommended before loops
that run many requests, because the limiter uses server time to align with
Binance's rate limit windows.

```python
client.ensure_time_offset_ready(min_samples=3)

# After sync, you can get the estimated server time
server_ms = client.now_server_ms()
```

If you skip this step, the limiter still works — it just uses your local clock,
which may be slightly off from Binance's window boundaries.

## Error Handling

```python
from panzer.errors import BinanceAPIException

try:
    client.klines("INVALID", "1m")
except BinanceAPIException as e:
    print(e.status_code)       # 400
    print(e.error_payload.code) # -1121
    print(e.error_payload.msg)  # "Invalid symbol."
```

All API errors (HTTP 4xx/5xx and Binance-specific error codes) raise
`BinanceAPIException` with the parsed error payload when available.

## Logging

Each module writes to its own rotating log file in `logs/`:

```
logs/
  binance_public_spot.log
  binance_fixed_limiter.log
  errors.log
  ...
```

Logs also print to stdout. The `logs/` directory is created automatically
and is gitignored.

## Architecture

```
panzer/
  __init__.py                   # Exports BinancePublicClient
  errors.py                     # BinanceAPIException, handle_response
  log_manager.py                # LogManager (rotating file + stdout)
  time_sync.py                  # TimeOffsetEstimator
  exchanges/binance/
    config.py                   # Parses /exchangeInfo rate limits
    public.py                   # BinancePublicClient (high-level)
    weights.py                  # Endpoint weight tables per market
  http/
    client.py                   # Low-level HTTP + header sync
  rate_limit/
    binance_fixed.py            # Fixed-window rate limiter
```

## License

MIT
