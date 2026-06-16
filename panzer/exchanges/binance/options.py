# panzer/exchanges/binance/options.py
"""
Cliente publico de alto nivel para Binance European Options (EAPI).

Las opciones europeas de Binance se sirven desde un host propio
(``https://eapi.binance.com``) con el prefijo ``/eapi/v1``. Este modulo
reutiliza toda la fontaneria de :class:`BinancePublicClient`
(HTTP de bajo nivel, rate limiting basado en ``/eapi/v1/exchangeInfo`` y
sincronizacion de reloj) y solo anade los wrappers de dominio especificos
de opciones.

El mercado queda fijado a ``"eapi"``; no debe cambiarse.

Endpoints implementados:
- ``exchange_info_options`` -> catalogo de contratos (strikes, expiraciones, call/put).
- ``mark``                  -> mark price, volatilidad implicita y griegas.
- ``index``                 -> precio indice del subyacente.
- ``ticker``                -> estadisticas 24 h por contrato.
- ``open_interest``         -> open interest agregado por subyacente y expiracion.
- ``exercise_history``      -> historico de ejercicios (liquidaciones de opciones).
- ``depth`` y ``klines``    -> heredados de :class:`BinancePublicClient`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from panzer.exchanges.binance.public import BinancePublicClient, MarketType


@dataclass
class BinanceOptionsClient(BinancePublicClient):
    """
    Cliente publico para Binance European Options (EAPI).

    Subclase de :class:`BinancePublicClient` con el mercado fijado a
    ``"eapi"``. Hereda ``get()``, rate limiting, sincronizacion de reloj y
    manejo de errores; anade los wrappers de datos de opciones.

    Parameters
    ----------
    safety_ratio : float
        Factor de seguridad para el rate limiter (``(0, 1]``).
    auto_sync : bool
        Si ``True``, sincroniza el reloj con Binance al instanciar.

    See Also
    --------
    BinancePublicClient : Cliente base con la fontaneria compartida.

    Examples
    --------
    >>> client = BinanceOptionsClient()
    >>> info = client.exchange_info_options()
    >>> marks = client.mark("BTC-260626-140000-C")
    >>> index = client.index("BTCUSDT")
    """

    market: MarketType = "eapi"

    def __post_init__(self) -> None:
        if self.market != "eapi":
            raise ValueError(
                f"BinanceOptionsClient solo soporta market='eapi', recibido {self.market!r}"
            )
        super().__post_init__()

    # ==========================
    # Catalogo de contratos
    # ==========================

    def exchange_info_options(self, *, timeout: int = 10) -> dict[str, Any]:
        """
        Obtiene el catalogo de contratos de opciones (``/eapi/v1/exchangeInfo``).

        Devuelve la informacion de todos los contratos negociables: simbolos,
        strikes, fechas de expiracion, lado (CALL/PUT), subyacente, filtros de
        precio/cantidad y estado.

        Parameters
        ----------
        timeout : int
            Timeout en segundos.

        Returns
        -------
        dict[str, Any]
            Diccionario con las claves ``timezone``, ``serverTime``,
            ``optionContracts``, ``optionAssets``, ``optionSymbols`` y
            ``rateLimits``. Cada entrada de ``optionSymbols`` incluye
            ``symbol``, ``side``, ``strikePrice``, ``underlying``,
            ``expiryDate``, ``filters`` y ``status``.

        Raises
        ------
        RuntimeError
            Si la respuesta no es un diccionario.
        """
        endpoint = self._endpoint("exchange_info")
        data = self.get(endpoint=endpoint, params=None, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/exchangeInfo: {data!r}")

        return data

    # ==========================
    # Mark price + griegas + IV
    # ==========================

    def mark(
        self,
        symbol: str | None = None,
        *,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene mark price, volatilidad implicita y griegas (``/eapi/v1/mark``).

        Es el endpoint clave para analisis: devuelve, por contrato, el precio
        marcado y las metricas de riesgo ya calculadas por Binance (no hay que
        implementar Black-Scholes).

        Parameters
        ----------
        symbol : str | None
            Simbolo del contrato (ej.: ``"BTC-260626-140000-C"``). Si es
            ``None``, devuelve el mark de todos los contratos negociables.
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de diccionarios (incluso con ``symbol`` unico). Cada entrada
            incluye ``symbol``, ``markPrice``, ``bidIV``, ``askIV``, ``markIV``,
            ``delta``, ``gamma``, ``theta``, ``vega``, ``highPriceLimit``,
            ``lowPriceLimit`` y ``riskFreeInterest``.

        Raises
        ------
        RuntimeError
            Si la respuesta no es una lista.
        """
        endpoint = self._endpoint("mark")
        params: dict[str, object] = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        data = self.get(endpoint=endpoint, params=params or None, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/mark: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Precio indice del subyacente
    # ==========================

    def index(self, underlying: str, *, timeout: int = 10) -> dict[str, Any]:
        """
        Obtiene el precio indice del subyacente (``/eapi/v1/index``).

        Parameters
        ----------
        underlying : str
            Par subyacente (ej.: ``"BTCUSDT"``).
        timeout : int
            Timeout en segundos.

        Returns
        -------
        dict[str, Any]
            Diccionario con ``indexPrice`` y ``time`` (epoch en ms).

        Raises
        ------
        RuntimeError
            Si la respuesta no es un diccionario.
        """
        endpoint = self._endpoint("index")
        params = {"underlying": underlying.upper()}
        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/index: {data!r}")

        return data

    # ==========================
    # Estadisticas 24 h por contrato
    # ==========================

    def ticker(
        self,
        symbol: str | None = None,
        *,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene estadisticas de 24 h por contrato (``/eapi/v1/ticker``).

        Parameters
        ----------
        symbol : str | None
            Simbolo del contrato (ej.: ``"BTC-260626-140000-C"``). Si es
            ``None``, devuelve el ticker de todos los contratos.
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de diccionarios (incluso con ``symbol`` unico). Cada entrada
            incluye ``symbol``, ``priceChange``, ``priceChangePercent``,
            ``lastPrice``, ``open``, ``high``, ``low``, ``volume``, ``amount``,
            ``bidPrice``, ``askPrice``, ``openTime``, ``closeTime``,
            ``tradeCount``, ``strikePrice`` y ``exercisePrice``.

        Raises
        ------
        RuntimeError
            Si la respuesta no es una lista.
        """
        endpoint = self._endpoint("ticker")
        params: dict[str, object] = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        data = self.get(endpoint=endpoint, params=params or None, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/ticker: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Open interest por subyacente y expiracion
    # ==========================

    def open_interest(  # type: ignore[override]
        self,
        underlying_asset: str,
        expiration: str,
        *,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene el open interest agregado de opciones (``/eapi/v1/openInterest``).

        A diferencia del ``open_interest`` de futuros (que recibe un ``symbol``),
        el de opciones se consulta por **activo subyacente** y **expiracion**, y
        devuelve el OI de todos los strikes de esa expiracion.

        Parameters
        ----------
        underlying_asset : str
            Activo subyacente, NO el par (ej.: ``"BTC"``, ``"ETH"``).
        expiration : str
            Fecha de expiracion en formato ``YYMMDD`` (ej.: ``"260626"``),
            tal como aparece en el simbolo del contrato.
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de entradas con ``symbol``, ``sumOpenInterest``,
            ``sumOpenInterestUsd`` y ``timestamp``.

        Raises
        ------
        RuntimeError
            Si la respuesta no es una lista.
        """
        endpoint = self._endpoint("open_interest")
        params = {
            "underlyingAsset": underlying_asset.upper(),
            "expiration": expiration,
        }
        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/openInterest: {data!r}")

        return data  # type: ignore[return-value]

    # ==========================
    # Historico de ejercicios
    # ==========================

    def exercise_history(
        self,
        underlying: str | None = None,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene el historico de ejercicios de opciones (``/eapi/v1/exerciseHistory``).

        Cada entrada describe como expiro un contrato: precio de ejercicio
        teorico (``strikePrice``), precio real de liquidacion (``realStrikePrice``)
        y el resultado (``strikeResult``).

        Parameters
        ----------
        underlying : str | None
            Subyacente para filtrar (ej.: ``"BTCUSDT"``). Si es ``None``,
            devuelve el historico de todos los subyacentes.
        start_time : int | None
            Marca de tiempo inicial en ms (opcional).
        end_time : int | None
            Marca de tiempo final en ms (opcional).
        limit : int
            Maximo de registros (default 100, max 100).
        timeout : int
            Timeout en segundos.

        Returns
        -------
        list[dict]
            Lista de entradas con ``symbol``, ``strikePrice``,
            ``realStrikePrice``, ``expiryDate`` y ``strikeResult``.

        Raises
        ------
        RuntimeError
            Si la respuesta no es una lista.
        """
        endpoint = self._endpoint("exercise_history")
        params: dict[str, object] = {"limit": limit}
        if underlying is not None:
            params["underlying"] = underlying.upper()
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        data = self.get(endpoint=endpoint, params=params, timeout=timeout)

        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de /eapi/v1/exerciseHistory: {data!r}")

        return data  # type: ignore[return-value]
