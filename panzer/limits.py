from time import time, sleep
from typing import Dict
from urllib.parse import urljoin
import pandas as pd
import requests

from panzer.binance_api_map import *
from panzer.logs import LogManager
from panzer.signatures import BinanceRequestSigner


class BinanceAPILimitsManager:
    def __init__(self, info_level='INFO'):

        self.logger = LogManager(filename="limits.log", info_level=info_level)
        self.limits_response = self.get_exchange_limits()
        self.time_server_offset = self.get_server_time() - int(time() * 1000)

        self.rate_limits = self.parse_weight_limits(self.limits_response)

        self.symbol_limits = pd.DataFrame(self.limits_response['symbols'])

        self.header_limits = {'X-SAPI-USED-IP-WEIGHT-1M': self.rate_limits['REQUEST_1M'],
                              'X-SAPI-USED-UID-WEIGHT-1M': self.rate_limits['REQUEST_1M'],
                              'x-mbx-used-weight': self.rate_limits['REQUEST_5M'],
                              'x-mbx-used-weight-1m': self.rate_limits['REQUEST_1M'],
                              'x-mbx-order-count-10s': self.rate_limits['ORDERS_10S'],
                              'x-mbx-order-count-1d': self.rate_limits['ORDERS_1D']}

        self.api_limits_weight_decrease_per_seconds = {'X-SAPI-USED-IP-WEIGHT-1M': self.rate_limits['REQUEST_1M'] // 60,
                                                       'X-SAPI-USED-UID-WEIGHT-1M': self.rate_limits['REQUEST_1M'] // 60,
                                                       'x-mbx-used-weight-1m': self.rate_limits['REQUEST_1M'] // 60,
                                                       'x-mbx-used-weight': self.rate_limits['REQUEST_5M'] // (60 * 5),
                                                       'x-mbx-order-count-10s': self.rate_limits['ORDERS_10S'] // 10,
                                                       'x-mbx-order-count-1d': self.rate_limits['ORDERS_1D'] // (24 * 60 * 60)}

        self.detected_endpoint_headers = {}
        self.endpoint_enabled_timestamp = {}

    def get_exchange_limits(self) -> dict:
        """
        Consulta la información de los límites de la API de Binance haciendo una solicitud al endpoint /api/v3/exchangeInfo.
        Esta información ayuda a prevenir exceder los límites de la API, evitando así errores 429 (Too Many Requests) y posibles baneos IP.

        Tipos de Límites:
        - REQUEST_WEIGHT: Aplicado al peso total de las solicitudes en un intervalo de tiempo. Cada solicitud tiene un peso asignado,
          reflejando su coste de procesamiento. Afecta a la mayoría de las solicitudes de la API.
        - ORDERS: Específico para solicitudes de creación o cancelación de órdenes, limitando la cantidad permitida en un intervalo de
        tiempo.
        - RAW_REQUESTS: Refiere al número total de solicitudes HTTP, independiente de su peso o tipo. Limita el número total de solicitudes.

        Formato de los Datos de Respuesta:
        - rateLimitType: Tipo de límite (REQUEST_WEIGHT, ORDERS, RAW_REQUESTS).
        - interval: Unidad de tiempo para el límite (SEGUNDO, MINUTO, HORA, DÍA).
        - intervalNum: Cantidad de la unidad de tiempo.
        - limit: Máximo permitido en el intervalo especificado.

        Ejemplo de Datos de Respuesta de la key 'rateLimits' en la respuesta de la API:

        .. code-block:: python

            # rateLimits key
            [
                {'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
                {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
                {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
                {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}
            ]

        Estos datos permiten ajustar dinámicamente las solicitudes a la API para cumplir con los límites establecidos y mantener una
        integración eficiente y respetuosa con la API de Binance.
        """
        response = requests.get(url=BINANCE_LIMITS_URL, params=None, headers=None)
        return response.json()

    def parse_weight_limits(self, response: Dict) -> Dict[str, int]:
        """
        Parsea la respuesta de la API para obtener los límites de peso.

        Ejemplo:

        .. code-block:: python

             {'REQUEST_1M': 6000,
              'ORDERS_10S': 100,
              'ORDERS_1D': 200000,
              'REQUEST_5M': 61000}

        """
        try:
            limits = response['rateLimits']
        except KeyError:
            self.logger.error(f"Error: No se encontraron límites en la respuesta: {response}, aplicando límites por defecto.")
            limits = [{'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
                      {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
                      {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
                      {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}]

        limits_dict = {}
        for limit in limits:
            if 'REQUEST' in limit['rateLimitType']:
                interval = str(limit['intervalNum'])
                interval += limit['interval'][0]
                limits_dict[f'REQUEST_{interval}'] = limit['limit']
            elif 'ORDERS' in limit['rateLimitType']:
                interval = str(limit['intervalNum'])
                interval += limit['interval'][0]
                limits_dict[f'ORDERS_{interval}'] = limit['limit']
            else:
                msg = f"BinPan error: Unknown limit from API: {limit}"
                raise Exception(msg)
        return limits_dict

    def register_header_for_endpoint(self, endpoint: str, header: str):
        """
        Adds API headers response info for weight control. It is an inventory of headers for each endpoint.

        :param str endpoint: Endpoint path.
        :param str header: Header in response.
        :return: None
        """
        if header not in self.detected_endpoint_headers.setdefault(endpoint, []):
            self.detected_endpoint_headers[endpoint].append(header)
            self.logger.info(f"Control de peso de cabeceras de endpoint actualizado: {endpoint} -> {header}")

    @staticmethod
    def get_server_time(base_url='https://api.binance.com', endpoint='/api/v3/time') -> int:
        """
        Get time from server.

        :return int: A linux timestamp in milliseconds.
        """
        url = urljoin(base_url, endpoint)
        response = requests.get(url=url, params=None, headers=None)
        return int(response.json()['serverTime'])

    def parse_response_headers(self, response: requests.Response) -> Dict[str, int]:
        """
        Parsea las cabeceras de la respuesta de la API para obtener los pesos de las solicitudes.

        :param response: Respuesta de la API.
        :return: Un diccionario con los pesos de las solicitudes.
        """
        weight_headers = {}
        for k, v in response.headers.items():
            # if 'WEIGHT' in k.upper() or 'COUNT' in k.upper() or k.startswith('x-') or k.startswith('X-'):
            if 'WEIGHT' in k.upper() or 'COUNT' in k.upper():
                try:
                    weight_headers[k] = int(v)
                except ValueError:
                    self.logger.debug(f"Error al convertir el valor de la cabecera {k}={v} a entero.")
                    continue
            # weight_headers = {k: int(v) for k, v in response.headers.items() if 'WEIGHT' in k.upper() or 'COUNT' in k.upper()}
            self.logger.debug(f"Header from API response: {k}={v}")
        return weight_headers

    def update(self, response: requests.Response, endpoint: str, register: bool = True):
        """
        Update header weights. Headers are across endpoints.
        """
        headers_weight = self.parse_response_headers(response)

        for header in headers_weight:
            if register:
                self.register_header_for_endpoint(endpoint=endpoint, header=header)
            self.update_header_enabled_timestamp(header=header, current_weight=headers_weight.get(header, 0))

    def update_header_enabled_timestamp(self, header: str, current_weight: int):
        """
        Update the header timestamp enabled for the endpoint.

        :param str header: Header name.
        :param int current_weight: Current weight of the header.
        """
        try:
            limit = self.header_limits.get(header, 0)
        except KeyError:
            raise KeyError(f"Header {header} not found in header limits: {self.header_limits}")

        if current_weight > limit:
            self.logger.debug(f"Header {header} current weight {current_weight} is over the limit {limit}.")
            excess_weight = current_weight - limit  # > 0
            excess_seconds = excess_weight // self.api_limits_weight_decrease_per_seconds[header]
            enabled_timestamp = int(time() * 1000) + self.time_server_offset + int(excess_seconds * 1000)
            self.endpoint_enabled_timestamp[header] = enabled_timestamp

    def check_and_wait_timestamp(self, endpoint: str):
        """
        Check if the timestamp is enabled for the endpoint.

        :param str endpoint: Endpoint requested.
        :return: True if the timestamp is enabled, False otherwise.
        """
        enabled_timestamp = self.endpoint_enabled_timestamp.get(endpoint, 0)
        current_time = int(time() * 1000) + self.time_server_offset
        if current_time > enabled_timestamp:
            self.endpoint_enabled_timestamp[endpoint] = current_time
            return
        else:
            self.logger.warning(f"Timestamp {current_time} is in the past for endpoint {endpoint}.")
            # seconds until timestamp is enabled
            seconds = (enabled_timestamp - current_time) / 1000
            self.logger.warning(f"Waiting {seconds} seconds until timestamp is enabled.")

            # We take the opportunity to update the endpoint timestamp
            self.time_server_offset = self.get_server_time() - int(time() * 1000)
            sleep(seconds)

            self.endpoint_enabled_timestamp[endpoint] = int(time() * 1000) + self.time_server_offset


if __name__ == "__main__":

    def fetch(symbol: str = 'BTCUSDT',
              fromId=0,
              limits: BinanceAPILimitsManager = None):

        base_url = 'https://api.binance.com'
        # endpoint = '/api/v3/allOrders'
        endpoint = '/api/v3/aggTrades'
        url = urljoin(base_url, endpoint)

        params = {'symbol': symbol, 'fromId': fromId, "limit": 1000}

        signer = BinanceRequestSigner()
        headers = signer.add_api_key_to_headers(headers={})
        # params = signer.sign_params(params=list(params.items()), add_timestamp=True)

        limits.check_and_wait_timestamp(endpoint=endpoint)
        response = requests.get(url, params=params, headers=headers)
        limits.update(response=response, endpoint=endpoint, register=True)

        print("\nRespuesta:")
        print("Cabeceras:")
        for k, value in response.headers.items():
            if 'WEIGHT' in k.upper() or 'COUNT' in k.upper():
                print(k, value)
        # print("Cuerpo de respuesta:", response.json())
        return response.json()


    limits = BinanceAPILimitsManager(info_level="INFO")
    print(limits.header_limits)

    fromId = 0

    for i in range(100):
        resp = fetch(limits=limits, fromId=fromId)
        fromId = resp[-1]['a']
        sleep(1)
