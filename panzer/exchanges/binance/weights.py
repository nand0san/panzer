# panzer/exchanges/binance/weights.py
"""
Tabla de referencia de pesos (REQUEST_WEIGHT) por endpoint de Binance.

Fuente: documentacion oficial de Binance (developers.binance.com), marzo 2026.

Estructura:
- Cada mercado (spot, um, cm) tiene su propio diccionario de pesos.
- Los pesos pueden ser fijos (int) o variables segun parametros (callable).
- Las funciones de peso variable reciben los params del request y devuelven
  el peso estimado.

Mantenimiento:
- Actualizar cuando Binance cambie pesos (revisar /exchangeInfo y docs).
- Los pesos variables (depth, klines, tickers) dependen del parametro `limit`
  o de si se pasa `symbol`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ==========================
# Helpers de peso variable
# ==========================


def _spot_depth_weight(params: dict[str, Any] | None = None) -> int:
    """
    Peso de GET /api/v3/depth segun el parametro limit.

    ===== ======
    limit  peso
    ===== ======
    1-100     5
    101-500  25
    501-1000 50
    1001-5000 250
    ===== ======
    """
    limit = int((params or {}).get("limit", 100))
    if limit <= 100:
        return 5
    if limit <= 500:
        return 25
    if limit <= 1000:
        return 50
    return 250


def _spot_trades_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de GET ``/api/v3/trades``: siempre 25."""
    return 25


def _spot_ticker_24hr_weight(params: dict[str, Any] | None = None) -> int:
    """
    Peso de GET /api/v3/ticker/24hr.

    - Con symbol unico: 2
    - Sin symbol (todos): 80
    - Con symbols (1-20): 2
    - Con symbols (21-100): 40
    - Con symbols (101+): 80
    """
    if params is None:
        return 80
    if "symbol" in params:
        return 2
    symbols = params.get("symbols")
    if symbols is None:
        return 80
    count = len(symbols) if isinstance(symbols, list) else 1
    if count <= 20:
        return 2
    if count <= 100:
        return 40
    return 80


def _spot_ticker_price_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de GET /api/v3/ticker/price: 2 con symbol, 4 sin symbol."""
    if params and "symbol" in params:
        return 2
    return 4


def _spot_ticker_book_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de GET /api/v3/ticker/bookTicker: 2 con symbol, 4 sin symbol."""
    if params and "symbol" in params:
        return 2
    return 4


def _futures_depth_weight(params: dict[str, Any] | None = None) -> int:
    """
    Peso de GET /fapi/v1/depth y /dapi/v1/depth.

    ===== ====
    limit peso
    ===== ====
    5-50     2
    100      5
    500     10
    1000    20
    ===== ====
    """
    limit = int((params or {}).get("limit", 20))
    if limit <= 50:
        return 2
    if limit <= 100:
        return 5
    if limit <= 500:
        return 10
    return 20


def _futures_klines_weight(params: dict[str, Any] | None = None) -> int:
    """
    Peso de GET /fapi/v1/klines y /dapi/v1/klines.

    ========= ====
    limit     peso
    ========= ====
    1-99         1
    100-499      2
    500-1000     5
    >1000       10
    ========= ====
    """
    limit = int((params or {}).get("limit", 500))
    if limit < 100:
        return 1
    if limit < 500:
        return 2
    if limit <= 1000:
        return 5
    return 10


def _futures_ticker_24hr_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de ``ticker/24hr`` en futuros: 1 con symbol, 40 sin symbol."""
    if params and "symbol" in params:
        return 1
    return 40


def _futures_ticker_price_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de ``ticker/price`` en futuros: 1 con symbol, 2 sin symbol."""
    if params and "symbol" in params:
        return 1
    return 2


def _futures_ticker_book_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de ``ticker/bookTicker`` en futuros: 2 con symbol, 5 sin symbol."""
    if params and "symbol" in params:
        return 2
    return 5


def _futures_mark_price_weight(params: dict[str, Any] | None = None) -> int:
    """Peso de ``premiumIndex``: 1 con symbol, 10 sin symbol."""
    if params and "symbol" in params:
        return 1
    return 10


# ==========================
# Tipo para entradas de peso
# ==========================

# Un peso puede ser un int fijo o un callable que recibe params y devuelve int.
WeightEntry = int | Callable[[dict[str, Any] | None], int]


# ==========================
# Tablas de pesos por mercado
# ==========================

# Clave: path del endpoint (sin base_url).
# Valor: int fijo o callable(params) -> int.

SPOT_WEIGHTS: dict[str, WeightEntry] = {
    # --- General ---
    "/api/v3/ping": 1,
    "/api/v3/time": 1,
    "/api/v3/exchangeInfo": 20,
    # --- Market data ---
    "/api/v3/depth": _spot_depth_weight,
    "/api/v3/trades": 25,
    "/api/v3/historicalTrades": 25,
    "/api/v3/aggTrades": 4,
    "/api/v3/klines": 2,
    "/api/v3/uiKlines": 2,
    "/api/v3/avgPrice": 2,
    "/api/v3/ticker/24hr": _spot_ticker_24hr_weight,
    "/api/v3/ticker/tradingDay": 4,  # 4 por symbol, max 200
    "/api/v3/ticker/price": _spot_ticker_price_weight,
    "/api/v3/ticker/bookTicker": _spot_ticker_book_weight,
    "/api/v3/ticker": 4,  # 4 por symbol, max 200
    # --- Trading ---
    "/api/v3/order": 1,  # POST y DELETE
    "/api/v3/order/test": 1,  # 20 si computeCommissionRates
    "/api/v3/openOrders": 3,
    "/api/v3/allOrders": 20,
    "/api/v3/order/oco": 1,
    "/api/v3/orderList": 2,
    "/api/v3/allOrderList": 20,
    "/api/v3/openOrderList": 3,
    "/api/v3/order/cancelReplace": 1,
    # --- Account ---
    "/api/v3/account": 10,
    "/api/v3/myTrades": 10,
    "/api/v3/rateLimit/order": 40,
}


FUTURES_UM_WEIGHTS: dict[str, WeightEntry] = {
    # --- General ---
    "/fapi/v1/ping": 1,
    "/fapi/v1/time": 1,
    "/fapi/v1/exchangeInfo": 1,
    # --- Market data ---
    "/fapi/v1/depth": _futures_depth_weight,
    "/fapi/v1/trades": 5,
    "/fapi/v1/aggTrades": 20,
    "/fapi/v1/klines": _futures_klines_weight,
    "/fapi/v1/premiumIndex": _futures_mark_price_weight,
    "/fapi/v1/fundingRate": 1,  # limite aparte: 500 req/5min/IP
    "/fapi/v1/ticker/24hr": _futures_ticker_24hr_weight,
    "/fapi/v1/ticker/price": _futures_ticker_price_weight,
    "/fapi/v1/ticker/bookTicker": _futures_ticker_book_weight,
    "/fapi/v1/openInterest": 1,
}


FUTURES_CM_WEIGHTS: dict[str, WeightEntry] = {
    # --- General ---
    "/dapi/v1/ping": 1,
    "/dapi/v1/time": 1,
    "/dapi/v1/exchangeInfo": 1,
    # --- Market data ---
    "/dapi/v1/depth": _futures_depth_weight,
    "/dapi/v1/trades": 5,
    "/dapi/v1/aggTrades": 20,
    "/dapi/v1/klines": _futures_klines_weight,
    "/dapi/v1/premiumIndex": 10,  # siempre devuelve todos los symbols
    "/dapi/v1/fundingRate": 1,
    "/dapi/v1/ticker/24hr": _futures_ticker_24hr_weight,
    "/dapi/v1/ticker/price": _futures_ticker_price_weight,
    "/dapi/v1/ticker/bookTicker": _futures_ticker_book_weight,
    "/dapi/v1/openInterest": 1,
}


# ==========================
# Mapa global por mercado
# ==========================

WEIGHTS_BY_MARKET: dict[str, dict[str, WeightEntry]] = {
    "spot": SPOT_WEIGHTS,
    "um": FUTURES_UM_WEIGHTS,
    "cm": FUTURES_CM_WEIGHTS,
}


# ==========================
# Funcion de consulta
# ==========================


def get_weight(
    market: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> int:
    """
    Devuelve el peso estimado para un endpoint y mercado dados.

    Parameters
    ----------
    market : str
        Mercado: "spot", "um" o "cm".
    endpoint : str
        Path del endpoint (ej: "/api/v3/depth").
    params : dict[str, Any] | None
        Parametros del request. Necesarios para pesos variables.

    Returns
    -------
    int
        Peso estimado. Si el endpoint no esta en la tabla, devuelve 1
        como valor conservador por defecto.
    """
    weights = WEIGHTS_BY_MARKET.get(market, {})
    entry = weights.get(endpoint, 1)
    if callable(entry):
        return entry(params)
    return entry
