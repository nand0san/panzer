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

    :param ask_for_missing: If True, the class will ask for missing keys and add them to the secret module ciphered.
    """
    def __init__(self, ask_for_missing: bool = True):
        self.secret_module = None
        self.find_and_import_secret_module()
        self.ask_missing = ask_for_missing
        self.cipher = AesCipher()

    def find_and_import_secret_module(self) -> bool:
        """
        Searches for and imports the 'secret.py' module.

        :return: True if the module was found and successfully loaded, False otherwise.
        """
        current_dir = os.path.abspath(os.curdir)
        while True:
            try:
                self.secret_module = importlib.import_module('secret')
                print("SECRET module found and imported!")
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
            if self.ask_missing:
                self.add_key_to_secret(key_name=secret_name)
                return self.get_secret(secret_name=secret_name)
            else:
                raise Exception(f"Secret '{secret_name}' not found in module.")

    def add_key_to_secret(self, key_name: str) -> None:
        """
        Checks if exists in a file and if not, then adds a line with the api key value for working with the package.

        :param str key_name: Variable name to import it later.
        """
        assert type(key_name) == str, "The key name must be a string."
        filename = "secret.py"
        saved_data = self.read_file(filename=filename)
        lines = []
        for line in saved_data:
            if line:
                if not line.strip().startswith(key_name):
                    lines.append(line.strip())
        new_key = input(f"Missing key '{key_name}'. Please enter the value: ")

        encrypted = self.cipher.encrypt(new_key)
        lines.append(f'{key_name} = "{encrypted}"')
        self.save_file(filename=filename, data=lines)
        # import again the module
        self.unload_imported_module()
        self.find_and_import_secret_module()

    @staticmethod
    def read_file(filename: str) -> list:
        """
        Read a file to a list of strings each line.

        :return list: list with a string each row in the file.
        """
        if not os.path.isfile(filename):
            return []
        with open(filename, 'r') as f:
            lines = f.readlines()
            lines = [line.rstrip() for line in lines if line]
        return lines

    @staticmethod
    def save_file(filename: str, data: list, mode='w') -> None:
        """
        Save a new file from a list of lists each line.

        :param str filename: a file name to save.
        :param list data: Data in a list of strings each line.
        :param str mode: 'w' to rewrite full file or 'a' to append to existing file.

        """
        with open(filename, mode) as f:
            for line in sorted(data):
                f.write(str(line) + '\n')

    def unload_imported_module(self):
        """
        Unloads the imported 'secret' module, allowing it to be re-imported to reflect any changes.
        """
        module_name = 'secret'
        if module_name in sys.modules:
            del sys.modules[module_name]
            # print("SECRET module unloaded!")
            self.secret_module = None

    def __str__(self):
        return f"SecretModuleImporter(ask_for_missing={self.ask_missing})"

    def __repr__(self):
        return f"SecretModuleImporter(ask_for_missing={self.ask_missing})"


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
