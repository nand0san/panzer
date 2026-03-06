# panzer/exchanges/binance/client.py
"""
Cliente autenticado de alto nivel para la API de Binance.

Extiende ``BinancePublicClient`` con soporte para endpoints firmados
(TRADE, MARGIN, USER_DATA) y semi-firmados (USER_STREAM, MARKET_DATA).

Gestiona credenciales cifradas mediante ``CredentialManager`` y firma
peticiones con HMAC-SHA256 via ``BinanceRequestSigner``.
"""

from __future__ import annotations

from typing import Any, Literal

from panzer.credentials import CredentialManager
from panzer.exchanges.binance.public import BinancePublicClient, MarketType
from panzer.exchanges.binance.signer import BinanceRequestSigner
from panzer.exchanges.binance.weights import get_weight
from panzer.http.client import binance_signed_request
from panzer.log_manager import LogManager


class BinanceClient(BinancePublicClient):
    """
    Cliente completo para Binance: endpoints publicos + autenticados.

    Hereda todos los metodos publicos de ``BinancePublicClient``
    (klines, depth, agg_trades, trades, etc.) y anade soporte para
    peticiones firmadas (account, ordenes, myTrades, etc.).

    Parameters
    ----------
    market : MarketType
        Mercado: ``"spot"``, ``"um"`` o ``"cm"``.
    safety_ratio : float
        Ratio de seguridad para el rate limiter (0-1].
    credentials : CredentialManager | None
        Gestor de credenciales. Si es None, crea uno por defecto
        (busca en ``~/.panzer_creds`` o solicita al usuario).
    auto_sync : bool
        Si True (por defecto), sincroniza el reloj con Binance al crear
        el cliente. Pasar False para omitir la sincronizacion.
    """

    def __init__(
        self,
        market: MarketType = "spot",
        safety_ratio: float = 0.9,
        credentials: CredentialManager | None = None,
        auto_sync: bool = True,
    ) -> None:
        super().__init__(market=market, safety_ratio=safety_ratio, auto_sync=auto_sync)
        self._signer = BinanceRequestSigner(credentials)
        self._auth_log = LogManager(
            name=f"panzer.binance.client.{self.market}",
            folder="logs",
            filename=f"binance_client_{self.market}.log",
            level="INFO",
        )
        self._auth_log.info("BinanceClient inicializado (market=%s)", self.market)

    @property
    def signer(self) -> BinanceRequestSigner:
        """Acceso al firmante de peticiones."""
        return self._signer

    # ── Peticion generica firmada ────────────────────────────

    def signed_request(
        self,
        method: str,
        endpoint: str,
        params: list[tuple[str, str | int]] | None = None,
        *,
        sign: bool = True,
        recv_window: int | None = None,
        weight: int | None = None,
        timeout: int = 10,
    ) -> Any:
        """
        Lanza una peticion autenticada contra Binance.

        Parameters
        ----------
        method : str
            ``"GET"``, ``"POST"`` o ``"DELETE"``.
        endpoint : str
            Path del endpoint (ej: ``"/api/v3/account"``).
        params : list[tuple] | None
            Pares (clave, valor). No incluir timestamp ni signature
            (se anaden automaticamente).
        sign : bool
            True para firma completa (TRADE/USER_DATA). False para
            semi-firma (solo API key, USER_STREAM/MARKET_DATA).
        recv_window : int | None
            Ventana de validez en ms. None para no enviarla.
        weight : int | None
            Peso de la operacion. None lo calcula automaticamente.
        timeout : int
            Timeout HTTP en segundos.

        Returns
        -------
        Any
            Respuesta parseada (dict o list).
        """
        if weight is None:
            params_dict = dict(params) if params else None
            weight = get_weight(self.market, endpoint, params_dict)

        # Sincronizar reloj si no esta listo (critico para la firma)
        if not self.time_offset.is_ready():
            self.ensure_time_offset_ready(min_samples=3)

        offset_ms = int(self.time_offset.current_offset() * 1000)
        now_server_sec = self.time_offset.to_server_ms() / 1000.0
        self.limiter.acquire(weight=weight, now=now_server_sec)

        data, headers = binance_signed_request(
            method=method,
            base_url=self.base_url,
            endpoint=endpoint,
            params=params,
            signer=self._signer,
            limiter=self.limiter,
            sign=sign,
            recv_window=recv_window,
            server_time_offset_ms=offset_ms,
            weight=weight,
            timeout=timeout,
        )

        self._auth_log.debug(
            "%s %s weight=%s used_local=%s server_used=%s",
            method,
            endpoint,
            weight,
            self.limiter.used_local,
            self.limiter.last_server_used,
        )

        return data

    # ── Wrappers de endpoints privados comunes ───────────────

    def account(self, *, recv_window: int = 5000, timeout: int = 10) -> dict:
        """
        Obtiene la informacion de la cuenta (balances, permisos, etc.).

        Returns
        -------
        dict
            Respuesta del endpoint ``/account``.
        """
        endpoint = self._account_endpoint()
        data = self.signed_request("GET", endpoint, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de account: {data!r}")
        return data

    def my_trades(
        self,
        symbol: str,
        *,
        limit: int = 500,
        from_id: int | None = None,
        recv_window: int = 5000,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene los trades propios para un simbolo.

        Parameters
        ----------
        symbol : str
            Par de trading.
        limit : int
            Maximo de trades a devolver.
        from_id : int | None
            TradeId desde el cual empezar.
        recv_window : int
            Ventana de validez en ms.
        timeout : int
            Timeout HTTP.

        Returns
        -------
        list[dict]
            Lista de trades propios.
        """
        endpoint = self._my_trades_endpoint()
        params: list[tuple[str, str | int]] = [
            ("symbol", symbol.upper()),
            ("limit", limit),
        ]
        if from_id is not None:
            params.append(("fromId", from_id))
        data = self.signed_request("GET", endpoint, params, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de myTrades: {data!r}")
        return data  # type: ignore[return-value]

    def new_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        order_type: str,
        *,
        quantity: float | None = None,
        quote_order_qty: float | None = None,
        price: float | None = None,
        time_in_force: str | None = None,
        recv_window: int = 5000,
        timeout: int = 10,
        **extra: str | int,
    ) -> dict:
        """
        Envia una orden nueva.

        Parameters
        ----------
        symbol : str
            Par de trading.
        side : "BUY" | "SELL"
            Lado de la orden.
        order_type : str
            Tipo: ``"LIMIT"``, ``"MARKET"``, ``"STOP_LOSS_LIMIT"``, etc.
        quantity : float | None
            Cantidad en base asset.
        quote_order_qty : float | None
            Cantidad en quote asset (para ordenes MARKET por quote).
        price : float | None
            Precio limite.
        time_in_force : str | None
            ``"GTC"``, ``"IOC"``, ``"FOK"``.
        recv_window : int
            Ventana de validez en ms.
        timeout : int
            Timeout HTTP.
        **extra
            Parametros adicionales de Binance (stopPrice, icebergQty, etc.).

        Returns
        -------
        dict
            Respuesta de la orden creada.
        """
        endpoint = self._order_endpoint()
        params: list[tuple[str, str | int]] = [
            ("symbol", symbol.upper()),
            ("side", side),
            ("type", order_type),
        ]
        if quantity is not None:
            params.append(("quantity", str(quantity)))
        if quote_order_qty is not None:
            params.append(("quoteOrderQty", str(quote_order_qty)))
        if price is not None:
            params.append(("price", str(price)))
        if time_in_force is not None:
            params.append(("timeInForce", time_in_force))
        for k, v in extra.items():
            params.append((k, v))

        data = self.signed_request("POST", endpoint, params, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de order: {data!r}")
        return data

    def cancel_order(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        orig_client_order_id: str | None = None,
        recv_window: int = 5000,
        timeout: int = 10,
    ) -> dict:
        """
        Cancela una orden existente.

        Parameters
        ----------
        symbol : str
            Par de trading.
        order_id : int | None
            ID de la orden a cancelar.
        orig_client_order_id : str | None
            Client order ID alternativo.
        recv_window : int
            Ventana de validez en ms.
        timeout : int
            Timeout HTTP.

        Returns
        -------
        dict
            Respuesta de la cancelacion.
        """
        endpoint = self._order_endpoint()
        params: list[tuple[str, str | int]] = [("symbol", symbol.upper())]
        if order_id is not None:
            params.append(("orderId", order_id))
        if orig_client_order_id is not None:
            params.append(("origClientOrderId", orig_client_order_id))

        data = self.signed_request("DELETE", endpoint, params, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada de cancel order: {data!r}")
        return data

    def open_orders(
        self,
        symbol: str | None = None,
        *,
        recv_window: int = 5000,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene las ordenes abiertas.

        Parameters
        ----------
        symbol : str | None
            Par de trading. Si es None, devuelve todas.

        Returns
        -------
        list[dict]
            Lista de ordenes abiertas.
        """
        endpoint = self._open_orders_endpoint()
        params: list[tuple[str, str | int]] = []
        if symbol is not None:
            params.append(("symbol", symbol.upper()))

        data = self.signed_request("GET", endpoint, params, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de openOrders: {data!r}")
        return data  # type: ignore[return-value]

    def all_orders(
        self,
        symbol: str,
        *,
        limit: int = 500,
        order_id: int | None = None,
        recv_window: int = 5000,
        timeout: int = 10,
    ) -> list[dict]:
        """
        Obtiene todas las ordenes (abiertas, cerradas, canceladas).

        Parameters
        ----------
        symbol : str
            Par de trading.
        limit : int
            Maximo de ordenes a devolver.
        order_id : int | None
            ID desde el cual empezar.

        Returns
        -------
        list[dict]
            Lista de ordenes.
        """
        endpoint = self._all_orders_endpoint()
        params: list[tuple[str, str | int]] = [
            ("symbol", symbol.upper()),
            ("limit", limit),
        ]
        if order_id is not None:
            params.append(("orderId", order_id))

        data = self.signed_request("GET", endpoint, params, recv_window=recv_window, timeout=timeout)
        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta inesperada de allOrders: {data!r}")
        return data  # type: ignore[return-value]

    # ── Resolucion de endpoints privados por mercado ─────────

    def _account_endpoint(self) -> str:
        return _PRIVATE_ENDPOINTS[self.market]["account"]

    def _my_trades_endpoint(self) -> str:
        return _PRIVATE_ENDPOINTS[self.market]["my_trades"]

    def _order_endpoint(self) -> str:
        return _PRIVATE_ENDPOINTS[self.market]["order"]

    def _open_orders_endpoint(self) -> str:
        return _PRIVATE_ENDPOINTS[self.market]["open_orders"]

    def _all_orders_endpoint(self) -> str:
        return _PRIVATE_ENDPOINTS[self.market]["all_orders"]


# ── Endpoints privados por mercado ───────────────────────────

_PRIVATE_ENDPOINTS: dict[str, dict[str, str]] = {
    "spot": {
        "account": "/api/v3/account",
        "my_trades": "/api/v3/myTrades",
        "order": "/api/v3/order",
        "open_orders": "/api/v3/openOrders",
        "all_orders": "/api/v3/allOrders",
    },
    "um": {
        "account": "/fapi/v2/account",
        "my_trades": "/fapi/v1/userTrades",
        "order": "/fapi/v1/order",
        "open_orders": "/fapi/v1/openOrders",
        "all_orders": "/fapi/v1/allOrders",
    },
    "cm": {
        "account": "/dapi/v1/account",
        "my_trades": "/dapi/v1/userTrades",
        "order": "/dapi/v1/order",
        "open_orders": "/dapi/v1/openOrders",
        "all_orders": "/dapi/v1/allOrders",
    },
}
