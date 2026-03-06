"""
Tests unitarios para el modulo de cifrado AES.

No requieren conexion a internet ni credenciales reales.
"""

from __future__ import annotations

from panzer.crypto import AesCipher


class TestAesCipherRoundtrip:
    """Cifrar y descifrar devuelve el texto original."""

    def test_simple_string(self) -> None:
        c = AesCipher()
        assert c.decrypt(c.encrypt("hola mundo")) == "hola mundo"

    def test_empty_string(self) -> None:
        c = AesCipher()
        assert c.decrypt(c.encrypt("")) == ""

    def test_special_characters(self) -> None:
        c = AesCipher()
        text = "p@$$w0rd!#%&/()=?¿*+~{[]}"
        assert c.decrypt(c.encrypt(text)) == text

    def test_long_string(self) -> None:
        c = AesCipher()
        text = "A" * 10_000
        assert c.decrypt(c.encrypt(text)) == text

    def test_unicode(self) -> None:
        c = AesCipher()
        text = "clave_secreta_con_tildes_aeiou_y_enes_n"
        assert c.decrypt(c.encrypt(text)) == text

    def test_api_key_like(self) -> None:
        c = AesCipher()
        key = "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
        assert c.decrypt(c.encrypt(key)) == key


class TestAesCipherDeterminism:
    """La misma instancia produce el mismo cifrado (misma clave/iv)."""

    def test_same_instance_same_output(self) -> None:
        c = AesCipher()
        enc1 = c.encrypt("test")
        enc2 = c.encrypt("test")
        assert enc1 == enc2

    def test_different_instances_same_output(self) -> None:
        """Dos instancias en la misma maquina comparten clave."""
        c1 = AesCipher()
        c2 = AesCipher()
        enc1 = c1.encrypt("secreto")
        assert c2.decrypt(enc1) == "secreto"


class TestAesCipherOutput:
    """Propiedades del texto cifrado."""

    def test_encrypted_differs_from_plaintext(self) -> None:
        c = AesCipher()
        plaintext = "mi_api_secret_1234567890"
        encrypted = c.encrypt(plaintext)
        assert encrypted != plaintext

    def test_encrypted_is_base64(self) -> None:
        """El output es una cadena base64 valida."""
        import base64

        c = AesCipher()
        encrypted = c.encrypt("test_value")
        # No debe lanzar excepcion
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 0

    def test_different_inputs_different_outputs(self) -> None:
        c = AesCipher()
        assert c.encrypt("aaa") != c.encrypt("bbb")
