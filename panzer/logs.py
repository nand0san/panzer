"""

Logging functions

"""
from typing import Union
import requests
import logging
from os import makedirs, path
from logging.handlers import RotatingFileHandler
import csv
from requests.structures import CaseInsensitiveDict

class LogManager:
    """
    Main logging class.
    """

    def __init__(self,
                 filename: str,
                 name: str = None,
                 folder: str = 'logs',
                 info_level='DEBUG',
                 max_log_size_mb: int = 10,
                 backup_count: int = 5):

        if name is None:
            if '\\' in filename:
                name = filename.split('\\')[-1].split('.')[0]
            else:
                name = filename.split('/')[-1].split('.')[0]

        try:
            makedirs(name=folder, exist_ok=True)
        except PermissionError:  # linux
            home = path.expanduser('~')
            makedirs(f'{home}/.binpan/', exist_ok=True)

        self.logger = logging.getLogger(name)

        # avoid duplicated logs
        if self.logger.hasHandlers():
            self.logger.handlers = []

        self.log_file = filename

        # Create handlers
        self.screen_handler = logging.StreamHandler()
        self.file_handler = RotatingFileHandler(self.log_file, maxBytes=max_log_size_mb * 1024 * 1024, backupCount=backup_count,
                                                encoding='utf-8')

        self.line_format = '%(asctime)s %(levelname)8s %(message)s'
        self.screen_format = logging.Formatter(self.line_format, datefmt='%Y-%m-%d\t %H:%M:%S')
        self.file_format = logging.Formatter(self.line_format, datefmt='%Y-%m-%d\t %H:%M:%S')

        self.screen_handler.setFormatter(self.screen_format)
        self.file_handler.setFormatter(self.file_format)

        # Add handlers to the logger
        self.logger.addHandler(self.screen_handler)
        self.logger.addHandler(self.file_handler)

        # Set level
        self.level = eval(f"logging.{info_level}")
        self.logger.setLevel(self.level)

    def debug(self, msg):
        """DEBUG Method"""
        self.logger.debug(msg)

    def info(self, msg):
        """INFO Method"""
        self.logger.info(msg)

    def warning(self, msg):
        """WARNING Method"""
        self.logger.warning(msg)

    def error(self, msg):
        """ERROR Method"""
        self.logger.error(msg, exc_info=True)

    def critical(self, msg):
        """CRITICAL Method"""
        self.logger.critical(msg, exc_info=True)

    def read_last_lines(self, num_lines):
        with open(self.log_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            return lines[-num_lines:]


def describe_structure(data):
    """
    Describir la estructura y los tipos de datos de una entrada hasta el segundo nivel,
    formateando la salida en una sola línea.

    Args:
        data: Los datos a describir.

    Returns:
        Una descripción de la estructura de datos hasta el segundo nivel, en una sola línea.
    """

    if isinstance(data, dict):
        types = [f"{key}: {type(value).__name__}" for key, value in data.items()]
        description = "dict: " + ", ".join(types)
    elif isinstance(data, list):
        if all(isinstance(item, type(data[0])) for item in data) and data:  # Verifica que la lista no esté vacía
            if isinstance(data[0], (dict, list)):
                # Si el primer elemento es un dict o list, describe su estructura
                inner_descriptions = []
                for value in data[0]:
                    if isinstance(value, (dict, list)):
                        inner_descriptions.append("[...]")
                    else:
                        inner_descriptions.append(type(value).__name__)
                description = f"list[{type(data[0]).__name__}]: " + ", ".join(inner_descriptions)
            else:
                description = f"list[{type(data[0]).__name__}]: " + type(data[0]).__name__
        else:
            unique_types = {type(item).__name__ for item in data}
            description = "list: " + ", ".join(unique_types)
    else:
        description = type(data).__name__

    return description


class APICallLogger:
    """
    Logs details about API calls to a CSV file.
    """

    def __init__(self,
                 log_file: str,
                 folder: str = 'api_logs'):

        self.log_file = path.join(folder, log_file)
        self.folder = folder
        self.fieldnames = ['base_url', 'endpoint', 'url', 'method', 'status_code', 'params', 'request_headers',
                           'response_headers', 'body', 'json_response', 'error']

        if not path.exists(folder):
            makedirs(folder)

        self.file = open(self.log_file, 'a', newline='', encoding='utf-8')
        self.is_file_empty = not path.exists(self.log_file) or path.getsize(self.log_file) == 0
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        if self.is_file_empty:
            self.writer.writeheader()

    def log(self,
            method: str,
            base_url: str,
            endpoint: str,
            url: str,
            status_code: int = None,
            params: dict = None,
            request_headers: Union[dict, list, CaseInsensitiveDict] = None,
            response_headers: Union[dict, list, CaseInsensitiveDict] = None,
            body: str = None,
            json_response: dict = None,
            error: str = None):

        log_entry = {
            'method': method,
            'url': url,
            'base_url': base_url,
            'endpoint': endpoint,
            'status_code': status_code,
            'params': self.get_keys(params),
            'request_headers': self.get_keys(request_headers),
            'response_headers': self.get_keys(response_headers),
            'body': len(body) if body else 0,
            'json_response': self.get_keys(json_response),
            'error': error if error else ''
        }

        self.writer.writerow(log_entry)
        self.file.flush()  # Flush the buffer to write the entry immediately

    @staticmethod
    def get_keys(input_data: Union[dict, list]) -> Union[list, str]:
        """
        Identifica si el input es un diccionario o una lista de diccionarios y devuelve las keys.

        Args:
            input_data (dict | list): Un diccionario o una lista de diccionarios.

        Returns:
            list: Las keys del diccionario o diccionarios.
        """
        try:
            return list(input_data.keys())
        except AttributeError:
            if isinstance(input_data, dict):
                return list(input_data.keys())
            elif isinstance(input_data, list) and all(isinstance(item, dict) for item in input_data):
                return list(input_data[0].keys()) if input_data else []
            else:
                # raise ValueError("El input debe ser un diccionario o una lista de diccionarios.")
                return describe_structure(input_data)

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type: Exception, exc_val: Exception, exc_tb: Exception):
        self.close()


if __name__ == "__main__":
    """
    Example usage of the LogManager class.
    """

    # URL y endpoint para el API de Binance
    BINANCE_API_URL = "https://api.binance.com"
    KLINES_ENDPOINT = "/api/v3/klines"

    # Parámetros para la consulta de Klines
    params = {
        'symbol': 'BTCUSDT',
        'interval': '1m',  # 1 minuto de intervalo
        'limit': 5  # Número limitado de klines para el test
    }

    def test_binance_api_klines():
        call_logger = APICallLogger(log_file='binance_api_calls.csv')

        with call_logger as logger:
            try:
                # Realiza la llamada a la API de Binance
                response = requests.get(BINANCE_API_URL + KLINES_ENDPOINT, params=params)

                # Registra los detalles de la llamada en el CSV
                logger.log(
                    method='GET',
                    url=response.url,
                    base_url=BINANCE_API_URL,
                    endpoint=KLINES_ENDPOINT,
                    status_code=response.status_code,
                    params=params,
                    request_headers=response.request.headers,
                    response_headers=response.request.headers,
                    body=None,
                    json_response=response.json(),
                    error=response.text if response.status_code != 200 else ''
                )

                # Imprime los Klines obtenidos para verificar (opcional)
                print(response.json())

            except Exception as e:
                print(f"An error occurred: {e}")


    # Ejecutar el test
    test_binance_api_klines()
