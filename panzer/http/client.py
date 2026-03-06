# panzer/http/client.py
"""
Cliente HTTP de bajo nivel para la API de Binance.

Soporta peticiones publicas (sin firma) y autenticadas (con HMAC-SHA256).

Integracion con:
- BinanceFixedWindowLimiter (control de REQUEST_WEIGHT).
- BinanceRequestSigner (firma HMAC para endpoints privados).
- LogManager (logs a fichero + pantalla).
- handle_response() para levantar BinanceAPIException cuando proceda.

Este modulo es una capa fina sobre requests + rate limiting + manejo de errores.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from panzer.errors import BinanceAPIException, handle_response
from panzer.log_manager import LogManager
from panzer.rate_limit.binance_fixed import BinanceFixedWindowLimiter

# ==========================
# Constantes básicas de Binance
# ==========================

BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_FUTURES_UM_BASE_URL = "https://fapi.binance.com"
BINANCE_FUTURES_CM_BASE_URL = "https://dapi.binance.com"


# ==========================
# Logger del módulo
# ==========================

_http_log = LogManager(
    name="panzer.http",
    folder="logs",
    filename="http.log",
    level="INFO",
)


# ==========================
# Funciones internas
# ==========================


def _build_url(base_url: str, endpoint: str) -> str:
    """
    Construye la URL absoluta para la peticion.

    Parameters
    ----------
    base_url : str
        URL base (sin endpoint), por ejemplo BINANCE_SPOT_BASE_URL.
    endpoint : str
        Path del endpoint, por ejemplo ``"/api/v3/time"``.

    Returns
    -------
    str
        URL absoluta.
    """
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


# ==========================
# API pública
# ==========================


def binance_public_get(
    base_url: str,
    endpoint: str,
    params: dict[str, Any] | None,
    limiter: BinanceFixedWindowLimiter,
    weight: int = 1,
    timeout: int = 10,
) -> tuple[Any, Mapping[str, str]]:
    """
    Realiza una peticion GET publica contra Binance.

    No hace acquire internamente -- el caller debe llamar a
    ``limiter.acquire(weight)`` antes si lo necesita.

    Parameters
    ----------
    base_url : str
        URL base (spot / futures).
    endpoint : str
        Path del endpoint (ej: ``"/api/v3/time"``).
    params : dict[str, Any] | None
        Parametros de query (o None).
    limiter : BinanceFixedWindowLimiter
        Instancia del rate limiter.
    weight : int
        Peso estimado de la operacion (REQUEST_WEIGHT).
    timeout : int
        Timeout en segundos para requests.

    Returns
    -------
    tuple[Any, Mapping[str, str]]
        (data, headers) -- JSON parseado y cabeceras HTTP.

    Raises
    ------
    BinanceAPIException
        En caso de error interpretado.
    requests.RequestException
        Ante errores de red.
    """
    url = _build_url(base_url, endpoint)

    _http_log.debug(f"GET {url} params={params} weight={weight} used_local={limiter.used_local}")

    # Petición HTTP
    resp = requests.get(url, params=params, timeout=timeout)

    # Sincronizar contador local con X-MBX-USED-WEIGHT-1M
    limiter.update_from_headers(resp.headers)

    # Manejo centralizado de errores + parseo JSON / texto
    data = handle_response(resp)

    _http_log.debug(
        "RESP %s status=%s used_local=%s server_used=%s",
        url,
        resp.status_code,
        limiter.used_local,
        limiter.last_server_used,
    )

    return data, resp.headers


# ==========================
# Peticiones firmadas (autenticadas)
# ==========================


def binance_signed_request(
    method: str,
    base_url: str,
    endpoint: str,
    params: list[tuple[str, str | int]] | None,
    signer: object,
    limiter: BinanceFixedWindowLimiter,
    *,
    sign: bool = True,
    recv_window: int | None = None,
    server_time_offset_ms: int = 0,
    weight: int = 1,
    timeout: int = 10,
) -> tuple[Any, Mapping[str, str]]:
    """
    Realiza una peticion firmada (GET/POST/DELETE) contra Binance.

    Parameters
    ----------
    method : str
        Metodo HTTP: ``"GET"``, ``"POST"`` o ``"DELETE"``.
    base_url : str
        URL base del mercado.
    endpoint : str
        Path del endpoint (ej: ``"/api/v3/account"``).
    params : list[tuple] | None
        Pares (clave, valor) de la peticion.
    signer : BinanceRequestSigner
        Instancia del firmante (inyecta API key y firma HMAC).
    limiter : BinanceFixedWindowLimiter
        Rate limiter para sincronizar pesos.
    sign : bool
        Si True, firma completa (timestamp + HMAC). Si False, solo
        anade API key al header (semi-signed, para USER_STREAM/MARKET_DATA).
    recv_window : int | None
        Ventana de validez en ms. Si se proporciona, se anade a los params.
    server_time_offset_ms : int
        Desfase servidor-local en ms para el timestamp.
    weight : int
        Peso estimado de la operacion.
    timeout : int
        Timeout en segundos para la peticion HTTP.

    Returns
    -------
    tuple[Any, Mapping[str, str]]
        (data, headers) -- respuesta parseada y cabeceras HTTP.

    Raises
    ------
    BinanceAPIException
        Ante errores de la API.
    requests.RequestException
        Ante errores de red.
    ValueError
        Si el metodo HTTP no es valido.
    """
    method = method.strip().upper()
    if method not in ("GET", "POST", "DELETE"):
        raise ValueError(f"Metodo HTTP no soportado: {method!r}")

    url = _build_url(base_url, endpoint)
    p = list(params) if params else []

    if recv_window is not None:
        p.append(("recvWindow", recv_window))

    # Firma o semi-firma
    headers = signer.headers_with_api_key()  # type: ignore[attr-defined]
    if sign:
        p = signer.sign_params(  # type: ignore[attr-defined]
            p,
            server_time_offset_ms=server_time_offset_ms,
        )

    _http_log.debug(
        "%s %s params=%d sign=%s weight=%s",
        method, url, len(p), sign, weight,
    )

    # Peticion HTTP
    if method == "GET":
        resp = requests.get(url, params=p, headers=headers, timeout=timeout)
    elif method == "POST":
        resp = requests.post(url, params=p, headers=headers, timeout=timeout)
    else:
        resp = requests.delete(url, params=p, headers=headers, timeout=timeout)

    # Sincronizar rate limiter
    limiter.update_from_headers(resp.headers)

    # Parseo y manejo de errores
    data = handle_response(resp)

    _http_log.debug(
        "RESP %s %s status=%s used_local=%s server_used=%s",
        method, url, resp.status_code,
        limiter.used_local, limiter.last_server_used,
    )

    return data, resp.headers


# ==========================
# Test manual rápido
# ==========================

if __name__ == "__main__":
    """
    Prueba manual del cliente HTTP:

    1) Obtiene los límites SPOT vía /exchangeInfo (usando config.py).
    2) Construye un BinanceFixedWindowLimiter con esos límites.
    3) Lanza:
        - GET /api/v3/time
        - GET /api/v3/exchangeInfo
        - GET /api/v3/endpoint_inexistente  (para forzar un error)
    """

    from panzer.exchanges.binance.config import get_spot_rate_limits
    from panzer.rate_limit.binance_fixed import BinanceFixedWindowLimiter

    # 1) Cargar límites dinámicos de SPOT
    spot_limits = get_spot_rate_limits()
    print("SPOT REQUEST_WEIGHT limit:", spot_limits.request_weight)

    # 2) Crear limiter
    limiter = BinanceFixedWindowLimiter.from_exchange_limits(
        spot_limits,
        safety_ratio=0.9,
    )

    # 3.1) /api/v3/time
    print("\n== GET /api/v3/time ==")
    data_time, headers_time = binance_public_get(
        base_url=BINANCE_SPOT_BASE_URL,
        endpoint="/api/v3/time",
        params=None,
        limiter=limiter,
        weight=1,
        timeout=5,
    )
    print("time response:", data_time)
    print("X-MBX-USED-WEIGHT-1M:", headers_time.get("X-MBX-USED-WEIGHT-1M"))

    # 3.2) /api/v3/exchangeInfo
    print("\n== GET /api/v3/exchangeInfo ==")
    data_exch, headers_exch = binance_public_get(
        base_url=BINANCE_SPOT_BASE_URL,
        endpoint="/api/v3/exchangeInfo",
        params=None,
        limiter=limiter,
        weight=10,  # peso aproximado típico del endpoint
        timeout=10,
    )
    print("symbols len:", len(data_exch.get("symbols", [])))
    print("X-MBX-USED-WEIGHT-1M:", headers_exch.get("X-MBX-USED-WEIGHT-1M"))

    # 3.3) Endpoint inexistente -> debe levantar BinanceAPIException
    print("\n== GET /api/v3/this_does_not_exist (esperado error) ==")
    try:
        _data_bad, _headers_bad = binance_public_get(
            base_url=BINANCE_SPOT_BASE_URL,
            endpoint="/api/v3/this_does_not_exist",
            params=None,
            limiter=limiter,
            weight=1,
            timeout=5,
        )
    except BinanceAPIException as exc:
        print("BinanceAPIException capturada:")
        print("  status_code:", exc.status_code)
        print("  url:", exc.url)
        if exc.error_payload:
            print("  code:", exc.error_payload.code)
            print("  msg:", exc.error_payload.msg)
    else:
        print("ERROR: se esperaba una BinanceAPIException y no se produjo.")
