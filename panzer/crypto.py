# panzer/crypto.py
"""
Cifrado AES-128-CBC para proteger credenciales en memoria y disco.

La clave y el vector de inicializacion se derivan deterministamente de
la identidad de la maquina (home del usuario + info de CPU), de modo
que las credenciales cifradas solo se pueden descifrar en la misma
maquina donde fueron creadas.

No requiere que el usuario introduzca ninguna contrasena.
"""

from __future__ import annotations

import hashlib
import platform
from base64 import b64decode, b64encode
from binascii import unhexlify
from os.path import expanduser

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class AesCipher:
    """
    Cifrado AES-128-CBC con clave derivada de la identidad de la maquina.

    La semilla se construye a partir de ``$HOME`` y la cadena de
    procesador reportada por ``platform.processor()``.  Si el
    procesador no esta disponible se usa ``platform.machine()``
    como fallback.

    Notes
    -----
    Las credenciales cifradas con esta clase solo se pueden descifrar
    en la misma maquina donde fueron creadas, ya que la clave depende
    del hardware y del usuario del sistema operativo.

    See Also
    --------
    CredentialManager : Gestor que usa esta clase para cifrar/descifrar.
    """

    def __init__(self) -> None:
        cpu_id = platform.processor() or platform.machine()
        seed = bytes(expanduser("~") + cpu_id, "utf-8")
        self._iv = hashlib.md5(seed).hexdigest()
        self._key = hashlib.md5(seed[::-1]).hexdigest()

    def encrypt(self, plaintext: str) -> str:
        """
        Cifra un texto plano.

        Parameters
        ----------
        plaintext : str
            Texto a cifrar.

        Returns
        -------
        str
            Texto cifrado codificado en base64.
        """
        padded = pad(plaintext.encode(), AES.block_size)
        cipher = AES.new(unhexlify(self._key), AES.MODE_CBC, unhexlify(self._iv))
        return b64encode(cipher.encrypt(padded)).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        Descifra un texto previamente cifrado con ``encrypt()``.

        Parameters
        ----------
        ciphertext : str
            Texto cifrado en base64.

        Returns
        -------
        str
            Texto plano original.
        """
        decipher = AES.new(unhexlify(self._key), AES.MODE_CBC, unhexlify(self._iv))
        return unpad(decipher.decrypt(b64decode(ciphertext)), AES.block_size).decode("utf-8")
