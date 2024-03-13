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
    Class for flexibly searching and importing the 'secret.py' module
    from anywhere within the project directory hierarchy.
    """
    def __init__(self):
        self.secret_module = None
        self.find_and_import_secret_module()

    def find_and_import_secret_module(self) -> bool:
        """
        Searches for and imports the 'secret.py' module.

        :return: True if the module was found and successfully loaded, False otherwise.
        """
        current_dir = os.path.abspath(os.curdir)
        while True:
            try:
                self.secret_module = importlib.import_module('secret')
                # print("SECRET module found and imported!")
                return True
            except ModuleNotFoundError:
                parent_dir = os.path.dirname(current_dir)

                if parent_dir == current_dir:  # it is at the top of the file system
                    print("SECRET module not found!")
                    return False

                current_dir = parent_dir
                sys.path.insert(0, current_dir)

    def get_secret(self, secret_name: str) -> Union[None, str]:
        """
        Retrieves a secret by name from the imported 'secret' module.

        :param secret_name: The name of the secret to retrieve.
        :return: The value of the secret if it exists, None otherwise.
        """
        if self.secret_module and hasattr(self.secret_module, secret_name):
            return getattr(self.secret_module, secret_name)
        else:
            print(f"Secret '{secret_name}' not found in module.")
            return None


class AesCipher(object):
    """
    Encryption object.

    Initialization function. Generates a key and an initialization vector based on the CPU information and the user's home directory.
    """

    def __init__(self):
        __seed = bytes(expanduser("~") + get_cpu_info()['brand_raw'], "utf8")
        self.__iv = hashlib.md5(__seed).hexdigest()
        self.__key = hashlib.md5(__seed[::-1]).hexdigest()

    def encrypt(self, msg: str) -> str:
        """
        Encryption function. Encrypts a message using AES-128-CBC.

        :param msg: Any message to encrypt.
        :return: A base64 encoded string of bytes.
        """
        msg_padded = pad(msg.encode(), AES.block_size)
        cipher = AES.new(unhexlify(self.__key), AES.MODE_CBC, unhexlify(self.__iv))
        cipher_text = cipher.encrypt(msg_padded)
        return b64encode(cipher_text).decode('utf-8')

    def decrypt(self, msg_encrypted: str) -> str:
        """
        Decryption function. Decrypts a message using AES-128-CBC.

        :param msg_encrypted: A base64 encoded string of bytes.
        :return: Plain text.
        """
        decipher = AES.new(unhexlify(self.__key), AES.MODE_CBC, unhexlify(self.__iv))
        plaintext = unpad(decipher.decrypt(b64decode(msg_encrypted)), AES.block_size).decode('utf-8')
        return plaintext


class SecureKeychain:
    """
    Manages secure keys. It keeps keys encrypted in memory and provides them decrypted on demand. This class utilizes an
    encryption cipher for the encryption and decryption of key values, ensuring that sensitive information is not
    stored or used in plain text.
    """

    def __init__(self):
        self.cipher = AesCipher()
        self.encrypted_keys = {}

    def add_key(self, key_name: str, key_value: str):
        """
        Adds a key to the manager, encrypting it before storage.

        :param key_name: The name of the key.
        :param key_value: The value of the key.
        """
        self.encrypted_keys[key_name] = self.cipher.encrypt(key_value)

    def get_key(self, key_name: str) -> str:
        """
        Retrieves a key from the manager, decrypting its value.

        :param key_name: The name of the key to retrieve.
        :return: The decrypted value of the key.
        """
        if key_name in self.encrypted_keys:
            return self.cipher.decrypt(self.encrypted_keys[key_name])
        else:
            raise KeyError(f"Key not found: {key_name}")

    def add_encrypted_key(self, key_name: str, key_value: str) -> None:
        """
         Adds a key to the manager without encrypting it, assuming the key is already encrypted.

         :param key_name: The name of the key.
         :param key_value: The already encrypted value of the key.
         """
        self.encrypted_keys[key_name] = key_value

    def get_encrypted_key(self, key_name: str) -> str:
        """
        Retrieves an encrypted key from the manager without decrypting its value.

        :param key_name: The name of the key to retrieve.
        :return: The encrypted value of the key.
        """
        if key_name in self.encrypted_keys:
            return self.encrypted_keys[key_name]
        else:
            raise KeyError(f"Key not found: {key_name}")
