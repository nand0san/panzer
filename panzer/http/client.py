# panzer/http/client.py
"""
Cliente HTTP de bajo nivel para la API pública de Binance.

Objetivos:
- Sólo peticiones públicas (sin API keys ni firmas).
- Integración con:
    - BinanceFixedWindowLimiter (control de REQUEST_WEIGHT).
    - LogManager (logs a fichero + pantalla).
    - handle_response() para levantar BinanceAPIException cuando proceda.

Este módulo NO conoce aún nada del “cliente de alto nivel” (BinancePublicClient);
es una capa fina sobre requests + rate limiting + manejo de errores.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import requests

from panzer.log_manager import LogManager
from panzer.errors import handle_response, BinanceAPIException
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
    Construye la URL absoluta para la petición.

    :param base_url: URL base (sin endpoint), por ejemplo BINANCE_SPOT_BASE_URL.
    :param endpoint: Path del endpoint, por ejemplo "/api/v3/time".
    :return: URL absoluta.
    """
    return base_url.rstrip("/") + "/" + endpoint.lstrip("/")


# ==========================
# API pública
# ==========================


def binance_public_get(
    base_url: str,
    endpoint: str,
    params: Optional[Dict[str, Any]],
    limiter: BinanceFixedWindowLimiter,
    weight: int = 1,
    timeout: int = 10,
) -> Tuple[Any, Mapping[str, str]]:
    """
    Realiza una petición GET pública contra Binance usando rate limiting.

    Flujo:
    - `limiter.acquire(weight)` antes de lanzar el GET.
    - GET con requests, con logs de entrada/salida.
    - `limiter.update_from_headers(resp.headers)` para sincronizar
      X-MBX-USED-WEIGHT-1M.
    - `handle_response(resp)` para levantar BinanceAPIException si procede.

    :param base_url: URL base (spot / futures).
    :param endpoint: Path del endpoint (ej: "/api/v3/time").
    :param params: Diccionario de parámetros de query (o None).
    :param limiter: Instancia de BinanceFixedWindowLimiter.
    :param weight: Peso estimado de la operación (REQUEST_WEIGHT).
    :param timeout: Timeout en segundos para requests.
    :return: Tupla (data, headers):
             - data: JSON parseado (dict/list) o texto.
             - headers: cabeceras HTTP de la respuesta.
    :raises BinanceAPIException: en caso de error interpretado.
    :raises requests.RequestException: ante errores de red.
    """
    url = _build_url(base_url, endpoint)

    # Rate limiting local antes de llamar a la API
    limiter.acquire(weight=weight)

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
