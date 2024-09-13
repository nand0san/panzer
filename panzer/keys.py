from os.path import expanduser
from cpuinfo import get_cpu_info
import hashlib
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from binascii import unhexlify
import os
from typing import Optional
from getpass import getpass

from panzer.logs import LogManager


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

    def add_key(self, key_name: str, key_value: str, is_sensitive: bool) -> None:
        """
         Adds a key to the manager, if is sensitive, it will encrypt value.

         :param key_name: The name of the key.
         :param key_value: The already encrypted value of the key.
         :param is_sensitive: If True, the key is sensitive.
         """
        if is_sensitive:
            key_value = self.cipher.encrypt(key_value)
        self.encrypted_keys[key_name] = key_value

    def get_key(self, key_name: str, decrypt: bool = False) -> str:
        """
        Retrieves from the manager and decrypting its value if decrypt is True.

        :param key_name: The name of the key to retrieve.
        :param decrypt: If True, it returns decrypted value.
        :return: The encrypted value of the key.
        """
        if key_name in self.encrypted_keys:
            if decrypt:
                return self.cipher.decrypt(self.encrypted_keys[key_name])
            else:
                return self.encrypted_keys[key_name]
        else:
            raise KeyError(f"Key not found: {key_name}")


class CredentialFileManager:
    def __init__(self, filename='panzer.tmp', info_level: str = "INFO"):
        """
        Inicializa la clase de gestión de credenciales. Busca o crea el archivo de credenciales.
        """
        self.logger = LogManager(filename="credential_manager.log", info_level=info_level)
        self.filename = filename
        self.filepath = self.get_credentials_file_path()
        self.cipher = AesCipher()

    def get_credentials_file_path(self) -> str:
        """
        Localiza el archivo de credenciales en la carpeta home del usuario.
        Si el archivo no existe, lo crea vacío.

        :return: Ruta completa del archivo.
        """
        home_dir = os.path.expanduser("~")  # Obtiene la carpeta home (Windows y Linux)
        credentials_path = os.path.join(home_dir, self.filename)

        # Si el archivo no existe, lo crea vacío
        if not os.path.exists(credentials_path):
            with open(credentials_path, 'w') as f:
                f.write("# Archivo de credenciales de Panzer\n")
            self.logger.info(f"Archivo de credenciales creado en: {credentials_path}")
        return credentials_path

    def _read_variable(self, variable_name: str) -> Optional[str]:
        """
        Lee el archivo de credenciales y busca la variable especificada. Si no existe, devuelve None.

        :param variable_name: Nombre de la variable que se quiere leer.
        :return: Valor de la variable o None si no existe. Tal y como esté en el archivo.
        """
        if not os.path.exists(self.filepath):
            self.logger.info(f"Archivo de credenciales no existe: {self.filepath}")
            return None

        # Leer el archivo línea por línea
        with open(self.filepath, 'r') as f:
            lines = f.readlines()

        # Buscar la variable en el archivo
        for line in lines:
            line = line.strip()  # Eliminar espacios en blanco y saltos de línea
            if line.startswith(f"{variable_name} ="):
                # Extraer el valor entre comillas
                try:
                    return line.split(' = ')[1].strip().strip('"')
                except IndexError:
                    self.logger.error(f"Error al procesar la variable {variable_name} en el archivo.")
                    return None

        # Si no se encontró la variable, devolver None
        return None

    def prompt_and_store_variable(self, variable_name: str) -> str:
        """
        Solicita al usuario que introduzca una variable y la almacena en el archivo de credenciales.
        Si la variable contiene "api_key", "api_secret", "password", o termina en "_id", se cifrará.

        :param variable_name: Nombre de la variable a solicitar.
        :return: El valor almacenado.
        """
        is_sensitive = any(substring in variable_name for substring in ['secret', 'api_key', 'password', '_id'])
        self.logger.info(f"Sensitive prompt!")
        prompt_message = f"Por favor, introduce el valor para {variable_name}: "

        # Si es una variable sensible, usa getpass para ocultar la entrada del usuario
        if is_sensitive:
            user_input = getpass(prompt_message)  # Oculta la entrada si es sensible
        else:
            user_input = input(prompt_message)

        # Añade la variable al archivo
        self.add_variable_to_file(variable_name, user_input, is_sensitive=is_sensitive)
        return user_input

    def add_variable_to_file(self, variable_name: str, variable_value: str, is_sensitive: bool) -> str:
        """
        Adds or replaces a variable in the credentials file.

        If the variable already exists, its value will be replaced. If it does not exist, a new line with the variable will be added.

        :param variable_name: Name of the variable.
        :param variable_value: Value of the variable.
        :param is_sensitive: If it is sensitive, it will be encrypted.
        :return: The value stored. Encrypted if it is sensitive.
        """
        if is_sensitive:
            variable_value = self.cipher.encrypt(variable_value)

        # Read all lines of the file
        if os.path.exists(self.filepath):
            with open(self.filepath, 'r') as f:
                lines = f.readlines()
        else:
            lines = []

        # Check if the variable already exists in the file
        variable_found = False
        for line in lines:
            if line.startswith(f"{variable_name} ="):
                variable_found = True

        # If the variable was not found, add it to the end
        if not variable_found:
            # Open the file in append mode to add the variable
            with open(self.filepath, 'a') as f:
                f.write(f'{variable_name} = "{variable_value}"\n')
            self.logger.info(f"Variable {variable_name} added to credentials file.")
            return variable_value
        else:
            self.logger.info(f"Variable {variable_name} exists in cache file. "
                             f"To renew it delete line in cache file at: {self.filepath}")
            # return file value
            return self._read_variable(variable_name)

    def get_or_prompt_variable(self, variable_name: str, prompt: bool = True) -> str:
        """
        Obtiene el valor de una variable del archivo de credenciales, tal y como esté, o la solicita si no existe.

        :param variable_name: Nombre de la variable a buscar o solicitar.
        :param prompt: Si es True, pregunta para añadir la clave.
        :return: Valor de la variable tal y como esté en el archivo.
        """
        value = self._read_variable(variable_name)
        if value is None:
            if prompt:
                self.logger.info(f"La variable {variable_name} no existe en el archivo. Solicitándola...")
                value = self.prompt_and_store_variable(variable_name)
            else:
                self.logger.warning(f"La variable {variable_name} no existe en el archivo.")
        return value

    def __repr__(self):
        """
        Devuelve una representación oficial del objeto, mostrando el path del archivo y su contenido si existe.

        :return: str con la representación del archivo.
        """
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    lines = f.readlines()
            except Exception as e:
                return f"Error reading file {self.filepath}: {e}"
            return f"File at {self.filepath}:\n{''.join(lines)}"
        else:
            return f"File at {self.filepath} does not exist."


class CredentialManager:
    def __init__(self, info_level: str = "INFO"):
        """
        Inicializa el gestor de credenciales que mantiene las credenciales en memoria.
        Usa el CredentialFileManager para acceder al archivo de credenciales solo cuando sea necesario.

        :param info_level: Nivel de logging.
        """
        self.logger = LogManager(filename="logs/credential_manager.log", info_level=info_level)
        self.file_manager = CredentialFileManager()
        self.credentials = {}  # Diccionario para almacenar las credenciales en memoria, pertinentemente encriptadas.

    def encrypt_value(self, value: str) -> str:
        return self.file_manager.cipher.encrypt(msg=value)

    def decrypt_value(self, value: str):
        return self.file_manager.cipher.decrypt(msg_encrypted=value)

    def get(self, variable_name: str, decrypt: bool = False) -> str:
        """
        Intenta obtener una credencial de memoria. Si no está disponible, la obtiene del archivo
        de credenciales o la solicita al usuario si no existe.

        :param variable_name: Nombre de la variable que se desea obtener.
        :param decrypt: Si True, desencripta el valor almacenado.
        :return: Valor de la credencial. Cifrada en su caso.
        """
        # Si la credencial está en memoria, la devuelve
        if variable_name in self.credentials:
            ret = self.credentials[variable_name]
        else:
            self.logger.debug(f"Credential not found in object: {variable_name}. Searching in file.")
            ret = self.file_manager.get_or_prompt_variable(variable_name, prompt=True)
            self.credentials.update({variable_name: ret})

        if decrypt:
            return self.decrypt_value(ret)
        else:
            return ret

    def add(self, variable_name: str, variable_value: str, is_sensitive: bool) -> str:
        """
        Añade una variable en memoria, si es sensible, se almacena cifrada. También la almacena en disco.

        :param variable_name: Nombre de la variable a almacenar en memoria.
        :param variable_value:
        :param is_sensitive:
        :return:
        """
        if is_sensitive:
            variable_value = self.encrypt_value(variable_value)
        self.credentials.update({variable_name: variable_value})
        # verifies if it is in the file and if it is not, it adds it.
        # Since it already comes encrypted, it saves it in non-sensitive mode to avoid re-encryption.
        variable_value = self._save(variable_name, variable_value, is_sensitive=False)
        return variable_value

    def _save(self, variable_name: str, variable_value: str, is_sensitive: bool):
        """
        Almacena la variable en archivo. Si es o no sensible, debe haberse gestionado previamente.

        :param variable_name: Nombre de la variable que se desea almacenar.
        :param variable_value: Valor de la variable, cifrado o no, previamente se debe haber gestionado.
        :param is_sensitive: Si es sensible la cifrará al almacenarla. Si ya viene cifrada debe usarse en modo False.
        :return:
        """
        # sensitive en false, si es o no sensible, debe haberse gestionado anteriormente.
        return self.file_manager.add_variable_to_file(variable_name, variable_value, is_sensitive=is_sensitive)

    def __repr__(self) -> str:
        return self.credentials.__repr__()
