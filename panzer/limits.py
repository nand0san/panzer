from time import time, sleep
from typing import Dict
from urllib.parse import urljoin
import pandas as pd
import requests

from panzer.binance_api_map import *
from panzer.logs import LogManager
from panzer.signatures import RequestSigner


class BinanceAPILimitsManager:
    """
    Manages the API limits for each type of header in the response from the Binance API. Assumes that headers are shared across all API endpoints
    returning that type of header. For instance, the 'X-SAPI-USED-IP-WEIGHT-1M' header is shared by all endpoints that return it. This class helps
    in preventing exceeding the API's rate limits, thus avoiding HTTP 429 (Too Many Requests) errors and possible IP bans by dynamically adjusting
    request rates according to the limits.
    """

    def __init__(self, info_level='INFO'):
        """
        Initializes the Binance API limits manager with logging, current limits, and server time offset.

        :param info_level: The logging level for the LogManager. Defaults to 'INFO'.
        """
        self.logger = LogManager(filename="limits.log", info_level=info_level)
        self.limits_response = self.get_exchange_limits()
        self.time_server_offset = self.get_server_time() - int(time() * 1000)
        self.rate_limits_ms = self.parse_weight_limits(self.limits_response)
        self.symbol_limits = pd.DataFrame(self.limits_response['symbols'])
        self.endpoint_headers = {}
        self.header_limits = {'X-SAPI-USED-IP-WEIGHT-1M': self.rate_limits_ms['REQUEST_1M'],
                              'X-SAPI-USED-UID-WEIGHT-1M': self.rate_limits_ms['REQUEST_1M'],
                              'x-mbx-used-weight': self.rate_limits_ms['REQUEST_5M'],
                              'x-mbx-used-weight-1m': self.rate_limits_ms['REQUEST_1M'],
                              'x-mbx-order-count-10s': self.rate_limits_ms['ORDERS_10S'],
                              'x-mbx-order-count-1d': self.rate_limits_ms['ORDERS_1D']}
        self.current_header_weights = {}
        self.header_renewal_timestamp = {}

    @staticmethod
    def get_exchange_limits() -> dict:
        """
        Fetches the API limits information from Binance by making a request to the /api/v3/exchangeInfo endpoint.
        This information is crucial for preventing API rate limit violations.

        Limit Types:
        - REQUEST_WEIGHT: Applied to the total request weight in a time frame. Each request has an assigned weight,
          reflecting its processing cost. It affects most API requests.
        - ORDERS: Specific to order creation or cancellation requests, limiting the number allowed in a timeframe.
        - RAW_REQUESTS: Refers to the total number of HTTP requests, regardless of their weight or type. It limits the total request count.

        Response Data Format:
        - rateLimitType: The limit type (REQUEST_WEIGHT, ORDERS, RAW_REQUESTS).
        - interval: Time unit for the limit (SECOND, MINUTE, HOUR, DAY).
        - intervalNum: Number of time units.
        - limit: Maximum allowed in the specified interval.

        .. code-block:: python

            # rateLimits key
            [
                {'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
                {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
                {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
                {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}
            ]

        """
        response = requests.get(url=BINANCE_LIMITS_URL, params=None, headers=None)
        return response.json()

    def parse_weight_limits(self, response: Dict) -> Dict[str, int]:
        """
        Parses the API response to obtain weight limits for rate limiting purposes.

        Example:

            {'REQUEST_1M': 6000,
             'ORDERS_10S': 100,
             'ORDERS_1D': 200000,
             'REQUEST_5M': 61000}
        """
        try:
            limits = response['rateLimits']
        except KeyError:
            self.logger.error(f"Error: No limits found in the response: {response}, applying default limits.")
            # Default limits if not found in the response
            limits = [{'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
                      {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
                      {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
                      {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}]

        limits_dict = {}
        for limit in limits:
            if 'REQUEST' in limit['rateLimitType']:
                interval = f"{limit['intervalNum']}{limit['interval'][0]}"
                limits_dict[f'REQUEST_{interval}'] = limit['limit']
            elif 'ORDERS' in limit['rateLimitType']:
                interval = f"{limit['intervalNum']}{limit['interval'][0]}"
                limits_dict[f'ORDERS_{interval}'] = limit['limit']
            else:
                msg = f"BinPan error: Unknown limit from API: {limit}"
                raise Exception(msg)
        return limits_dict

    def register_header_for_endpoint(self, endpoint: str, header: str):
        """
        Registers API header information for weight control, maintaining an inventory of headers for each endpoint.

        :param endpoint: The API endpoint path.
        :param header: The response header to be registered.
        """
        if header not in self.endpoint_headers.setdefault(endpoint, []):
            self.endpoint_headers[endpoint].append(header)
            self.logger.info(f"Endpoint header weight control updated: {endpoint} -> {header}")

    @staticmethod
    def get_server_time(base_url='https://api.binance.com', endpoint='/api/v3/time') -> int:
        """
        Fetches the current server time from the Binance API.

        :return: The server time as a Unix timestamp in milliseconds.
        """
        url = urljoin(base_url, endpoint)
        response = requests.get(url=url, params=None, headers=None)
        return int(response.json()['serverTime'])

    def parse_response_headers(self, response: requests.Response) -> Dict[str, int]:
        """
        Parses API response headers to obtain the weights of the requests.

        :param response: The API response.
        :return: A dictionary containing the weights of the requests.
        """
        weight_headers = {}
        for k, v in response.headers.items():
            if 'WEIGHT' in k.upper() or 'COUNT' in k.upper():
                try:
                    weight_headers[k] = int(v)
                except ValueError:
                    self.logger.debug(f"Failed to convert header value to integer: {k}={v}.")
                    continue
            self.logger.debug(f"Header from API response: {k}={v}")
        return weight_headers

    def update(self, response: requests.Response, endpoint: str):
        """
        Updates header weights based on the API response. This method is used for across-endpoint header weight control.
        """
        headers_weight = self.parse_response_headers(response)

        for header, weight in headers_weight.items():
            self.register_header_for_endpoint(endpoint=endpoint, header=header)
            self.current_header_weights[header] = weight

    def get_limit_refresh_timestamp_ms(self, header: str) -> int:
        """
        Calculates the timestamp in milliseconds when a header's limit will be refreshed.

        :param header: The header name.
        :return: The refresh timestamp in milliseconds.
        """
        limit_ms = self.rate_limits_ms[header]
        now = int(time() * 1000) + self.time_server_offset
        cycle_ms = now % limit_ms
        remaining_ms = limit_ms - cycle_ms
        return now + remaining_ms

    def check_and_wait_timestamp(self, endpoint: str):
        """
        Checks and waits for a timestamp to become available for a given endpoint.

        :param endpoint: The requested API endpoint.
        """
        for header in self.endpoint_headers.get(endpoint, []):
            header_current_weight = self.current_header_weights.get(header, 0)
            header_weight_limit = self.header_limits[header]

            if header_current_weight < header_weight_limit:
                continue
            else:
                self.logger.warning(f"Header {header} reached its limit of {header_weight_limit} with {header_current_weight}.")
                refresh_timestamp = self.get_limit_refresh_timestamp_ms(header=header)
                # Update the endpoint timestamp
                self.time_server_offset = self.get_server_time() - int(time() * 1000)
                now = int(time() * 1000) + self.time_server_offset
                seconds_wait = (refresh_timestamp - now) / 1000
                self.logger.warning(f"Waiting {seconds_wait} seconds until timestamp is available.")
                sleep(max(seconds_wait, 0))
                break  # Prevent multiple waits for endpoints with more than one header


if __name__ == "__main__":

    def fetch(symbol: str = 'BTCUSDT',
              # fromId=0,
              limits: BinanceAPILimitsManager = None):

        base_url = 'https://api.binance.com'
        endpoint = '/api/v3/allOrders'
        # endpoint = '/api/v3/aggTrades'
        url = urljoin(base_url, endpoint)

        # params = {'symbol': symbol, 'fromId': fromId, "limit": 1000}
        params = {'symbol': symbol}

        signer = RequestSigner()
        headers = signer.add_api_key_to_headers(headers={})
        params = signer.sign_params(params=list(params.items()), add_timestamp=True)

        limits.check_and_wait_timestamp(endpoint=endpoint)
        response = requests.get(url, params=params, headers=headers)
        limits.update(response=response, endpoint=endpoint)

        print("\nRespuesta:")
        print("Cabeceras:")
        for k, value in response.headers.items():
            if 'WEIGHT' in k.upper() or 'COUNT' in k.upper():
                print(k, value)
        # print("Cuerpo de respuesta:", response.json())
        # status
        print("Status:", response.status_code, response.reason)
        return response.json()


    limits = BinanceAPILimitsManager(info_level="INFO")
    print(limits.rate_limits_ms)

    fromId = 0

    for i in range(100):
        resp = fetch(limits=limits,)
        # fromId=fromId)
        # fromId = resp[-1]['a']
        # sleep(1)
