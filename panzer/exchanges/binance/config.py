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
    Representa una entrada del array `rateLimits` de /exchangeInfo.

    Campos esperados según la doc oficial:
    - rateLimitType: REQUEST_WEIGHT, RAW_REQUEST(S), ORDERS, ORDER, etc.
    - interval: SECOND, MINUTE, HOUR, DAY...
    - intervalNum: tamaño del intervalo (1, 5, 10, ...)
    - limit: máximo de peticiones/peso en dicho intervalo.
    """

    rate_limit_type: str
    interval: str
    interval_num: int
    limit: int


@dataclass
class ExchangeRateLimits:
    """
    Colección de rate limits relevantes para un exchange concreto.

    Se guarda:
    - request_weight: límite de REQUEST_WEIGHT en el intervalo principal
                      (típicamente MINUTE / 1).
    - raw_requests: límite de RAW_REQUESTS si existe y es relevante.
    - others: lista completa de todos los `rateLimits` devueltos.
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

    :param url: URL absoluta al endpoint /exchangeInfo.
    :param timeout: Timeout de la petición HTTP en segundos.
    :return: Dict con el JSON de respuesta.
    :raises BinanceAPIException: si la respuesta no es OK.
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
    Parsea la sección `rateLimits` de la respuesta de /exchangeInfo.

    Se construyen objetos RateLimit y se identifican los más relevantes:
    - REQUEST_WEIGHT (priorizando intervalo MINUTE, intervalNum=1 si existe).
    - RAW_REQUESTS (si aparece).

    :param payload: JSON devuelto por /exchangeInfo.
    :return: ExchangeRateLimits con los límites relevantes y la lista completa.
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

    :param timeout: Timeout de la petición HTTP en segundos.
    :return: ExchangeRateLimits con información de REQUEST_WEIGHT, etc.
    """
    data = _fetch_exchange_info(SPOT_EXCHANGE_INFO_URL, timeout=timeout)
    return _parse_rate_limits(data)


def get_futures_um_rate_limits(timeout: int = 10) -> ExchangeRateLimits:
    """
    Obtiene los rate limits de Binance Futuros USDT-M desde /fapi/v1/exchangeInfo.

    :param timeout: Timeout de la petición HTTP en segundos.
    :return: ExchangeRateLimits con información de REQUEST_WEIGHT, etc.
    """
    data = _fetch_exchange_info(FUTURES_UM_EXCHANGE_INFO_URL, timeout=timeout)
    return _parse_rate_limits(data)


def get_futures_cm_rate_limits(timeout: int = 10) -> ExchangeRateLimits:
    """
    Obtiene los rate limits de Binance Futuros COIN-M desde /dapi/v1/exchangeInfo.

    :param timeout: Timeout de la petición HTTP en segundos.
    :return: ExchangeRateLimits con información de REQUEST_WEIGHT, etc.
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
