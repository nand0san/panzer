from os.path import expanduser
from cpuinfo import get_cpu_info
import hashlib
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from binascii import unhexlify
import os
import sys
import importlib
from typing import Union


class SecretModuleImporter:
    """
    Clase para buscar e importar de manera flexible el módulo 'secret.py'
    desde cualquier lugar en la jerarquía de directorios del proyecto.
    """

    def __init__(self):
        self.secret_module = None
        self.find_and_import_secret_module()

    def find_and_import_secret_module(self):
        """
        Busca y importa el módulo 'secret.py'.

        :return: True si el módulo fue encontrado y cargado con éxito, False de lo contrario.
        """
        current_dir = os.path.abspath(os.curdir)
        while True:
            try:
                self.secret_module = importlib.import_module('secret')
                # print("SECRET module found and imported!")
                return True
            except ModuleNotFoundError:
                parent_dir = os.path.dirname(current_dir)

                if parent_dir == current_dir:
                    print("SECRET module not found!")
                    return False

                current_dir = parent_dir
                sys.path.insert(0, current_dir)

    def get_secret(self, secret_name: str) -> Union[None, str]:
        """
        Obtiene un secreto por nombre desde el módulo 'secret' importado.

        :param secret_name: El nombre del secreto a obtener.
        :return: El valor del secreto si existe, None de lo contrario.
        """
        if self.secret_module and hasattr(self.secret_module, secret_name):
            return getattr(self.secret_module, secret_name)
        else:
            print(f"Secret '{secret_name}' not found in module.")
            return None


class AesCipher(object):
    """
    Objeto de cifrado.

    Función de inicialización. Genera una clave y un vector de inicialización basados en la información de la CPU y el home del usuario.
    """

    def __init__(self):
        __seed = bytes(expanduser("~") + get_cpu_info()['brand_raw'], "utf8")
        self.__iv = hashlib.md5(__seed).hexdigest()
        self.__key = hashlib.md5(__seed[::-1]).hexdigest()

    def encrypt(self, msg: str) -> str:
        """
        Función de cifrado. Cifra un mensaje con AES-128-CBC.

        :param str msg: Cualquier mensaje a cifrar.
        :return str: Una cadena en base64 de bytes.
        """
        msg_padded = pad(msg.encode(), AES.block_size)
        cipher = AES.new(unhexlify(self.__key), AES.MODE_CBC, unhexlify(self.__iv))
        cipher_text = cipher.encrypt(msg_padded)
        return b64encode(cipher_text).decode('utf-8')

    def decrypt(self, msg_encrypted: str) -> str:
        """
        Función de descifrado. Descifra un mensaje con AES-128-CBC.

        :param str msg_encrypted: Una cadena en base64 de bytes.
        :return str: Texto plano.
        """
        decipher = AES.new(unhexlify(self.__key), AES.MODE_CBC, unhexlify(self.__iv))
        plaintext = unpad(decipher.decrypt(b64decode(msg_encrypted)), AES.block_size).decode('utf-8')
        return plaintext


class SecureKeyManager:
    """
    Gestor de claves seguras. Mantiene las claves en memoria de forma cifrada y las proporciona descifradas bajo demanda.
    """

    def __init__(self):
        self.cipher = AesCipher()
        self.encrypted_keys = {}

    def add_key(self, key_name: str, key_value: str):
        """
        Añade una clave al gestor, cifrándola antes de almacenarla.

        :param str key_name: El nombre de la clave.
        :param str key_value: El valor de la clave.
        """
        self.encrypted_keys[key_name] = self.cipher.encrypt(key_value)

    def get_key(self, key_name: str) -> str:
        """
        Obtiene una clave del gestor, descifrando su valor.

        :param str key_name: El nombre de la clave.
        :return str: El valor de la clave descifrado.
        """
        if key_name in self.encrypted_keys:
            return self.cipher.decrypt(self.encrypted_keys[key_name])
        else:
            raise KeyError(f"Key not found: {key_name}")

    def add_encrypted_key(self, key_name: str, key_value: str):
        """
        Añade una clave al gestor, sin cifrarla.

        :param str key_name: El nombre de la clave.
        :param str key_value: El valor de la clave.
        """
        self.encrypted_keys[key_name] = key_value

    def get_encrypted_key(self, key_name: str) -> str:
        """
        Obtiene una clave del gestor, sin descifrar su valor.

        :param str key_name: El nombre de la clave.
        :return str: El valor de la clave sin descifrar.
        """
        if key_name in self.encrypted_keys:
            return self.encrypted_keys[key_name]
        else:
            raise KeyError("Key not found")
