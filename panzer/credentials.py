# panzer/credentials.py
"""
Gestor de credenciales con cifrado en disco y en memoria.

Arquitectura de tres capas:
1. **Memoria** -- diccionario interno con valores cifrados.
2. **Disco** -- archivo ``~/.panzer_creds`` con pares ``nombre = "valor"``.
   Los valores sensibles se guardan cifrados con ``AesCipher``.
3. **Prompt** -- si una credencial no existe ni en memoria ni en disco,
   se solicita al usuario (con ``getpass`` para las sensibles).

Flujo de ``get(name)``:
    memoria -> disco -> prompt -> almacenar en las tres capas.
"""

from __future__ import annotations

import os
from getpass import getpass

from panzer.crypto import AesCipher
from panzer.log_manager import LogManager

_log = LogManager(
    name="panzer.credentials",
    folder="logs",
    filename="credentials.log",
    level="INFO",
)

_SENSITIVE_MARKERS = ("secret", "api_key", "password", "_id")


def _is_sensitive(name: str) -> bool:
    """Determina si un nombre de variable es sensible."""
    lower = name.lower()
    return any(m in lower for m in _SENSITIVE_MARKERS)


class CredentialManager:
    """
    Gestor de credenciales cifradas en memoria y disco.

    Parameters
    ----------
    filename : str
        Nombre del archivo de credenciales en ``$HOME``.
    """

    def __init__(self, filename: str = ".panzer_creds") -> None:
        self._cipher = AesCipher()
        self._cache: dict[str, str] = {}
        self._filepath = os.path.join(os.path.expanduser("~"), filename)
        self._ensure_file()

    # ── Archivo ──────────────────────────────────────────────

    def _ensure_file(self) -> None:
        """Crea el archivo si no existe."""
        if not os.path.exists(self._filepath):
            with open(self._filepath, "w") as f:
                f.write("# Archivo de credenciales de Panzer\n")
            _log.info("Archivo de credenciales creado en: %s", self._filepath)

    def _read_from_file(self, name: str) -> str | None:
        """Lee una variable del archivo. Devuelve None si no existe."""
        if not os.path.exists(self._filepath):
            return None
        with open(self._filepath) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{name} ="):
                    try:
                        return stripped.split(" = ", 1)[1].strip().strip('"')
                    except IndexError:
                        return None
        return None

    def _write_to_file(self, name: str, value: str, *, overwrite: bool = False) -> None:
        """Escribe una variable en el archivo (ya cifrada si procede)."""
        if os.path.exists(self._filepath):
            with open(self._filepath) as f:
                lines = f.readlines()
        else:
            lines = []

        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{name} ="):
                found = True
                if overwrite:
                    lines[i] = f'{name} = "{value}"\n'
                break

        if not found:
            lines.append(f'{name} = "{value}"\n')

        with open(self._filepath, "w") as f:
            f.writelines(lines)

    # ── API publica ──────────────────────────────────────────

    def get(self, name: str, *, decrypt: bool = False) -> str:
        """
        Obtiene una credencial. Busca en memoria, disco y prompt (en ese orden).

        Parameters
        ----------
        name : str
            Nombre de la credencial (ej: ``"api_key"``, ``"api_secret"``).
        decrypt : bool
            Si es True, descifra el valor antes de devolverlo.

        Returns
        -------
        str
            Valor de la credencial (cifrado o plano segun ``decrypt``).
        """
        # 1. Memoria
        if name in self._cache:
            value = self._cache[name]
            return self._cipher.decrypt(value) if decrypt and _is_sensitive(name) else value

        # 2. Disco
        from_file = self._read_from_file(name)
        if from_file is not None:
            self._cache[name] = from_file
            return self._cipher.decrypt(from_file) if decrypt and _is_sensitive(name) else from_file

        # 3. Prompt
        _log.info("Credencial '%s' no encontrada. Solicitando al usuario.", name)
        value = self._prompt_and_store(name)
        return self._cipher.decrypt(value) if decrypt and _is_sensitive(name) else value

    def add(
        self,
        name: str,
        value: str,
        *,
        sensitive: bool | None = None,
        overwrite: bool = False,
    ) -> str:
        """
        Anade una credencial a memoria y disco.

        Parameters
        ----------
        name : str
            Nombre de la variable.
        value : str
            Valor en texto plano.
        sensitive : bool | None
            Forzar cifrado (True/False) o detectar automaticamente (None).
        overwrite : bool
            Sobreescribir si ya existe en disco.

        Returns
        -------
        str
            Valor almacenado (cifrado si es sensible).
        """
        is_sens = sensitive if sensitive is not None else _is_sensitive(name)
        stored = self._cipher.encrypt(value) if is_sens else value
        self._cache[name] = stored
        self._write_to_file(name, stored, overwrite=overwrite)
        return stored

    @property
    def filepath(self) -> str:
        """Ruta del archivo de credenciales."""
        return self._filepath

    # ── Internos ─────────────────────────────────────────────

    def _prompt_and_store(self, name: str) -> str:
        """Solicita una credencial al usuario y la almacena."""
        is_sens = _is_sensitive(name)
        prompt_msg = f"Introduce el valor para {name}: "
        raw = getpass(prompt_msg) if is_sens else input(prompt_msg)
        stored = self._cipher.encrypt(raw) if is_sens else raw
        self._cache[name] = stored
        self._write_to_file(name, stored)
        _log.info("Credencial '%s' almacenada (%s).", name, "cifrada" if is_sens else "plana")
        return stored

    def __repr__(self) -> str:
        if os.path.exists(self._filepath):
            with open(self._filepath) as f:
                return f"CredentialManager({self._filepath}):\n{f.read()}"
        return f"CredentialManager({self._filepath}): archivo no existe"
