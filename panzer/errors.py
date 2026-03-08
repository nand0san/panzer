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
    Carga util de error tipica de la API de Binance.

    Binance devuelve errores con la estructura ``{"code": <int>, "msg": <str>}``.
    Este dataclass encapsula ambos campos de forma tipada.

    Attributes
    ----------
    code : int | None
        Codigo de error de Binance (negativo por convencion, ej. ``-1121``).
        ``None`` si no se pudo parsear.
    msg : str | None
        Mensaje descriptivo del error (ej. ``"Invalid symbol."``).
        ``None`` si no viene en la respuesta.

    Examples
    --------
    >>> payload = BinanceAPIErrorPayload.from_dict({"code": -1121, "msg": "Invalid symbol."})
    >>> payload.code
    -1121
    """

    code: int | None
    msg: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BinanceAPIErrorPayload:
        """
        Construye un payload a partir de un diccionario JSON.

        Parameters
        ----------
        data : dict[str, Any]
            Diccionario con claves opcionales ``"code"`` y ``"msg"``.

        Returns
        -------
        BinanceAPIErrorPayload
            Instancia con los valores parseados y tipados.
        """
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
    Excepcion para errores devueltos por la API de Binance.

    Se lanza tanto ante errores HTTP (4xx/5xx) como ante respuestas con
    ``status_code`` 200 que contienen un ``"code"`` negativo en el cuerpo JSON.

    Attributes
    ----------
    status_code : int
        Codigo de estado HTTP de la respuesta.
    method : str
        Metodo HTTP usado (``"GET"``, ``"POST"``, ``"DELETE"``).
    url : str
        URL completa de la peticion.
    error_payload : BinanceAPIErrorPayload | None
        Codigo y mensaje de error de Binance, si se pudo parsear.
    body : str | None
        Cuerpo de la respuesta en texto bruto; util para debugging.

    See Also
    --------
    handle_response : Funcion que construye y lanza esta excepcion.
    BinanceAPIErrorPayload : Detalle del error de Binance.
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
    Intenta parsear JSON de la respuesta sin lanzar excepciones.

    Parameters
    ----------
    response : requests.Response
        Objeto Response devuelto por ``requests``.

    Returns
    -------
    tuple[dict[str, Any] | Any | None, str | None]
        ``(json_data, None)`` si se pudo parsear, o ``(None, raw_text)``
        si el cuerpo no es JSON valido.
    """
    try:
        data = response.json()
        return data, None
    except ValueError:
        # No es JSON válido; devolvemos el texto bruto
        return None, response.text


def _build_exception(response: requests.Response) -> BinanceAPIException:
    """
    Construye una ``BinanceAPIException`` a partir de un ``Response``.

    Extrae el payload de error del cuerpo JSON si tiene la estructura
    ``{"code": <int>, "msg": <str>}``, tanto para errores HTTP (4xx/5xx)
    como para errores logicos con status 200.

    Parameters
    ----------
    response : requests.Response
        Respuesta HTTP de Binance.

    Returns
    -------
    BinanceAPIException
        Excepcion lista para ser lanzada.
    """
    method = (response.request.method if response.request is not None else None) or "GET"
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

    - Si status_code no esta en 2xx, levanta ``BinanceAPIException``.
    - Si status_code es 2xx:
        - Se intenta parsear JSON.
        - Si el JSON es un dict con ``"code"`` < 0 (errores tipicos de
          Binance), levanta ``BinanceAPIException``.
        - En caso contrario, devuelve el JSON (o texto si no es JSON).

    Parameters
    ----------
    response : requests.Response
        Objeto Response devuelto por requests.

    Returns
    -------
    Any
        JSON parseado (dict o list) o texto si no es JSON.

    Raises
    ------
    BinanceAPIException
        Ante cualquier error interpretado.
    """
    status = response.status_code
    method = (response.request.method if response.request is not None else None) or "GET"
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
