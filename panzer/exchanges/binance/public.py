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

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from time import time as _time
from typing import Any, Literal

from panzer.exchanges.binance.config import (
    ExchangeRateLimits,
    get_futures_cm_rate_limits,
    get_futures_um_rate_limits,
    get_spot_rate_limits,
)
from panzer.exchanges.binance.weights import get_weight
from panzer.http import binance_public_get
from panzer.http.client import (
    BINANCE_FUTURES_CM_BASE_URL,
    BINANCE_FUTURES_UM_BASE_URL,
    BINANCE_SPOT_BASE_URL,
)
from panzer.log_manager import LogManager
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
        "force_orders": "/fapi/v1/forceOrders",
    },
    "cm": {
        "ping": "/dapi/v1/ping",
        "time": "/dapi/v1/time",
        "exchange_info": "/dapi/v1/exchangeInfo",
        "trades": "/dapi/v1/trades",
        "agg_trades": "/dapi/v1/aggTrades",
        "klines": "/dapi/v1/klines",
        "depth": "/dapi/v1/depth",
        "force_orders": "/dapi/v1/forceOrders",
    },
}


# ==========================
# Duracion de cada intervalo de vela en milisegundos
# ==========================

TICK_INTERVAL_MS: dict[str, int] = {
    '1s': 1_000,
    '1m': 60_000,
    '3m': 180_000,
    '5m': 300_000,
    '15m': 900_000,
    '30m': 1_800_000,
    '1h': 3_600_000,
    '2h': 7_200_000,
    '4h': 14_400_000,
    '6h': 21_600_000,
    '8h': 28_800_000,
    '12h': 43_200_000,
    '1d': 86_400_000,
    '3d': 259_200_000,
    '1w': 604_800_000,
    '1M': 2_592_000_000,
}


# ==========================
# Cliente público de alto nivel
# ==========================


@dataclass
class BinancePublicClient:
    """
    Cliente publico de alto nivel para la API de Binance.

    Integra seleccion de mercado, rate limiting automatico y
    sincronizacion de reloj en una interfaz unificada. Solo usa
    endpoints publicos (sin API key ni firma).

    Parameters
    ----------
    market : MarketType
        Mercado: ``"spot"``, ``"um"`` (USDT-M) o ``"cm"`` (COIN-M).
    safety_ratio : float
        Factor de seguridad para el rate limiter (``(0, 1]``).
    auto_sync : bool
        Si ``True``, sincroniza el reloj con Binance al instanciar.

    Attributes
    ----------
    limiter : BinanceFixedWindowLimiter
        Rate limiter configurado con los limites de ``/exchangeInfo``.
    time_offset : TimeOffsetEstimator
        Estimador de desfase de reloj local vs. servidor.
    base_url : str
        URL base del mercado seleccionado.

    See Also
    --------
    BinanceClient : Extiende este cliente con endpoints autenticados.

    Examples
    --------
    >>> client = BinancePublicClient(market="spot")
    >>> klines = client.klines("BTCUSDT", "1h", limit=100)
    >>> books = client.bulk_depth(["BTCUSDT", "ETHUSDT"])
    """

    market: MarketType = "spot"
    safety_ratio: float = 0.9
    auto_sync: bool = True
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

        if self.auto_sync:
            self.ensure_time_offset_ready(min_samples=3)
            self._log.info(
                "Reloj sincronizado: offset=%.0f ms",
                self._time_offset.current_offset() * 1000,
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
        Rate limiter interno (solo lectura).

        Permite inspeccionar metricas como ``used_local``,
        ``last_server_used`` y ``remaining``.

        Raises
        ------
        RuntimeError
            Si se accede antes de que ``__post_init__`` lo inicialice.
        """
        if self._limiter is None:
            raise RuntimeError("Limiter no inicializado")
        return self._limiter

    @property
    def time_offset(self) -> TimeOffsetEstimator:
        """Estimador de desfase de reloj local vs. servidor."""
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
        Resuelve el path del endpoint en funcion del mercado.

        Parameters
        ----------
        name : str
            Nombre logico del endpoint (ping, time, klines, etc.).

        Returns
        -------
        str
            Path a usar en la peticion (ej. ``"/api/v3/klines"``).

        Raises
        ------
        KeyError
            Si el endpoint no esta definido para el mercado.
        """
        try:
            return _ENDPOINTS[self.market][name]
        except KeyError as exc:
            raise KeyError(f"Endpoint '{name}' no definido para market={self.market!r}") from exc

    # ==========================
    # API genérica
    # ==========================

    def _execute_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,

        weight: int = 1,
        timeout: int = 10,
    ) -> Any:
        """
        GET sin acquire -- usado internamente por ``get()`` y ``parallel_get()``.

        Realiza la peticion HTTP, sincroniza headers del limiter y actualiza
        el offset de reloj si procede.
        """
        data, _headers = binance_public_get(
            base_url=self.base_url,
            endpoint=endpoint,
            params=params,
            limiter=self.limiter,
            weight=weight,
            timeout=timeout,
        )
        self._maybe_update_time_offset_from_response(endpoint, data)

        self._log.debug(
            "GET %s params=%r weight=%s -> used_local=%s server_used=%s",
            endpoint,
            params,
            weight,
            self.limiter.used_local,
            self.limiter.last_server_used,
        )
        return data

    def _acquire(self, weight: int) -> None:
        """Reserva peso teniendo en cuenta el offset de reloj si esta listo."""
        if self._time_offset.is_ready():
            now_server_sec = self._time_offset.to_server_ms() / 1000.0
            self.limiter.acquire(weight=weight, now=now_server_sec)
        else:
            self.limiter.acquire(weight=weight)

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,

        weight: int | None = None,
        timeout: int = 10,
    ) -> Any:
        """
        Lanza un GET publico contra Binance con rate limiting y manejo de errores.

        Parameters
        ----------
        endpoint : str
            Path de la API (ej: ``"/api/v3/time"``, ``"/fapi/v1/depth"``).
        params : dict[str, Any] | None
            Parametros de query (o None).
        weight : int | None
            REQUEST_WEIGHT de la operacion. Si es None, se calcula
            automaticamente desde weights.py.
        timeout : int
            Timeout en segundos para la peticion HTTP.

        Returns
        -------
        Any
            JSON parseado o texto, segun ``handle_response``.
        """
        if weight is None:
            weight = get_weight(self.market, endpoint, params)

        self._acquire(weight)
        return self._execute_get(endpoint, params, weight=weight, timeout=timeout)

    # ==========================
    # Wrappers básicos: salud / tiempo
    # ==========================

    def ping(self, *, timeout: int = 5) -> Any:
        """
        Realiza un /ping en el mercado actual.

        Parameters
        ----------
        timeout : int
            Timeout en segundos para la llamada HTTP.

        Returns
        -------
        Any
            Respuesta JSON o cuerpo vacio segun Binance.
        """
        endpoint = self._endpoint("ping")
        return self.get(endpoint=endpoint, params=None, timeout=timeout)

    def server_time(self, *, timeout: int = 5) -> dict[str, Any]:
        """
        Obtiene la hora del servidor para el mercado actual y actualiza el offset interno.

        Parameters
        ----------
        timeout : int
            Timeout en segundos para la llamada HTTP.

        Returns
        -------
        dict[str, Any]
            Diccionario con al menos la clave ``serverTime`` en milisegundos.

        Raises
        ------
        RuntimeError
            Si la respuesta no es un dict con serverTime.
        """
        endpoint = self._endpoint("time")
        data = self.get(endpoint=endpoint, params=None, timeout=timeout)

        if not isinstance(data, dict) or "serverTime" not in data:
            raise RuntimeError(f"Respuesta inesperada de /time: {data!r}")

        return data

    def ensure_time_offset_ready(
        self,
        min_samples: int = 3,
        timeout: int = 5,
    ) -> None:
        """
        Asegura disponer de suficientes muestras recientes de /time.

        Si el estimador no esta "ready", realiza llamadas a ``server_time()``
        hasta alcanzar al menos *min_samples* intentos o hasta que
        ``is_ready()`` devuelva True.

        Parameters
        ----------
        min_samples : int
            Numero minimo de iteraciones de sincronizacion.
        timeout : int
            Timeout por llamada a /time.
        """
        attempts = 0
        target_attempts = max(min_samples, 1)

        while not self._time_offset.is_ready() and attempts < target_attempts:
            self.server_time(timeout=timeout)
            attempts += 1

    def now_server_ms(self) -> int:
        """
        Estimacion de la hora actual del servidor en milisegundos.

        Aplica el offset calculado por ``TimeOffsetEstimator`` al reloj local.

        Returns
        -------
        int
            Epoch estimado del servidor en milisegundos.
        """
        return self._time_offset.to_server_ms()

    # ==========================
    # Wrappers de metadatos
    # ==========================

    def exchange_info(
        self,
        symbol: str | None = None,
        timeout: int = 10,
    ) -> dict:
        """
        Envuelve el endpoint /exchangeInfo del mercado actual.

        Parameters
        ----------
        symbol : str | None
            Simbolo opcional (ej.: ``"BTCUSDT"``). Si es None, devuelve toda la info.
        timeout : int
            Timeout en segundos para la llamada HTTP.

        Returns
        -------
        dict
            Informacion del exchange.
        """
        endpoint = self._endpoint("exchange_info")
        params: dict[str, object] | None = None

        if symbol is not None:
            params = {"symbol": symbol.upper()}

        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /exchangeInfo: {data!r}")

        return data

    # ==========================
    # Wrappers de trades
    # ==========================

    def trades(        self,
        symbol: str,

        limit: int = 500,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene la lista de trades recientes del simbolo.

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        limit : int
            Numero de trades a devolver (max. segun Binance).
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de trades en formato dict.
        """
        endpoint = self._endpoint("trades")
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
        }
        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /trades: {data!r}")

        return data  # type: ignore[return-value]

    def agg_trades(
        self,
        symbol: str,

        from_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene trades agregados (aggTrades) para un simbolo.

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        from_id : int | None
            ID inicial opcional.
        start_time : int | None
            Marca de tiempo inicial (ms).
        end_time : int | None
            Marca de tiempo final (ms).
        limit : int
            Maximo de registros a devolver.
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de aggTrades.
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

        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /aggTrades: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Wrapper de profundidad (order book)
    # ==========================

    def depth(
        self,
        symbol: str,

        limit: int = 100,
        timeout: int = 10,
    ) -> dict:
        """
        Obtiene la profundidad de libro (order book) para un simbolo.

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        limit : int
            Profundidad de niveles (ej.: 5, 10, 20, 50, 100, 500, 1000).
        timeout : int
            Timeout en segundos.

        Returns
        -------
        dict
            Diccionario con bids/asks, lastUpdateId, etc.
        """
        endpoint = self._endpoint("depth")
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
        }
        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /depth: {data!r}")

        return data

    # ==========================
    # Wrapper de liquidaciones (force orders)
    # ==========================

    def force_orders(
        self,
        symbol: str | None = None,

        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene ordenes de liquidacion recientes (solo futuros).

        Wrapper del endpoint ``/forceOrders``. Disponible unicamente para
        mercados ``"um"`` y ``"cm"``; en ``"spot"`` lanza ``KeyError``.

        Parameters
        ----------
        symbol : str | None
            Par de trading (ej.: ``"BTCUSDT"``). Si es ``None``, devuelve
            liquidaciones de todos los simbolos (max 24 h de historico).
            Con simbolo, el rango disponible es de hasta 7 dias.
        start_time : int | None
            Marca de tiempo inicial en ms (opcional).
        end_time : int | None
            Marca de tiempo final en ms (opcional).
        limit : int
            Maximo de registros a devolver (default 100, max 1000).
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de ordenes de liquidacion.

        Raises
        ------
        KeyError
            Si el mercado es ``"spot"`` (no existe el endpoint).
        RuntimeError
            Si la respuesta no es una lista.
        """
        endpoint = self._endpoint("force_orders")
        params: dict[str, object] = {"limit": limit}
        if symbol is not None:
            params["symbol"] = symbol.upper()
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /forceOrders: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Wrapper de klines (velas)
    # ==========================

    def klines(
        self,
        symbol: str,
        interval: str,

        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
        timeout: int = 10,
    ) -> list[list[object]]:
        """
        Obtiene velas (klines) para un simbolo e intervalo.

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        interval : str
            Intervalo de vela (ej.: ``"1m"``, ``"5m"``, ``"1h"``, ``"1d"``).
        start_time : int | None
            Marca de arranque en ms (opcional).
        end_time : int | None
            Marca de fin en ms (opcional).
        limit : int
            Maximo de velas por peticion.
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[list[object]]
            Lista de velas en el formato estandar de Binance.
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

        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /klines: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # API paralela
    # ==========================

    def parallel_get(
        self,
        jobs: list[tuple[str, dict[str, Any] | None]],

        max_workers: int = 10,
        timeout: int = 10,
    ) -> list[Any]:
        """
        Lanza multiples GET publicos en paralelo con pre-reserva de peso.

        Calcula el peso total de todas las peticiones, las agrupa en lotes
        que quepan en una ventana de rate limiting, reserva el peso de cada
        lote de golpe y lanza las peticiones con un pool de threads.

        Parameters
        ----------
        jobs : list[tuple[str, dict | None]]
            Lista de (endpoint, params) a ejecutar.
        max_workers : int
            Numero maximo de threads concurrentes.
        timeout : int
            Timeout en segundos por peticion HTTP.

        Returns
        -------
        list[Any]
            Resultados en el mismo orden que *jobs*.

        Raises
        ------
        BinanceAPIException
            Si alguna peticion falla. Se relanza la primera excepcion
            encontrada tras completar todas las peticiones del lote.
        ValueError
            Si el peso de un job individual excede el limite efectivo.
        """
        if not jobs:
            return []

        # Calcular pesos
        weights = [get_weight(self.market, ep, p) for ep, p in jobs]
        eff = self.limiter.effective_limit

        # Partir en lotes que quepan en una ventana
        batches: list[list[tuple[int, str, dict[str, Any] | None, int]]] = []
        batch: list[tuple[int, str, dict[str, Any] | None, int]] = []
        batch_weight = 0

        for i, ((ep, params), w) in enumerate(zip(jobs, weights, strict=True)):
            if w > eff:
                raise ValueError(f"Peso del job {i} ({w}) excede el limite efectivo ({eff})")
            if batch_weight + w > eff and batch:
                batches.append(batch)
                batch = []
                batch_weight = 0
            batch.append((i, ep, params, w))
            batch_weight += w

        if batch:
            batches.append(batch)

        # Ejecutar lotes
        results: list[Any] = [None] * len(jobs)

        for b in batches:
            total_w = sum(w for _, _, _, w in b)
            self._acquire(total_w)

            workers = min(max_workers, len(b))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_idx = {
                    pool.submit(
                        self._execute_get,
                        ep,
                        params,
                        weight=w,
                        timeout=timeout,
                    ): idx
                    for idx, ep, params, w in b
                }

                errors: dict[int, Exception] = {}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result()
                    except Exception as exc:
                        errors[idx] = exc

                if errors:
                    first_idx = min(errors)
                    raise errors[first_idx]

        self._log.info(
            "parallel_get: %d jobs, %d lotes, used_local=%s",
            len(jobs),
            len(batches),
            self.limiter.used_local,
        )
        return results

    # ==========================
    # Wrappers bulk
    # ==========================

    def bulk_trades(
        self,
        symbols: list[str],

        limit: int = 500,
        max_workers: int = 10,
        timeout: int = 10,
    ) -> dict[str, list[dict]]:
        """
        Obtiene trades recientes de multiples simbolos en paralelo.

        Parameters
        ----------
        symbols : list[str]
            Lista de pares de trading.
        limit : int
            Numero de trades por simbolo.
        max_workers : int
            Threads concurrentes.
        timeout : int
            Timeout por peticion.

        Returns
        -------
        dict[str, list[dict]]
            Diccionario ``{symbol: trades}``.
        """
        endpoint = self._endpoint("trades")
        normed = [s.upper() for s in symbols]
        jobs: list[tuple[str, dict[str, Any] | None]] = [(endpoint, {"symbol": s, "limit": limit}) for s in normed]
        results = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)
        return dict(zip(normed, results, strict=True))

    def bulk_klines(
        self,
        symbols: list[str],
        interval: str,

        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 500,
        max_workers: int = 10,
        timeout: int = 10,
    ) -> dict[str, list[list[object]]]:
        """
        Obtiene klines de multiples simbolos en paralelo.

        Parameters
        ----------
        symbols : list[str]
            Lista de pares de trading.
        interval : str
            Intervalo de vela (``"1m"``, ``"1h"``, ``"1d"``, etc.).
        start_time : int | None
            Marca de arranque en ms (opcional, compartida por todos).
        end_time : int | None
            Marca de fin en ms (opcional, compartida por todos).
        limit : int
            Maximo de velas por simbolo.
        max_workers : int
            Threads concurrentes.
        timeout : int
            Timeout por peticion.

        Returns
        -------
        dict[str, list[list[object]]]
            Diccionario ``{symbol: klines}``.
        """
        endpoint = self._endpoint("klines")
        normed = [s.upper() for s in symbols]
        jobs: list[tuple[str, dict[str, Any] | None]] = []
        for s in normed:
            p: dict[str, Any] = {"symbol": s, "interval": interval, "limit": limit}
            if start_time is not None:
                p["startTime"] = start_time
            if end_time is not None:
                p["endTime"] = end_time
            jobs.append((endpoint, p))
        results = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)
        return dict(zip(normed, results, strict=True))

    def bulk_depth(
        self,
        symbols: list[str],

        limit: int = 100,
        max_workers: int = 10,
        timeout: int = 10,
    ) -> dict[str, dict]:
        """
        Obtiene order books de multiples simbolos en paralelo.

        Parameters
        ----------
        symbols : list[str]
            Lista de pares de trading.
        limit : int
            Profundidad de niveles.
        max_workers : int
            Threads concurrentes.
        timeout : int
            Timeout por peticion.

        Returns
        -------
        dict[str, dict]
            Diccionario ``{symbol: orderbook}``.
        """
        endpoint = self._endpoint("depth")
        normed = [s.upper() for s in symbols]
        jobs: list[tuple[str, dict[str, Any] | None]] = [(endpoint, {"symbol": s, "limit": limit}) for s in normed]
        results = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)
        return dict(zip(normed, results, strict=True))

    def bulk_agg_trades(
        self,
        symbols: list[str],

        limit: int = 500,
        max_workers: int = 10,
        timeout: int = 10,
    ) -> dict[str, list[dict]]:
        """
        Obtiene aggTrades de multiples simbolos en paralelo.

        Parameters
        ----------
        symbols : list[str]
            Lista de pares de trading.
        limit : int
            Maximo de registros por simbolo.
        max_workers : int
            Threads concurrentes.
        timeout : int
            Timeout por peticion.

        Returns
        -------
        dict[str, list[dict]]
            Diccionario ``{symbol: agg_trades}``.
        """
        endpoint = self._endpoint("agg_trades")
        normed = [s.upper() for s in symbols]
        jobs: list[tuple[str, dict[str, Any] | None]] = [(endpoint, {"symbol": s, "limit": limit}) for s in normed]
        results = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)
        return dict(zip(normed, results, strict=True))

    # ==========================
    # Paginacion automatica por rango
    # ==========================

    def klines_range(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,

        max_workers: int = 10,
        timeout: int = 10,
    ) -> list[list[object]]:
        """
        Obtiene todas las klines entre start_time y end_time, paginando automaticamente.

        Divide el rango en bloques de hasta 1000 velas y lanza peticiones en
        paralelo. Deduplica por open timestamp y descarta velas que abren
        despues de end_time.

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        interval : str
            Intervalo de vela (``"1m"``, ``"1h"``, ``"1d"``, etc.).
        start_time : int
            Marca de arranque en ms (inclusive).
        end_time : int
            Marca de fin en ms (inclusive).
        max_workers : int
            Threads concurrentes para peticiones paralelas.
        timeout : int
            Timeout en segundos por peticion.

        Returns
        -------
        list[list[object]]
            Lista de velas ordenadas por open timestamp, sin duplicados.

        Raises
        ------
        ValueError
            Si el intervalo no es soportado o start_time > end_time.
        """
        interval_ms = TICK_INTERVAL_MS.get(interval)
        if interval_ms is None:
            raise ValueError(f"Intervalo no soportado: {interval!r}")

        now_ms = int(_time() * 1000)
        end_time = min(end_time, now_ms)

        if start_time > end_time:
            raise ValueError(f"start_time ({start_time}) > end_time ({end_time})")

        block_ms = 1000 * interval_ms
        endpoint = self._endpoint("klines")

        ranges: list[tuple[int, int]] = []
        block_start = start_time
        while block_start < end_time:
            block_end = min(block_start + block_ms, end_time)
            ranges.append((block_start, block_end))
            block_start += block_ms

        if not ranges:
            return []

        if len(ranges) == 1:
            s, e = ranges[0]
            return self.klines(symbol, interval, start_time=s, end_time=e, limit=1000, timeout=timeout)

        jobs = [
            (endpoint, {'symbol': symbol.upper(), 'interval': interval,
                        'startTime': s, 'endTime': e, 'limit': 1000})
            for s, e in ranges
        ]
        self._log.info("klines_range: %d peticiones en paralelo para %s %s", len(jobs), symbol, interval)
        results = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)

        all_klines: list[list[object]] = []
        for batch in results:
            if batch:
                all_klines.extend(batch)

        # deduplicar por open timestamp y descartar overtime
        seen: set[int] = set()
        unique: list[list[object]] = []
        for k in all_klines:
            open_ts = int(k[0])
            if open_ts <= end_time and open_ts not in seen:
                seen.add(open_ts)
                unique.append(k)

        unique.sort(key=lambda x: int(x[0]))
        self._log.info("klines_range: %d velas obtenidas para %s %s", len(unique), symbol, interval)
        return unique

    def agg_trades_range(
        self,
        symbol: str,
        start_time: int,
        end_time: int,

        max_workers: int = 10,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene todos los aggTrades entre start_time y end_time, paginando automaticamente.

        Divide en chunks de 1 hora (limite de la API), lanza el primer batch
        de cada chunk en paralelo, y sub-pagina secuencialmente si algun chunk
        tiene >= 1000 trades. Deduplica por campo ``'a'`` (aggregate trade ID).

        Parameters
        ----------
        symbol : str
            Par de trading (ej.: ``"BTCUSDT"``).
        start_time : int
            Marca de arranque en ms (inclusive).
        end_time : int
            Marca de fin en ms (inclusive).
        max_workers : int
            Threads concurrentes para peticiones paralelas.
        timeout : int
            Timeout en segundos por peticion.

        Returns
        -------
        list[dict]
            Lista de aggTrades ordenados por ``'a'``, sin duplicados.

        Raises
        ------
        ValueError
            Si start_time > end_time.
        """
        ONE_HOUR_MS = 3_600_000

        now_ms = int(_time() * 1000)
        end_time = min(end_time, now_ms)

        if start_time > end_time:
            raise ValueError(f"start_time ({start_time}) > end_time ({end_time})")

        # chunks de 1 hora (limite de ventana de la API)
        chunks: list[tuple[int, int]] = []
        chunk_start = start_time
        while chunk_start < end_time:
            chunk_end = min(chunk_start + ONE_HOUR_MS, end_time)
            chunks.append((chunk_start, chunk_end))
            chunk_start = chunk_end + 1

        if not chunks:
            return []

        # primer batch de cada chunk en paralelo
        if len(chunks) == 1:
            first_batches = [
                self.agg_trades(symbol, start_time=chunks[0][0], end_time=chunks[0][1], limit=1000, timeout=timeout)
            ]
        else:
            endpoint = self._endpoint("agg_trades")
            jobs = [
                (endpoint, {'symbol': symbol.upper(), 'startTime': cs, 'endTime': ce, 'limit': 1000})
                for cs, ce in chunks
            ]
            self._log.info("agg_trades_range: %d peticiones en paralelo para %s", len(jobs), symbol)
            first_batches = self.parallel_get(jobs, max_workers=max_workers, timeout=timeout)

        all_trades: list[dict] = []

        for i, batch in enumerate(first_batches):
            if not batch:
                continue
            all_trades.extend(batch)

            # sub-paginar dentro de la hora si hay >= 1000 trades
            if len(batch) >= 1000:
                chunk_end = chunks[i][1]
                while True:
                    sub_start = batch[-1]['T'] + 1
                    if sub_start > chunk_end:
                        break
                    batch = self.agg_trades(
                        symbol, start_time=sub_start, end_time=chunk_end, limit=1000, timeout=timeout
                    )
                    if not batch:
                        break
                    all_trades.extend(batch)
                    if len(batch) < 1000:
                        break

        # deduplicar por 'a' y ordenar
        seen: set[int] = set()
        result = [t for t in all_trades if t['a'] not in seen and not seen.add(t['a'])]
        result.sort(key=lambda x: x['a'])
        self._log.info("agg_trades_range: %d trades obtenidos para %s", len(result), symbol)
        return result


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
