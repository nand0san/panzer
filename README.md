# Panzer: Binance API Connection Manager

Panzer is a Python-based library designed to manage Binance API interactions efficiently, handling both signed and unsigned requests. It includes features like secure credential management, automatic request signing, and a sophisticated rate-limiting and weight-control system.

## Key Features

- **Secure Credential Management**: AES-encrypted storage for API credentials. Credentials are decrypted **just-in-time** for security, meaning you never handle decrypted keys directly.
- **Request Signing**: Automatic signing for secure Binance API endpoints.
- **Rate-Limiting System**: Dynamic control of API request weight and order limits.
- **Weight Control**: Tracks and logs changes in Binance API request weights, enabling visibility of weight fluctuations.
- **Exception Handling**: Centralized error management for API requests.

## Installation

You can install Panzer via `pip`:

```bash
pip install panzer
```

Alternatively, clone the repository:

```bash
git clone https://github.com/nand0san/panzer.git
```

And then install the dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

Panzer is meant to manage all the ugly API things like, reate limits, manage secure credentials and keep track of API endpoint weights updates automatically. But also you can 
manage objects from the module if you want to.

### Rate-Limit Control
The `BinanceRateLimiter` fetches rate limits directly from Binance and adapts accordingly.

```python
from panzer.limits import BinanceRateLimiter

rate_limiter = BinanceRateLimiter()

# Show automatically fetched rate limits
rate_limiter.get()

   {'orders_limit_per_ten_seconds': 100,
    'orders_limit_per_day': 200000,
    'weight_limit_per_minute': 6000,
    'raw_limit_per_5_minutes': 61000,
    'server_time_offset': 113,
    'five_minutes_counts': {5755608: 2},
    'minutes_weights': {28778040: 21},
    'ten_seconds_orders_counts': {},
    'daily_orders_count': {}}
```

### Error Handling
Panzer offers centralized exception handling for all API requests.

```python
from panzer.errors import BinanceAPIException
from panzer.request import get

try:
    # missing symbol example
    response = get(url="https://api.binance.com/api/v3/klines", params=[("interval", "1m"),])

except BinanceAPIException as e:
    print(f"Error: {e}")

Error: BinanceAPIException(code=-1102, status_code=400): Mandatory parameter 'symbol' was not sent, was empty/null, or malformed.
```

### Manage Credentials Securely
Panzer manages creds in a very automated way. It will save securely to a file: ' "~/.panzer_creds"' for every future API request if needed.

First call to API that requires credentials, will prompt the user to enter credentials if necessary. Also can be added to the credential manager.

```python
from panzer.keys import CredentialManager

credentials = CredentialManager()
credentials.add("api_key", "your_api_key", is_sensitive=True)
```

### Retrieve Kline Data (Public API)
```python
from panzer.request import get

url = 'https://api.binance.com/api/v3/klines'
weight=2
params = {
    "symbol": "BTCUSDT",  # Par BTCUSDT
    "interval": "1m",     # Intervalo de 1 minuto
    "limit": 3            # Limitar a las últimas 5 velas
}

if rate_limiter.can_make_request(url=url, params_qty=len(params), weight=weight, is_order=False):
   
   response, headers = get(params=params, 
                           url=url,
                           full_sign=False,
                           server_time_offset=rate_limiter.server_time_offset)
   
    rate_limiter.update_from_headers(url=url, params_qty=len(params), headers=headers, expected_weight=weight)
   
print(response)
```

### Place a Test Order (Signed API)
```python
from panzer.request import post

url = 'https://api.binance.com/api/v3/order/test'
weight = 1

# timestamp is automatically added when signed call
params = {'symbol': "BTCUSDT",
          'side': "SELL",
          'type': "LIMIT",
          'timeInForce': 'GTC',
          'quantity': 0.001,
          'price': 80000,
          'recvWindow': 10000}

if rate_limiter.can_make_request(url=url, params_qty=len(params), weight=weight, is_order=False):
   
    response, headers = post(params=params, 
                            url=url,
                            full_sign=True,
                            server_time_offset=rate_limiter.server_time_offset,)
    
rate_limiter.update_from_headers(url=url, params_qty=len(params), headers=headers, expected_weight=weight)

print(response)
```

### Retrieve Trade History (Signed API)
```python
from panzer.request import get

url = 'https://api.binance.com/api/v3/myTrades'
weight = 20
params = {
    'symbol': 'BTCUSDT',                   # The trading pair
    'limit': 3,                            # Optional: Limit the number of trades to retrieve (default 500)
    'recvWindow': 5000                     # Optional: Time window for the request (default 5000 ms)
}

if rate_limiter.can_make_request(url=url, params_qty=len(params), weight=weight, is_order=False):
   
    response, headers = get(params=params, 
                            url=url,
                            full_sign=True,
                            server_time_offset=rate_limiter.server_time_offset,)
    
rate_limiter.update_from_headers(url=url, params_qty=len(params), headers=headers, expected_weight=weight)

print(response)
```

## Some classes

### 1. Setup Credentials
Panzer securely manages Binance credentials. Credentials are stored encrypted in the home directory (`~/panzer_creds`). If a credential is requested and not found, it 
will be **prompted automatically**. You can also manually add credentials if needed.

Example:
```python
from panzer.keys import CredentialManager

# Initialize the credential manager
credentials = CredentialManager()

# The keys are always decrypted just-in-time, meaning you don't need to manually decrypt them.
api_key = credentials.get("api_key", decrypt=True)  # Prompted if not available
api_secret = credentials.get("api_secret", decrypt=True)  # Prompted if not available
```

You can add credentials manually using:

```python
credentials.add("api_key", "your_api_key", is_sensitive=True)
credentials.add("api_secret", "your_api_secret", is_sensitive=True)
```

### 2. Make API Requests
Panzer simplifies both public and private Binance API requests.

#### Public API Request (Unsigned)
```python
from panzer.request import get

url = "https://api.binance.com/api/v3/ticker/price"
params = [('symbol', 'BTCUSDT')]
response, headers = get(url=url, params=params)
print(response)
```

#### Private API Request (Signed)
```python
from panzer.request import get

url = "https://api.binance.com/api/v3/account"
response, headers = get(url=url, full_sign=True)
print(response)
```

### 3. Rate Limiting
The `BinanceRateLimiter` manages rate limits dynamically to ensure compliance with Binance's rules.

```python
from panzer.limits import BinanceRateLimiter

rate_limiter = BinanceRateLimiter()

# Check if a request can be made
url = "https://api.binance.com/api/v3/account"
params = {}

if rate_limiter.can_make_request(url=url, params_qty=len(params), weight=10, is_order=False):
    print("Request can proceed")
else:
    print("Rate limit exceeded, waiting...")
```

### 4. Weight Control
Panzer includes a feature that tracks and logs changes in Binance API request weights. The **WeightControl** class stores these weights in a file (`~/.panzer_weights.csv`), and updates them automatically as API requests are made. Initially, no weights are stored, but entries will accumulate as requests are logged.

Example:
```python
from panzer.weights import WeightControl

# Initialize the weight control system
weight_control = WeightControl()

# Fetch the current weight for a specific API call
url = "https://api.binance.com/api/v3/ticker/price"
params_qty = 1  # Number of parameters in the request
weight = weight_control.get(url, params_qty)
print(f"Current weight for {url} with {params_qty} params: {weight}")

# If the weight changes, update it
new_weight = 5  # New weight as observed
weight_control.update_weight(url, params_qty, new_weight)
print(f"Updated weight for {url} to {new_weight}")
```

As you use the API, the **weights file** will accumulate more entries, logging the weights for various API calls and parameter combinations. This will help you track changes in Binance’s rate-limiting policies.

### 5. Logging
Panzer logs all API interactions for debugging purposes, with logs stored in the `logs/` directory.

```python
from panzer.logs import LogManager

logger = LogManager(filename='logs/request.log', info_level='DEBUG')
logger.info("Logging API request details")
```



## Conclusion
Panzer is a robust and secure solution for interacting with Binance's API. It provides request signing, secure credential management, built-in rate-limiting controls, and now a **weight control system** for tracking API weight changes. Install via `pip` and start using it to manage Binance API interactions efficiently.
