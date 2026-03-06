"""
Tests unitarios para el gestor de credenciales.

Usa archivos temporales para no tocar ``~/.panzer_creds``.
No requiere conexion a internet.
"""

from __future__ import annotations

import os

import pytest

from panzer.credentials import CredentialManager, _is_sensitive

# =====================================================================
# Helpers
# =====================================================================

@pytest.fixture()
def tmp_creds(tmp_path: object) -> CredentialManager:
    """CredentialManager con archivo temporal (no toca $HOME)."""
    # tmp_path es un pathlib.Path de pytest
    filepath = os.path.join(str(tmp_path), ".panzer_creds_test")
    # Crear el CM apuntando al archivo temporal
    cm = CredentialManager.__new__(CredentialManager)
    from panzer.crypto import AesCipher

    cm._cipher = AesCipher()
    cm._cache = {}
    cm._filepath = filepath
    cm._ensure_file()
    return cm


# =====================================================================
# _is_sensitive
# =====================================================================

class TestIsSensitive:
    """Deteccion automatica de nombres sensibles."""

    def test_api_key_is_sensitive(self) -> None:
        assert _is_sensitive("api_key") is True

    def test_api_secret_is_sensitive(self) -> None:
        assert _is_sensitive("api_secret") is True

    def test_password_is_sensitive(self) -> None:
        assert _is_sensitive("my_password") is True

    def test_telegram_id_is_sensitive(self) -> None:
        assert _is_sensitive("telegram_id") is True

    def test_plain_name_not_sensitive(self) -> None:
        assert _is_sensitive("market") is False
        assert _is_sensitive("base_url") is False

    def test_case_insensitive(self) -> None:
        assert _is_sensitive("API_KEY") is True
        assert _is_sensitive("Api_Secret") is True


# =====================================================================
# CredentialManager -- add / get
# =====================================================================

class TestCredentialManagerAddGet:
    """Almacenar y recuperar credenciales."""

    def test_add_and_get_plain(self, tmp_creds: CredentialManager) -> None:
        """Variable no sensible se almacena en texto plano."""
        tmp_creds.add("market", "spot")
        assert tmp_creds.get("market") == "spot"

    def test_add_and_get_sensitive_encrypted(self, tmp_creds: CredentialManager) -> None:
        """Variable sensible se almacena cifrada y se descifra con decrypt=True."""
        tmp_creds.add("api_key", "my_real_key_123")
        # Sin descifrar: devuelve el valor cifrado
        encrypted = tmp_creds.get("api_key", decrypt=False)
        assert encrypted != "my_real_key_123"
        # Con descifrar: devuelve el valor original
        assert tmp_creds.get("api_key", decrypt=True) == "my_real_key_123"

    def test_add_and_get_secret(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("api_secret", "super_secret_456")
        assert tmp_creds.get("api_secret", decrypt=True) == "super_secret_456"

    def test_force_sensitive(self, tmp_creds: CredentialManager) -> None:
        """Forzar cifrado en variable que no seria autodetectada."""
        tmp_creds.add("token", "abc123", sensitive=True)
        encrypted = tmp_creds.get("token", decrypt=False)
        assert encrypted != "abc123"

    def test_force_not_sensitive(self, tmp_creds: CredentialManager) -> None:
        """Forzar texto plano en variable que seria autodetectada."""
        tmp_creds.add("api_key", "plain_value", sensitive=False)
        assert tmp_creds.get("api_key") == "plain_value"


# =====================================================================
# CredentialManager -- persistencia en disco
# =====================================================================

class TestCredentialManagerPersistence:
    """Los datos persisten en el archivo."""

    def test_file_created(self, tmp_creds: CredentialManager) -> None:
        assert os.path.exists(tmp_creds.filepath)

    def test_value_persists_to_disk(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("market", "um")
        with open(tmp_creds.filepath) as f:
            content = f.read()
        assert 'market = "um"' in content

    def test_sensitive_persists_encrypted(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("api_secret", "the_secret")
        with open(tmp_creds.filepath) as f:
            content = f.read()
        # El secreto no debe aparecer en plano
        assert "the_secret" not in content
        # Pero api_secret = "..." si debe estar
        assert "api_secret =" in content

    def test_read_from_disk_after_cache_clear(self, tmp_creds: CredentialManager) -> None:
        """Simula reinicio: limpia cache y relee de disco."""
        tmp_creds.add("market", "cm")
        # Limpiar cache en memoria
        tmp_creds._cache.clear()
        # Debe recuperar del archivo
        assert tmp_creds.get("market") == "cm"

    def test_sensitive_roundtrip_disk(self, tmp_creds: CredentialManager) -> None:
        """Cifrado -> disco -> limpia cache -> lee disco -> descifra."""
        tmp_creds.add("api_key", "roundtrip_key")
        tmp_creds._cache.clear()
        assert tmp_creds.get("api_key", decrypt=True) == "roundtrip_key"

    def test_overwrite(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("market", "spot")
        tmp_creds.add("market", "um", overwrite=True)
        tmp_creds._cache.clear()
        assert tmp_creds.get("market") == "um"

    def test_no_overwrite_keeps_original(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("market", "spot")
        tmp_creds.add("market", "um", overwrite=False)
        tmp_creds._cache.clear()
        # Sin overwrite, el archivo mantiene el valor original
        assert tmp_creds.get("market") == "spot"


# =====================================================================
# CredentialManager -- multiples variables
# =====================================================================

class TestCredentialManagerMultiple:
    """Varias variables coexisten sin interferencia."""

    def test_multiple_variables(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("api_key", "key_1")
        tmp_creds.add("api_secret", "secret_2")
        tmp_creds.add("market", "spot")

        assert tmp_creds.get("api_key", decrypt=True) == "key_1"
        assert tmp_creds.get("api_secret", decrypt=True) == "secret_2"
        assert tmp_creds.get("market") == "spot"

    def test_multiple_persist_after_cache_clear(self, tmp_creds: CredentialManager) -> None:
        tmp_creds.add("api_key", "k1")
        tmp_creds.add("api_secret", "s1")
        tmp_creds.add("base_url", "https://api.binance.com")
        tmp_creds._cache.clear()

        assert tmp_creds.get("api_key", decrypt=True) == "k1"
        assert tmp_creds.get("api_secret", decrypt=True) == "s1"
        assert tmp_creds.get("base_url") == "https://api.binance.com"

    def test_repr_shows_filepath(self, tmp_creds: CredentialManager) -> None:
        result = repr(tmp_creds)
        assert tmp_creds.filepath in result
