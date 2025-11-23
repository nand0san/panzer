# panzer/exchanges/binance/public.py
"""
Cliente público de alto nivel para la API de Binance.

Características:
- Sólo usa endpoints públicos (sin API keys ni firmas).
- Soporta mercados:
    - "spot"  -> https://api.binance.com
    - "um"    -> https://fapi.binance.com (USDT-M futures)
    - "cm"    -> https://dapi.binance.com (COIN-M futures)
- Carga dinámicamente los límites REQUEST_WEIGHT desde /exchangeInfo.
- Usa BinanceFixedWindowLimiter para evitar baneos por exceso de peso.
- Delegación HTTP en binance_public_get (capa de bajo nivel).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from panzer.log_manager import LogManager
from panzer.exchanges.binance.config import (
    get_spot_rate_limits,
    get_futures_um_rate_limits,
    get_futures_cm_rate_limits,
    ExchangeRateLimits,
)
from panzer.rate_limit.binance_fixed import BinanceFixedWindowLimiter
from panzer.http.client import (
    binance_public_get,
    BINANCE_SPOT_BASE_URL,
    BINANCE_FUTURES_UM_BASE_URL,
    BINANCE_FUTURES_CM_BASE_URL,
)

MarketType = Literal["spot", "um", "cm"]


# ==========================
# Configuración por mercado
# ==========================


@dataclass
class _MarketConfig:
    market: MarketType
    base_url: str
    time_endpoint: str
    exchange_info_endpoint: str
    klines_endpoint: str


_MARKETS: Dict[MarketType, _MarketConfig] = {
    "spot": _MarketConfig(
        market="spot",
        base_url=BINANCE_SPOT_BASE_URL,
        time_endpoint="/api/v3/time",
        exchange_info_endpoint="/api/v3/exchangeInfo",
        klines_endpoint="/api/v3/klines",
    ),
    "um": _MarketConfig(
        market="um",
        base_url=BINANCE_FUTURES_UM_BASE_URL,
        time_endpoint="/fapi/v1/time",
        exchange_info_endpoint="/fapi/v1/exchangeInfo",
        klines_endpoint="/fapi/v1/klines",
    ),
    "cm": _MarketConfig(
        market="cm",
        base_url=BINANCE_FUTURES_CM_BASE_URL,
        time_endpoint="/dapi/v1/time",
        exchange_info_endpoint="/dapi/v1/exchangeInfo",
        klines_endpoint="/dapi/v1/klines",
    ),
}


def _load_limits_for_market(market: MarketType) -> ExchangeRateLimits:
    """
    Carga los límites REQUEST_WEIGHT adecuados al mercado elegido.
    """
    if market == "spot":
        return get_spot_rate_limits()
    if market == "um":
        return get_futures_um_rate_limits()
    if market == "cm":
        return get_futures_cm_rate_limits()
    raise ValueError(f"Mercado no soportado: {market}")


# ==========================
# Cliente público
# ==========================


class BinancePublicClient:
    """
    Cliente público de alto nivel para Binance.

    Uso típico:

        client = BinancePublicClient(market="spot")
        server_time = client.get_time()
        info = client.get_exchange_info()
        kl = client.get_klines("BTCUSDT", "1m", limit=1000)
    """

    def __init__(
        self,
        market: MarketType = "spot",
        safety_ratio: float = 0.9,
    ) -> None:
        """
        :param market:
            Mercado objetivo:
                - "spot":   Binance Spot (api.binance.com)
                - "um":     USDT-M futures (fapi.binance.com)
                - "cm":     COIN-M futures (dapi.binance.com)
        :param safety_ratio:
            Factor de seguridad para el rate limiter en (0, 1].
        """
        if market not in _MARKETS:
            raise ValueError(f"Mercado no soportado: {market}")

        self.market: MarketType = market
        self.config: _MarketConfig = _MARKETS[market]

        # Logger específico del cliente
        self._log = LogManager(
            name=f"panzer.binance.{market}",
            folder="logs",
            filename=f"binance_{market}.log",
            level="INFO",
        )

        # Carga dinámica de límites desde /exchangeInfo
        limits = _load_limits_for_market(market)
        self._log.info(
            f"Market={market} REQUEST_WEIGHT limit: {limits.request_weight}"
        )

        # Rate limiter ajustado al límite del mercado
        self._limiter = BinanceFixedWindowLimiter.from_exchange_limits(
            limits,
            safety_ratio=safety_ratio,
        )

        self._log.info(
            f"BinancePublicClient inicializado para market={market}, "
            f"base_url={self.config.base_url}, safety_ratio={safety_ratio}"
        )

    # ==========================
    # Métodos auxiliares internos
    # ==========================

    def _get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        weight: int = 1,
        timeout: int = 10,
    ) -> Any:
        """
        Helper interno para hacer GETs públicos con rate limiting.
        """
        self._log.debug(
            f"GET {self.config.base_url}{endpoint} "
            f"params={params} weight={weight} used_local={self._limiter.used_local}"
        )

        data, headers = binance_public_get(
            base_url=self.config.base_url,
            endpoint=endpoint,
            params=params,
            limiter=self._limiter,
            weight=weight,
            timeout=timeout,
        )

        self._log.debug(
            f"RESP {self.config.base_url}{endpoint} "
            f"used_local={self._limiter.used_local} "
            f"server_used={self._limiter.last_server_used}"
        )

        return data

    # ==========================
    # Métodos públicos
    # ==========================

    def get_time(self, timeout: int = 5) -> int:
        """
        Devuelve el tiempo de servidor en milisegundos desde epoch.

        Endpoint:
        - Spot: /api/v3/time
        - Futuros UM: /fapi/v1/time
        - Futuros CM: /dapi/v1/time
        """
        data = self._get(
            endpoint=self.config.time_endpoint,
            params=None,
            weight=1,
            timeout=timeout,
        )
        # Todas las variantes devuelven {"serverTime": <int>}
        server_time = int(data["serverTime"])
        self._log.debug(f"serverTime={server_time}")
        return server_time

    def get_exchange_info(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Devuelve la información de exchange completa para el mercado actual.

        Para Spot incluye símbolos, filtros, rateLimits, etc.
        Para Futuros incluye símbolos y metadatos específicos del mercado.
        """
        # Este endpoint es pesado; con peso 10 nos mantenemos conservadores.
        data = self._get(
            endpoint=self.config.exchange_info_endpoint,
            params=None,
            weight=10,
            timeout=timeout,
        )
        return data

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        timeout: int = 10,
    ) -> list[list[Any]]:
        """
        Recupera velas (klines) para un símbolo e intervalo.

        :param symbol:
            Par de trading en formato de Binance (ej: "BTCUSDT").
        :param interval:
            Intervalo de vela (ej: "1m", "5m", "1h", "1d").
        :param limit:
            Número máximo de velas a devolver (1..1000 típicamente).
        :param start_time:
            Epoch en ms de inicio (opcional).
        :param end_time:
            Epoch en ms de fin (opcional).
        :param timeout:
            Timeout en segundos.
        :return:
            Lista de velas, cada una es una lista con el formato estándar
            de klines de Binance.
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        # Peso típico de klines suele ser bajo; usamos 1 por defecto.
        data = self._get(
            endpoint=self.config.klines_endpoint,
            params=params,
            weight=1,
            timeout=timeout,
        )

        # La API devuelve una lista de listas
        if not isinstance(data, list):
            raise TypeError(f"Respuesta inesperada para klines: {type(data)}")

        self._log.debug(
            f"klines: symbol={symbol}, interval={interval}, "
            f"limit={limit}, received={len(data)}"
        )

        return data


# ==========================
# Test manual rápido
# ==========================

if __name__ == "__main__":
    """
    Pruebas rápidas del BinancePublicClient:

    1) Crear cliente SPOT.
    2) Obtener serverTime.
    3) Obtener exchangeInfo (tamaño de symbols).
    4) Obtener algunas velas 1m de BTCUSDT.
    """

    client = BinancePublicClient(market="spot", safety_ratio=0.9)

    print("== get_time() ==")
    server_time = client.get_time()
    print(f"serverTime={server_time}")

    print("\n== get_exchange_info() ==")
    exch = client.get_exchange_info()
    print(f"symbols count={len(exch.get('symbols', []))}")

    print("\n== get_klines('BTCUSDT','1m', limit=5) ==")
    kl = client.get_klines("BTCUSDT", "1m", limit=5)
    print(f"received klines={len(kl)}")
    for row in kl:
        print(row)
