# panzer/exchanges/binance/config.py
"""
Obtención y parseo de rate limits desde los endpoints /exchangeInfo de Binance.

- Spot:       https://api.binance.com/api/v3/exchangeInfo
- Futures UM: https://fapi.binance.com/fapi/v1/exchangeInfo
- Futures CM: https://dapi.binance.com/dapi/v1/exchangeInfo

Se extraen especialmente los límites de tipo REQUEST_WEIGHT y RAW_REQUESTS
para intervalos de interés (por ejemplo, MINUTE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from panzer.errors import BinanceAPIException, handle_response

# ==========================
# URLs base /exchangeInfo
# ==========================

SPOT_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"
FUTURES_UM_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
FUTURES_CM_EXCHANGE_INFO_URL = "https://dapi.binance.com/dapi/v1/exchangeInfo"


# ==========================
# Modelos de datos
# ==========================


@dataclass
class RateLimit:
    """
    Entrada individual del array ``rateLimits`` de ``/exchangeInfo``.

    Attributes
    ----------
    rate_limit_type : str
        Tipo de limite: ``"REQUEST_WEIGHT"``, ``"RAW_REQUESTS"``,
        ``"ORDERS"``, etc.
    interval : str
        Unidad temporal: ``"SECOND"``, ``"MINUTE"``, ``"HOUR"``, ``"DAY"``.
    interval_num : int
        Tamano del intervalo (ej. ``1``, ``5``, ``10``).
    limit : int
        Maximo de peso/peticiones permitidas en el intervalo.
    """

    rate_limit_type: str
    interval: str
    interval_num: int
    limit: int


@dataclass
class ExchangeRateLimits:
    """
    Coleccion de rate limits relevantes para un exchange concreto.

    Se obtiene parseando la respuesta de ``/exchangeInfo`` y seleccionando
    los limites mas relevantes para el control de trafico.

    Attributes
    ----------
    request_weight : RateLimit | None
        Limite de ``REQUEST_WEIGHT`` en el intervalo principal
        (tipicamente ``MINUTE / 1``). ``None`` si no se encontro.
    raw_requests : RateLimit | None
        Limite de ``RAW_REQUESTS`` si existe. ``None`` si no aparece.
    others : list[RateLimit]
        Lista completa de todos los ``rateLimits`` devueltos por el exchange.

    See Also
    --------
    get_spot_rate_limits : Obtiene estos limites para Spot.
    get_futures_um_rate_limits : Obtiene estos limites para Futuros USDT-M.
    get_futures_cm_rate_limits : Obtiene estos limites para Futuros COIN-M.
    """

    request_weight: RateLimit | None
    raw_requests: RateLimit | None
    others: list[RateLimit]


# ==========================
# Funciones internas
# ==========================


def _fetch_exchange_info(url: str, timeout: int = 10) -> dict[str, Any]:
    """
    Lanza un GET contra el endpoint /exchangeInfo correspondiente y
    retorna el JSON parseado.

    Parameters
    ----------
    url : str
        URL absoluta al endpoint /exchangeInfo.
    timeout : int
        Timeout de la peticion HTTP en segundos.

    Returns
    -------
    dict[str, Any]
        JSON de respuesta.

    Raises
    ------
    BinanceAPIException
        Si la respuesta no es OK.
    """
    resp = requests.get(url, timeout=timeout)
    # handle_response ya lanza BinanceAPIException si hay error (429, 5xx, etc.)
    data = handle_response(resp)

    # Para /exchangeInfo esperamos siempre un dict JSON
    if not isinstance(data, dict):
        raise BinanceAPIException(
            status_code=resp.status_code,
            method="GET",
            url=url,
            error_payload=None,
        )
    return data


def _parse_rate_limits(payload: dict[str, Any]) -> ExchangeRateLimits:
    """
    Parsea la seccion ``rateLimits`` de la respuesta de /exchangeInfo.

    Se construyen objetos RateLimit y se identifican los mas relevantes:
    - REQUEST_WEIGHT (priorizando intervalo MINUTE, intervalNum=1 si existe).
    - RAW_REQUESTS (si aparece).

    Parameters
    ----------
    payload : dict[str, Any]
        JSON devuelto por /exchangeInfo.

    Returns
    -------
    ExchangeRateLimits
        Limites relevantes y la lista completa.
    """
    raw_rl: list[RateLimit] = []

    for item in payload.get("rateLimits", []):
        try:
            rl = RateLimit(
                rate_limit_type=str(item.get("rateLimitType")),
                interval=str(item.get("interval")),
                interval_num=int(item.get("intervalNum")),
                limit=int(item.get("limit")),
            )
            raw_rl.append(rl)
        except (TypeError, ValueError):
            # Si algo viene malformado, lo saltamos silenciosamente.
            continue

    # Seleccionar REQUEST_WEIGHT más interesante (MINUTE; intervalNum pequeño).
    request_weight_candidates = [rl for rl in raw_rl if rl.rate_limit_type.upper() == "REQUEST_WEIGHT"]

    request_weight: RateLimit | None = None
    if request_weight_candidates:
        # Heurística simple: priorizar MINUTE y menor intervalNum.
        request_weight_candidates.sort(key=lambda r: (r.interval.upper() != "MINUTE", r.interval_num))
        request_weight = request_weight_candidates[0]

    # Seleccionar RAW_REQUESTS (nombre varía: RAW_REQUESTS / RAW_REQUEST)
    raw_requests_candidates = [rl for rl in raw_rl if rl.rate_limit_type.upper() in ("RAW_REQUESTS", "RAW_REQUEST")]

    raw_requests: RateLimit | None = raw_requests_candidates[0] if raw_requests_candidates else None

    return ExchangeRateLimits(
        request_weight=request_weight,
        raw_requests=raw_requests,
        others=raw_rl,
    )


# ==========================
# Funciones públicas
# ==========================


def get_spot_rate_limits(timeout: int = 10) -> ExchangeRateLimits:
    """
    Obtiene los rate limits de Binance SPOT desde /api/v3/exchangeInfo.

    Parameters
    ----------
    timeout : int
        Timeout de la peticion HTTP en segundos.

    Returns
    -------
    ExchangeRateLimits
        Informacion de REQUEST_WEIGHT, etc.
    """
    data = _fetch_exchange_info(SPOT_EXCHANGE_INFO_URL, timeout=timeout)
    return _parse_rate_limits(data)


def get_futures_um_rate_limits(timeout: int = 10) -> ExchangeRateLimits:
    """
    Obtiene los rate limits de Binance Futuros USDT-M desde /fapi/v1/exchangeInfo.

    Parameters
    ----------
    timeout : int
        Timeout de la peticion HTTP en segundos.

    Returns
    -------
    ExchangeRateLimits
        Informacion de REQUEST_WEIGHT, etc.
    """
    data = _fetch_exchange_info(FUTURES_UM_EXCHANGE_INFO_URL, timeout=timeout)
    return _parse_rate_limits(data)


def get_futures_cm_rate_limits(timeout: int = 10) -> ExchangeRateLimits:
    """
    Obtiene los rate limits de Binance Futuros COIN-M desde /dapi/v1/exchangeInfo.

    Parameters
    ----------
    timeout : int
        Timeout de la peticion HTTP en segundos.

    Returns
    -------
    ExchangeRateLimits
        Informacion de REQUEST_WEIGHT, etc.
    """
    data = _fetch_exchange_info(FUTURES_CM_EXCHANGE_INFO_URL, timeout=timeout)
    return _parse_rate_limits(data)


if __name__ == "__main__":
    spot_limits = get_spot_rate_limits()
    fut_um_limits = get_futures_um_rate_limits()
    fut_cm_limits = get_futures_cm_rate_limits()

    print("SPOT REQUEST_WEIGHT:", spot_limits.request_weight)
    print("FUT UM REQUEST_WEIGHT:", fut_um_limits.request_weight)
    print("FUT CM REQUEST_WEIGHT:", fut_cm_limits.request_weight)
