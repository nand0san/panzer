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
- Integra un estimador de desfase de reloj (TimeOffsetEstimator).
- Delegación HTTP en binance_public_get (capa de bajo nivel).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time as _time
from typing import Any, Dict, Literal, Optional

from panzer.http import binance_public_get
from panzer.http.client import (
    BINANCE_SPOT_BASE_URL,
    BINANCE_FUTURES_UM_BASE_URL,
    BINANCE_FUTURES_CM_BASE_URL,
)
from panzer.log_manager import LogManager
from panzer.exchanges.binance.config import (
    get_spot_rate_limits,
    get_futures_um_rate_limits,
    get_futures_cm_rate_limits,
    ExchangeRateLimits,
)
from panzer.rate_limit.binance_fixed import BinanceFixedWindowLimiter
from panzer.time_sync import TimeOffsetEstimator

MarketType = Literal["spot", "um", "cm"]


# ==========================
# Logger del módulo
# ==========================

_log = LogManager(
    name="panzer.binance.public",
    folder="logs",
    filename="binance_public.log",
    level="INFO",
)


# ==========================
# Endpoints por mercado
# ==========================

_ENDPOINTS: dict[str, dict[str, str]] = {
    "spot": {
        "ping": "/api/v3/ping",
        "time": "/api/v3/time",
        "exchange_info": "/api/v3/exchangeInfo",
        "trades": "/api/v3/trades",
        "agg_trades": "/api/v3/aggTrades",
        "klines": "/api/v3/klines",
        "depth": "/api/v3/depth",
    },
    "um": {
        "ping": "/fapi/v1/ping",
        "time": "/fapi/v1/time",
        "exchange_info": "/fapi/v1/exchangeInfo",
        "trades": "/fapi/v1/trades",
        "agg_trades": "/fapi/v1/aggTrades",
        "klines": "/fapi/v1/klines",
        "depth": "/fapi/v1/depth",
    },
    "cm": {
        "ping": "/dapi/v1/ping",
        "time": "/dapi/v1/time",
        "exchange_info": "/dapi/v1/exchangeInfo",
        "trades": "/dapi/v1/trades",
        "agg_trades": "/dapi/v1/aggTrades",
        "klines": "/dapi/v1/klines",
        "depth": "/dapi/v1/depth",
    },
}


# ==========================
# Cliente público de alto nivel
# ==========================

@dataclass
class BinancePublicClient:
    """
    Cliente público de alto nivel para Binance.

    Aglutina:
    - Selección de mercado (spot / um / cm).
    - Rate limiter (BinanceFixedWindowLimiter) construido desde los límites
      dinámicos de /exchangeInfo.
    - Estimación del desfase de reloj mediante TimeOffsetEstimator.
    """
    market: MarketType = "spot"
    safety_ratio: float = 0.9
    _limits: ExchangeRateLimits | None = field(default=None, init=False, repr=False)
    _limiter: BinanceFixedWindowLimiter | None = field(default=None, init=False, repr=False)
    _time_offset: TimeOffsetEstimator = field(default_factory=TimeOffsetEstimator, init=False, repr=False)

    def __post_init__(self) -> None:
        self._log = LogManager(
            name=f"panzer.binance.public.{self.market}",
            folder="logs",
            filename=f"binance_public_{self.market}.log",
            level="INFO",
        )
        self._log.info("Inicializando BinancePublicClient(market=%s)", self.market)

        self._limits = self._load_limits()
        self._limiter = BinanceFixedWindowLimiter.from_exchange_limits(
            self._limits,
            safety_ratio=self.safety_ratio,
        )
        self._log.info(
            "Rate limiter inicializado: max_per_minute=%s safety_ratio=%.2f",
            self._limits.request_weight.limit if self._limits.request_weight else "N/A",
            self.safety_ratio,
        )

    # ==========================
    # Helpers internos
    # ==========================

    @property
    def base_url(self) -> str:
        if self.market == "spot":
            return BINANCE_SPOT_BASE_URL
        if self.market == "um":
            return BINANCE_FUTURES_UM_BASE_URL
        if self.market == "cm":
            return BINANCE_FUTURES_CM_BASE_URL
        raise ValueError(f"Mercado no soportado: {self.market!r}")

    def _load_limits(self) -> ExchangeRateLimits:
        if self.market == "spot":
            return get_spot_rate_limits()
        if self.market == "um":
            return get_futures_um_rate_limits()
        if self.market == "cm":
            return get_futures_cm_rate_limits()
        raise ValueError(f"Mercado no soportado: {self.market!r}")

    @property
    def limiter(self) -> BinanceFixedWindowLimiter:
        """
        Acceso sólo-lectura al limiter interno.

        Útil para inspeccionar métricas (used_local, last_server_used).
        """
        assert self._limiter is not None, "Limiter no inicializado"
        return self._limiter

    @property
    def time_offset(self) -> TimeOffsetEstimator:
        """
        Acceso al estimador de desfase de reloj.
        """
        return self._time_offset

    def _maybe_update_time_offset_from_response(
        self,
        endpoint: str,
        data: Any,
    ) -> None:
        """
        Si la respuesta corresponde a un /time que devuelve serverTime en ms,
        actualiza el estimador de offset.
        """
        normalized = endpoint.rstrip("/").lower()
        if not normalized.endswith("/time"):
            return

        if not isinstance(data, dict):
            return

        server_ms = data.get("serverTime")
        if not isinstance(server_ms, int):
            return

        local_now = _time()
        offset = self._time_offset.add_sample(server_ms, local_now=local_now)
        self._log.debug(
            "Actualizado offset de tiempo: server_ms=%s local_now=%.6f offset=%.6f",
            server_ms,
            local_now,
            offset,
        )

    # ==========================
    # Helpers de endpoints
    # ==========================

    def _endpoint(self, name: str) -> str:
        """
        Resuelve el path del endpoint en función del mercado.

        :param name: Nombre lógico del endpoint (ping, time, klines, etc.).
        :return: Path a usar en la petición (ej. "/api/v3/klines").
        :raises KeyError: Si el endpoint no está definido para el mercado.
        """
        try:
            return _ENDPOINTS[self.market][name]
        except KeyError as exc:
            raise KeyError(f"Endpoint '{name}' no definido para market={self.market!r}") from exc

    # ==========================
    # API genérica
    # ==========================

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        weight: int = 1,
        timeout: int = 10,
    ) -> Any:
        """
        Lanza un GET público contra Binance con rate limiting y manejo de errores.

        :param endpoint: Path de la API (ej: "/api/v3/time", "/fapi/v1/depth").
        :param params: Parámetros de query (o None).
        :param weight: REQUEST_WEIGHT estimado de la operación.
        :param timeout: Timeout en segundos para la petición HTTP.
        :return: JSON parseado o texto, según `handle_response`.
        """

        if self._time_offset.is_ready():
            now_server_sec = self._time_offset.to_server_ms() / 1000.0
            self.limiter.acquire(weight=weight, now=now_server_sec)
        else:
            self.limiter.acquire(weight=weight)

        data, headers = binance_public_get(
            base_url=self.base_url,
            endpoint=endpoint,
            params=params,
            limiter=self.limiter,
            weight=weight,
            timeout=timeout,
        )

        # Sincronizar offset de reloj si procede
        self._maybe_update_time_offset_from_response(endpoint, data)

        # Logging ligero
        self._log.debug(
            "GET %s params=%r weight=%s -> used_local=%s server_used=%s",
            endpoint,
            params,
            weight,
            self.limiter.used_local,
            self.limiter.last_server_used,
        )

        return data

    # ==========================
    # Wrappers básicos: salud / tiempo
    # ==========================

    def ping(self, *, timeout: int = 5) -> Any:
        """
        Realiza un /ping en el mercado actual.

        :param timeout: Timeout en segundos para la llamada HTTP.
        :return: Respuesta JSON o cuerpo vacío según Binance.
        """
        endpoint = self._endpoint("ping")
        return self.get(endpoint=endpoint, params=None, weight=1, timeout=timeout)

    def server_time(self, *, weight: int = 1, timeout: int = 5) -> Dict[str, Any]:
        """
        Obtiene la hora del servidor para el mercado actual y actualiza el offset interno.

        :param weight: Peso estimado de la operación para el limiter.
        :param timeout: Timeout en segundos para la llamada HTTP.
        :return: Diccionario con al menos la clave 'serverTime' en milisegundos.
        :raises RuntimeError: Si la respuesta no es un dict con serverTime.
        """
        endpoint = self._endpoint("time")
        data = self.get(endpoint=endpoint, params=None, weight=weight, timeout=timeout)

        if not isinstance(data, dict) or "serverTime" not in data:
            raise RuntimeError(f"Respuesta inesperada de /time: {data!r}")

        return data

    def ensure_time_offset_ready(
        self,
        *,
        min_samples: int = 3,
        weight: int = 1,
        timeout: int = 5,
    ) -> None:
        """
        Asegura disponer de suficientes muestras recientes de /time.

        Si el estimador no está "ready", realiza llamadas a server_time()
        hasta alcanzar al menos min_samples intentos o hasta que is_ready()
        devuelva True.

        :param min_samples: Número mínimo de iteraciones de sincronización.
        :param weight: Peso estimado de cada llamada a /time.
        :param timeout: Timeout por llamada a /time.
        """
        attempts = 0
        target_attempts = max(min_samples, 1)

        while not self._time_offset.is_ready() and attempts < target_attempts:
            self.server_time(weight=weight, timeout=timeout)
            attempts += 1

    def now_server_ms(self) -> int:
        """
        Devuelve la estimación actual de 'ahora' en tiempo de servidor (ms).

        Usa internamente el estimador de offset de tiempo.
        """
        return self._time_offset.to_server_ms()

    def acquire(self, weight: int = 1, now: float | None = None) -> None:
        if now is None:
            from time import time as _time
            now = _time()

        bucket_id = int(now // 60)

        if bucket_id != self._bucket_id:
            self._reset(bucket_id)

        projected = self._used_local + weight
        if projected > self._effective_limit:
            next_window_start = (self._bucket_id + 1) * 60
            sleep_for = max(0.0, next_window_start - now)
            self._logger.warning(
                "Límite de seguridad alcanzado (used_local=%s, weight=%s, effective_limit=%s). "
                "Durmiendo %.2f segundos.",
                self._used_local,
                weight,
                self._effective_limit,
                sleep_for,
            )
            from time import sleep as _sleep
            _sleep(sleep_for)
            # Recalcula bucket tras dormir
            from time import time as _time2
            now2 = _time2() if now is None else now + sleep_for
            new_bucket_id = int(now2 // 60)
            self._reset(new_bucket_id)

        self._used_local += weight

    # ==========================
    # Wrappers de metadatos
    # ==========================

    def exchange_info(
        self,
        symbol: str | None = None,
        *,
        timeout: int = 10,
        weight: int = 1,
    ) -> dict:
        """
        Envuelve el endpoint /exchangeInfo del mercado actual.

        :param symbol: Símbolo opcional (ej.: "BTCUSDT"). Si es None, devuelve toda la info.
        :param timeout: Timeout en segundos para la llamada HTTP.
        :param weight: Peso estimado de la operación para el limiter.
        :return: Diccionario con la información del exchange.
        """
        endpoint = self._endpoint("exchange_info")
        params: dict[str, object] | None = None

        if symbol is not None:
            params = {"symbol": symbol.upper()}

        data = self.get(endpoint=endpoint, params=params, weight=weight, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /exchangeInfo: {data!r}")

        return data

    # ==========================
    # Wrappers de trades
    # ==========================

    def trades(
        self,
        symbol: str,
        *,
        limit: int = 500,
        timeout: int = 10,
        weight: int = 1,
    ) -> list[dict]:
        """
        Obtiene la lista de trades recientes del símbolo.

        :param symbol: Par de trading (ej.: "BTCUSDT").
        :param limit: Número de trades a devolver (máx. según Binance).
        :param timeout: Timeout en segundos.
        :param weight: Peso estimado de la operación.
        :return: Lista de trades en formato dict.
        """
        endpoint = self._endpoint("trades")
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
        }
        data = self.get(endpoint=endpoint, params=params, weight=weight, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /trades: {data!r}")

        return data  # type: ignore[return-value]

    def agg_trades(
        self,
        symbol: str,
        *,
        from_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
        timeout: int = 10,
        weight: int = 1,
    ) -> list[dict]:
        """
        Obtiene trades agregados (aggTrades) para un símbolo.

        Parámetros opcionales según la API oficial:
        - fromId: ID desde el que empezar.
        - startTime / endTime: ventana temporal en ms.
        - limit: número máximo de registros.

        :param symbol: Par de trading (ej.: "BTCUSDT").
        :param from_id: ID inicial opcional.
        :param start_time: Marca de tiempo inicial (ms).
        :param end_time: Marca de tiempo final (ms).
        :param limit: Máximo de registros a devolver.
        :param timeout: Timeout en segundos.
        :param weight: Peso estimado de la operación.
        :return: Lista de aggTrades.
        """
        endpoint = self._endpoint("agg_trades")
        params: dict[str, object] = {
            "symbol": symbol.upper(),
            "limit": limit,
        }
        if from_id is not None:
            params["fromId"] = from_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        data = self.get(endpoint=endpoint, params=params, weight=weight, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /aggTrades: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Wrapper de profundidad (order book)
    # ==========================

    def depth(
        self,
        symbol: str,
        *,
        limit: int = 100,
        timeout: int = 10,
        weight: int = 1,
    ) -> dict:
        """
        Obtiene la profundidad de libro (order book) para un símbolo.

        :param symbol: Par de trading (ej.: "BTCUSDT").
        :param limit: Profundidad de niveles (ej.: 5, 10, 20, 50, 100, 500, 1000).
        :param timeout: Timeout en segundos.
        :param weight: Peso estimado de la operación.
        :return: Diccionario con bids/asks, lastUpdateId, etc.
        """
        endpoint = self._endpoint("depth")
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
        }
        data = self.get(endpoint=endpoint, params=params, weight=weight, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /depth: {data!r}")

        return data

    # ==========================
    # Wrapper de klines (velas)
    # ==========================

    def klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
        timeout: int = 10,
        weight: int = 1,
    ) -> list[list[object]]:
        """
        Obtiene velas (klines) para un símbolo e intervalo.

        Esta es la llamada "básica" a /klines. Para rangos largos con
        múltiples ventanas (más allá del limit típico de 1000) construiremos
        helpers adicionales en otro paso para que Panzer orqueste varias
        llamadas de forma segura.

        :param symbol: Par de trading (ej.: "BTCUSDT").
        :param interval: Intervalo de vela (ej.: "1m", "5m", "1h", "1d").
        :param start_time: Marca de arranque en ms (opcional).
        :param end_time: Marca de fin en ms (opcional).
        :param limit: Máximo de velas por petición.
        :param timeout: Timeout en segundos.
        :param weight: Peso estimado de la operación.
        :return: Lista de velas en el formato estándar de Binance.
        """
        endpoint = self._endpoint("klines")
        params: dict[str, object] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        data = self.get(endpoint=endpoint, params=params, weight=weight, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /klines: {data!r}")

        return data  # type: ignore[return-value]


# ==========================
# Test manual rápido
# ==========================

if __name__ == "__main__":
    client = BinancePublicClient(market="um", safety_ratio=0.8)

    # Aseguramos offset de tiempo aceptable
    client.ensure_time_offset_ready(min_samples=5)

    # Velas 1m de BTCUSDT
    klines_data = client.klines("BTCUSDT", "1m", limit=1000)
    print("Primeras 5 velas:", klines_data[:5])

    # Trades recientes
    trades_data = client.trades("BTCUSDT", limit=1000)
    print("Primeros 5 trades:", trades_data[:5])

    # Profundidad
    orderbook = client.depth("BTCUSDT", limit=500)
    print("Order book (resumen): lastUpdateId =", orderbook.get("lastUpdateId"))
