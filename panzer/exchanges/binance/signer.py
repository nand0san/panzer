# panzer/exchanges/binance/signer.py
"""
Firma HMAC-SHA256 para peticiones autenticadas a la API de Binance.

Tipos de seguridad de Binance:
- NONE: endpoints publicos, sin firma ni API key.
- TRADE / MARGIN / USER_DATA: requieren API key en header + firma HMAC.
- USER_STREAM / MARKET_DATA: requieren API key en header, sin firma.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from panzer.credentials import CredentialManager
from panzer.log_manager import LogManager

_log = LogManager(
    name="panzer.binance.signer",
    folder="logs",
    filename="binance_signer.log",
    level="INFO",
)


class BinanceRequestSigner:
    """
    Firma peticiones para la API de Binance usando HMAC-SHA256.

    Obtiene ``api_key`` y ``api_secret`` del ``CredentialManager``
    bajo demanda (memoria -> disco -> prompt al usuario).

    Parameters
    ----------
    credentials : CredentialManager | None
        Gestor de credenciales. Si es ``None``, crea uno por defecto.

    Attributes
    ----------
    api_key : str
        API key descifrada (propiedad de solo lectura).
    api_secret : str
        API secret descifrada (propiedad de solo lectura).

    See Also
    --------
    CredentialManager : Almacenamiento seguro de credenciales.
    BinanceClient : Consumidor principal de esta clase.
    """

    def __init__(self, credentials: CredentialManager | None = None) -> None:
        self._credentials = credentials or CredentialManager()

    @property
    def api_key(self) -> str:
        """API key descifrada desde ``CredentialManager``."""
        return self._credentials.get("api_key", decrypt=True)

    @property
    def api_secret(self) -> str:
        """API secret descifrada desde ``CredentialManager``."""
        return self._credentials.get("api_secret", decrypt=True)

    def headers_with_api_key(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """
        Devuelve headers con ``X-MBX-APIKEY`` inyectado.

        Parameters
        ----------
        headers : dict | None
            Headers existentes. Si es None, crea un dict nuevo.

        Returns
        -------
        dict[str, str]
            Headers con la API key.
        """
        h = dict(headers) if headers else {}
        h["X-MBX-APIKEY"] = self.api_key
        return h

    def sign_params(
        self,
        params: list[tuple[str, str | int]],
        *,
        add_timestamp: bool = True,
        server_time_offset_ms: int = 0,
    ) -> list[tuple[str, str | int]]:
        """
        Firma los parametros con HMAC-SHA256 y anade timestamp + signature.

        Parameters
        ----------
        params : list[tuple[str, str | int]]
            Pares (clave, valor) de la peticion.
        add_timestamp : bool
            Si True, anade ``timestamp`` automaticamente.
        server_time_offset_ms : int
            Desfase servidor-local en ms (positivo = servidor adelantado).

        Returns
        -------
        list[tuple[str, str | int]]
            Parametros con ``timestamp`` y ``signature`` anadidos.
        """
        result = list(params)

        has_timestamp = any(k == "timestamp" for k, _ in result)
        if add_timestamp and not has_timestamp:
            now_ms = int(time.time() * 1000) + server_time_offset_ms
            result.append(("timestamp", now_ms))

        query_string = "&".join(f"{k}={v}" for k, v in result)
        signature = hmac.new(
            key=self.api_secret.encode(),
            msg=query_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        result.append(("signature", signature))

        _log.debug("Parametros firmados: %d pares", len(result))
        return result
