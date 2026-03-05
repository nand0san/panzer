# panzer/errors.py
"""
Errores y manejo de respuestas para Panzer.

Se centra en:
- Interpretar correctamente las respuestas de la API de Binance.
- Unificar el punto donde se levantan excepciones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from panzer.log_manager import LogManager

# ==========================
# Logger específico del módulo
# ==========================

_log = LogManager(
    name="panzer.errors",
    folder="logs",
    filename="errors.log",
    level="INFO",
)


# ==========================
# Modelos de error
# ==========================


@dataclass
class BinanceAPIErrorPayload:
    """
    Representa la carga útil de error típica de la API de Binance.

    Ejemplo de cuerpo:
        {
            "code": -1121,
            "msg": "Invalid symbol."
        }
    """

    code: int | None
    msg: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BinanceAPIErrorPayload:
        code = data.get("code")
        msg = data.get("msg")

        try:
            code_int: int | None = int(code) if code is not None else None
        except (TypeError, ValueError):
            code_int = None

        msg_str = str(msg) if msg is not None else None

        return cls(code=code_int, msg=msg_str)


class BinanceAPIException(Exception):
    """
    Excepción base para errores devueltos por la API de Binance.

    Incluye:
    - status_code HTTP.
    - error_payload: código/mensaje de Binance (si se ha podido parsear).
    - url: URL de la petición.
    - method: GET/POST/DELETE...
    - body: contenido de la respuesta (texto bruto), útil para debugging.
    """

    def __init__(
        self,
        status_code: int,
        method: str,
        url: str,
        error_payload: BinanceAPIErrorPayload | None = None,
        body: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.method = method
        self.url = url
        self.error_payload = error_payload
        self.body = body

        base_msg = f"[{status_code}] {method} {url}"

        detail = f" (code={error_payload.code}, msg={error_payload.msg})" if error_payload is not None else ""

        super().__init__(base_msg + detail)


# ==========================
# Helpers internos
# ==========================


def _extract_json_safe(response: requests.Response) -> tuple[dict[str, Any] | Any | None, str | None]:
    """
    Intenta parsear JSON de la respuesta. Si falla, devuelve (None, texto).

    :return: (json_data, raw_text)
    """
    try:
        data = response.json()
        return data, None
    except ValueError:
        # No es JSON válido; devolvemos el texto bruto
        return None, response.text


def _build_exception(response: requests.Response) -> BinanceAPIException:
    """
    Construye una BinanceAPIException a partir de un objeto Response.

    Maneja tanto errores HTTP (4xx/5xx) como cuerpos con la forma:
        {"code": <int>, "msg": <str>}
    aunque vengan con status_code 200.
    """
    method = response.request.method if response.request is not None else "GET"
    url = response.url or "UNKNOWN"

    json_data, raw_text = _extract_json_safe(response)

    error_payload: BinanceAPIErrorPayload | None = None

    if isinstance(json_data, dict) and ("code" in json_data or "msg" in json_data):
        error_payload = BinanceAPIErrorPayload.from_dict(json_data)

    exc = BinanceAPIException(
        status_code=response.status_code,
        method=method,
        url=url,
        error_payload=error_payload,
        body=(
            raw_text
            if raw_text is not None
            else (json.dumps(json_data, ensure_ascii=False) if json_data is not None else None)
        ),
    )

    _log.error(
        "BinanceAPIException raised: status=%s method=%s url=%s code=%s msg=%s",
        exc.status_code,
        exc.method,
        exc.url,
        exc.error_payload.code if exc.error_payload else None,
        exc.error_payload.msg if exc.error_payload else None,
    )

    return exc


# ==========================
# API pública para manejo de respuestas
# ==========================


def handle_response(response: requests.Response) -> Any:
    """
    Valida una respuesta de la API de Binance.

    Comportamiento:
    - Si status_code no está en 2xx -> se levanta BinanceAPIException.
    - Si status_code es 2xx:
        - Se intenta parsear JSON.
        - Si el JSON es un dict con "code" < 0 (errores típicos de Binance),
          se levanta BinanceAPIException.
        - En caso contrario, se devuelve el JSON (o texto si no es JSON).

    :param response: Objeto requests.Response devuelto por requests.
    :return: JSON parseado (dict o list) o texto si no es JSON.
    :raises BinanceAPIException: ante cualquier error interpretado.
    """
    status = response.status_code
    method = response.request.method if response.request is not None else "GET"
    url = response.url or "UNKNOWN"

    _log.debug("handle_response: %s %s -> %s", method, url, status)

    # 1) Errores HTTP directos
    if not (200 <= status < 300):
        raise _build_exception(response)

    # 2) Intentamos parsear JSON
    json_data, raw_text = _extract_json_safe(response)

    if isinstance(json_data, dict):
        # Binance a veces devuelve errores con 200 pero code < 0
        if "code" in json_data:
            try:
                code_int = int(json_data["code"])
            except (TypeError, ValueError):
                code_int = None

            if code_int is not None and code_int < 0:
                # Es un error lógico de Binance aunque el HTTP sea 200
                raise _build_exception(response)

        return json_data

    if json_data is not None:
        # JSON válido pero no dict (p.ej. lista)
        return json_data

    # No hay JSON; devolvemos el texto bruto
    return raw_text
