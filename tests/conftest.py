"""
Fixtures compartidas para tests empiricos contra la API de Binance.

Estrategia de ahorro de llamadas:
- Toda la obtencion de datos ocurre UNA VEZ por sesion de pytest.
- Un unico dict ``_all_market_data`` cachea clientes, simbolos y respuestas.
- Fixtures parametrizadas sobre mercados ("spot", "um", "cm") reutilizan
  los datos cacheados sin repetir llamadas HTTP.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import pytest

from panzer import BinancePublicClient
from panzer.errors import BinanceAPIException


def pytest_configure(config: pytest.Config) -> None:
    """Registra markers personalizados."""
    config.addinivalue_line(
        "markers",
        "empirical: tests que requieren conexion a la API real de Binance",
    )


# =====================================================================
# Constantes
# =====================================================================

TICK_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}

MARKETS: list[str] = ["spot", "um", "cm"]
FUTURES_MARKETS: list[str] = ["um", "cm"]


# =====================================================================
# Modelo de datos cacheados
# =====================================================================

@dataclass
class MarketTestData:
    """Datos obtenidos de un mercado, cacheados para toda la sesion."""

    market: str
    client: BinancePublicClient
    primary_symbol: str
    alt_symbol: str
    klines_15m: list[list[object]]
    klines_15m_alt: list[list[object]]
    agg_trades: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    depth: dict[str, Any]


@dataclass
class FuturesTestData:
    """Datos de derivados de un mercado futures, cacheados para toda la sesion."""

    market: str
    client: BinancePublicClient
    primary_symbol: str
    open_interest: dict[str, Any]
    open_interest_hist: list[dict[str, Any]]
    premium_index: dict[str, Any] | list[dict[str, Any]]
    funding_rate_history: list[dict[str, Any]]
    funding_info: list[dict[str, Any]]
    force_orders: list[dict[str, Any]]


# =====================================================================
# Helpers internos
# =====================================================================

def _pick_symbols(
    info: dict[str, Any],
    market: str,
    rng: random.Random,
) -> tuple[str, str]:
    """Elige un simbolo principal (fijo, liquido) y uno aleatorio."""
    if market == "cm":
        primary = "BTCUSD_PERP"
        all_symbols = [
            s["symbol"]
            for s in info.get("symbols", [])
            if s.get("contractStatus") == "TRADING"
            and s["symbol"].endswith("_PERP")
            and s["symbol"] != primary
        ]
    else:
        primary = "BTCUSDT"
        all_symbols = [
            s["symbol"]
            for s in info.get("symbols", [])
            if s.get("status") == "TRADING"
            and s.get("quoteAsset") == "USDT"
            and s["symbol"] != primary
        ]

    alt = rng.choice(all_symbols) if all_symbols else primary
    return primary, alt


def _build_market_data(market: str, rng: random.Random) -> MarketTestData:
    """Crea un cliente, elige simbolos y descarga todos los datos necesarios."""
    client = BinancePublicClient(market=market, safety_ratio=0.9)
    info = client.exchange_info()
    primary, alt = _pick_symbols(info, market, rng)

    return MarketTestData(
        market=market,
        client=client,
        primary_symbol=primary,
        alt_symbol=alt,
        klines_15m=client.klines(primary, "15m", limit=100),
        klines_15m_alt=client.klines(alt, "15m", limit=50),
        agg_trades=client.agg_trades(primary, limit=200),
        trades=client.trades(primary, limit=200),
        depth=client.depth(primary, limit=100),
    )


def _build_futures_data(market: str, rng: random.Random) -> FuturesTestData:
    """Crea un cliente futures y descarga datos de derivados."""
    client = BinancePublicClient(market=market, safety_ratio=0.9)
    info = client.exchange_info()
    primary, _ = _pick_symbols(info, market, rng)

    return FuturesTestData(
        market=market,
        client=client,
        primary_symbol=primary,
        open_interest=client.open_interest(primary),
        open_interest_hist=client.open_interest_hist(primary, "5m", limit=10),
        premium_index=client.premium_index(primary),
        funding_rate_history=client.funding_rate_history(primary, limit=10),
        funding_info=client.funding_info(),
        force_orders=_safe_force_orders(client, primary),
    )


def _safe_force_orders(
    client: BinancePublicClient,
    symbol: str,
) -> list[dict[str, Any]]:
    """force_orders requiere API key en futuros; devuelve [] si falla auth."""
    try:
        return client.force_orders(symbol, limit=10)
    except BinanceAPIException:
        return []


# =====================================================================
# Fixtures de sesion
# =====================================================================

@pytest.fixture(scope="session")
def _all_market_data() -> dict[str, MarketTestData]:
    """Obtiene TODOS los datos de todos los mercados una sola vez."""
    rng = random.Random()
    data: dict[str, MarketTestData] = {}
    for market in MARKETS:
        md = _build_market_data(market, rng)
        print(f"\n  [{market}] primary={md.primary_symbol}  alt={md.alt_symbol}")
        data[market] = md
    return data


@pytest.fixture(scope="session", params=MARKETS)
def market_data(request: pytest.FixtureRequest, _all_market_data: dict) -> MarketTestData:
    """Un MarketTestData por mercado; el test se ejecuta 3 veces."""
    return _all_market_data[request.param]


@pytest.fixture(scope="session")
def spot_data(_all_market_data: dict) -> MarketTestData:
    return _all_market_data["spot"]


@pytest.fixture(scope="session")
def um_data(_all_market_data: dict) -> MarketTestData:
    return _all_market_data["um"]


@pytest.fixture(scope="session")
def cm_data(_all_market_data: dict) -> MarketTestData:
    return _all_market_data["cm"]


@pytest.fixture(scope="session")
def _all_futures_data() -> dict[str, FuturesTestData]:
    """Obtiene datos de derivados de todos los mercados futures una sola vez."""
    rng = random.Random()
    data: dict[str, FuturesTestData] = {}
    for market in FUTURES_MARKETS:
        fd = _build_futures_data(market, rng)
        print(f"\n  [{market}/futures] primary={fd.primary_symbol}")
        data[market] = fd
    return data


@pytest.fixture(scope="session", params=FUTURES_MARKETS)
def futures_data(request: pytest.FixtureRequest, _all_futures_data: dict) -> FuturesTestData:
    """Un FuturesTestData por mercado futures; el test se ejecuta 2 veces (um, cm)."""
    return _all_futures_data[request.param]


@pytest.fixture(scope="session")
def spot_interval_klines(spot_data: MarketTestData) -> dict[str, list]:
    """Klines en varios intervalos (solo spot, limit bajo para ahorrar)."""
    client = spot_data.client
    sym = spot_data.primary_symbol
    intervals = ["1m", "1h", "1d", "1w"]
    return {iv: client.klines(sym, iv, limit=5) for iv in intervals}
