from typing import Dict, Union
from time import time

from panzer.logs import LogManager
from panzer.time import second, ten_seconds, minute, hour, day, update_server_time_offset


# class BinanceLimitsFetcher:
#
#     def __init__(self, info_level="INFO"):
#         self.BASE_URL = BASE_URL
#         self.EXCHANGE_INFO_ENDPOINT = EXCHANGE_INFO_ENDPOINT
#         self.MARGIN_ACCOUNT_ENDPOINT = MARGIN_ACCOUNT_ENDPOINT
#         self.FUTURES_BASE_URL = FUTURES_BASE_URL
#         self.FUTURES_EXCHANGE_INFO_ENDPOINT = FUTURES_EXCHANGE_INFO_ENDPOINT
#
#         self.url = urljoin(self.BASE_URL, self.EXCHANGE_INFO_ENDPOINT)
#
#         self.spot_url = urljoin(self.BASE_URL, self.EXCHANGE_INFO_ENDPOINT)
#         self.margin_url = urljoin(self.BASE_URL, self.MARGIN_ACCOUNT_ENDPOINT)
#         self.futures_url = urljoin(self.FUTURES_BASE_URL, self.FUTURES_EXCHANGE_INFO_ENDPOINT)
#
#         self.logger = LogManager(filename='logs/limits.log', info_level=info_level)
#         self.signer = RequestSigner(info_level=info_level)
#
#     @staticmethod
#     def _get_limits(url: str) -> Dict[str, Dict[str, str]]:
#         """
#         Fetches and returns the limits from a given URL endpoint.
#
#         :param url: The API endpoint to fetch limits from.
#         :return: A dictionary of limits.
#         """
#         response = requests.get(url)
#         if response.status_code != 200:
#             raise Exception(f"Error fetching limits from {url}: {response.status_code} - {response.text}")
#
#         return response.json()
#
#     @staticmethod
#     def parse_limits(data: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
#         """
#         Parses the API response to extract rate limits.
#
#         :param data: The JSON response containing limits information.
#         :return: A dictionary with the parsed limits.
#         """
#         limits = data.get('rateLimits', [])
#         parsed_limits = {}
#
#         for limit in limits:
#             limit_type = limit.get('rateLimitType')
#             interval = limit.get('interval')
#             interval_num = limit.get('intervalNum')
#             max_limit = limit.get('limit')
#
#             key = f"{limit_type}_{interval_num}{interval.lower()}"
#             parsed_limits[key] = {
#                 'type': limit_type,
#                 'cycle': f"{interval_num} {interval.lower()}",
#                 'max_requests': max_limit
#             }
#
#         return parsed_limits
#
#     def get_spot_limits(self):
#         """
#         Fetches and parses the limits for SPOT trading from Binance API.
#
#         :return: A dictionary with the SPOT trading limits.
#         """
#         data = self._get_limits(self.spot_url)
#         return self.parse_limits(data)
#
#     def get_margin_limits(self):
#         """
#         Fetches and parses the limits for MARGIN trading from Binance API.
#         Note: Margin trading doesn't provide rateLimits directly, so limits may need to be derived from response headers.
#
#         :return: A dictionary with margin-related limits.
#         """
#         data = self._get_limits(self.margin_url)
#
#         # For Margin, the response might not directly have 'rateLimits', so we can parse necessary data.
#         # Here we assume we might parse headers or other specific limits relevant to margin trading.
#         margin_limits = {
#             "marginAccount": {
#                 "borrowLimit": data.get("totalAssetOfBtc"),  # Example limit
#                 "totalMarginBalance": data.get("totalNetAssetOfBtc")
#             }
#         }
#         return margin_limits
#
#     def get_futures_limits(self):
#         """
#         Fetches and parses the limits for FUTURES trading from Binance API.
#
#         :return: A dictionary with the FUTURES trading limits.
#         """
#         data = self._get_limits(self.futures_url)
#         return self.parse_limits(data)
#
#     def get_all_limits(self):
#         """
#         Fetches and aggregates limits from SPOT, MARGIN, and FUTURES into a single dictionary.
#
#         :return: A dictionary with all limits.
#         """
#         limits = {
#             'spot': self.get_spot_limits(),
#             'margin': self.get_margin_limits(),
#             'futures': self.get_futures_limits()
#         }
#         return limits
#
#     def print_limits(self):
#         """
#         Prints the limits obtained for SPOT, MARGIN, and FUTURES in a formatted manner.
#         """
#         all_limits = self.get_all_limits()
#
#         for api_type, limits in all_limits.items():
#             print(f"\n--- Límites para {api_type.upper()} ---")
#             if isinstance(limits, dict):
#                 for key, value in limits.items():
#                     if isinstance(value, dict):
#                         print(f"{key}:")
#                         for sub_key, sub_value in value.items():
#                             print(f"  {sub_key}: {sub_value}")
#                     else:
#                         print(f"{key}: {value}")
#             else:
#                 print(limits)
#
#     def __repr__(self):
#         return self.print_limits()
#
#
# class BinanceAPILimitsManager:
#     """
#     Manages the API limits for each type of header in the response from the Binance API. Assumes that headers are shared across all API endpoints
#     returning that type of header. For instance, the 'X-SAPI-USED-IP-WEIGHT-1M' header is shared by all endpoints that return it. This class helps
#     in preventing exceeding the API's rate limits, thus avoiding HTTP 429 (Too Many Requests) errors and possible IP bans by dynamically adjusting
#     request rates according to the limits.
#     """
#
#     def __init__(self, info_level='INFO'):
#         """
#         Initializes the Binance API limits manager with logging, current limits, and server time offset.
#
#         :param info_level: The logging level for the LogManager. Defaults to 'INFO'.
#         """
#         self.logger = LogManager(filename="limits.log", info_level=info_level)
#         self.limits_response = self.get_exchange_limits()
#         self.time_server_offset = self.get_server_time() - int(time() * 1000)
#         self.rate_limits_ms = self.parse_weight_limits(self.limits_response)
#         self.symbol_limits = pd.DataFrame(self.limits_response['symbols'])
#         self.endpoint_headers = {}
#         self.header_limits = {'X-SAPI-USED-IP-WEIGHT-1M': self.rate_limits_ms['REQUEST_1M'],
#                               'X-SAPI-USED-UID-WEIGHT-1M': self.rate_limits_ms['REQUEST_1M'],
#                               'x-mbx-used-weight': self.rate_limits_ms['REQUEST_5M'],
#                               'x-mbx-used-weight-1m': self.rate_limits_ms['REQUEST_1M'],
#                               'x-mbx-order-count-10s': self.rate_limits_ms['ORDERS_10S'],
#                               'x-mbx-order-count-1d': self.rate_limits_ms['ORDERS_1D']}
#         self.current_header_weights = {}
#         self.header_renewal_timestamp = {}
#
#     @staticmethod
#     def get_exchange_limits() -> dict:
#         """
#         Fetches the API limits information from Binance by making a request to the /api/v3/exchangeInfo endpoint.
#         This information is crucial for preventing API rate limit violations.
#
#         Limit Types:
#         - REQUEST_WEIGHT: Applied to the total request weight in a time frame. Each request has an assigned weight,
#           reflecting its processing cost. It affects most API requests.
#         - ORDERS: Specific to order creation or cancellation requests, limiting the number allowed in a timeframe.
#         - RAW_REQUESTS: Refers to the total number of HTTP requests, regardless of their weight or type. It limits the total request count.
#
#         Response Data Format:
#         - rateLimitType: The limit type (REQUEST_WEIGHT, ORDERS, RAW_REQUESTS).
#         - interval: Time unit for the limit (SECOND, MINUTE, HOUR, DAY).
#         - intervalNum: Number of time units.
#         - limit: Maximum allowed in the specified interval.
#
#         .. code-block:: python
#
#             # rateLimits key
#             [
#                 {'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
#                 {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
#                 {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
#                 {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}
#             ]
#
#         """
#         response = requests.get(url=EXCHANGE_INFO_ENDPOINT, params=None, headers=None)
#         return response.json()
#
#     def parse_weight_limits(self, response: Dict) -> Dict[str, int]:
#         """
#         Parses the API response to obtain weight limits for rate limiting purposes.
#
#         Example:
#
#             {'REQUEST_1M': 6000,
#              'ORDERS_10S': 100,
#              'ORDERS_1D': 200000,
#              'REQUEST_5M': 61000}
#         """
#         try:
#             limits = response['rateLimits']
#         except KeyError:
#             self.logger.error(f"Error: No limits found in the response: {response}, applying default limits.")
#             # Default limits if not found in the response
#             limits = [{'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000},
#                       {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100},
#                       {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000},
#                       {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}]
#
#         limits_dict = {}
#         for limit in limits:
#             if 'REQUEST' in limit['rateLimitType']:
#                 interval = f"{limit['intervalNum']}{limit['interval'][0]}"
#                 limits_dict[f'REQUEST_{interval}'] = limit['limit']
#             elif 'ORDERS' in limit['rateLimitType']:
#                 interval = f"{limit['intervalNum']}{limit['interval'][0]}"
#                 limits_dict[f'ORDERS_{interval}'] = limit['limit']
#             else:
#                 msg = f"BinPan error: Unknown limit from API: {limit}"
#                 raise Exception(msg)
#         return limits_dict
#
#     def register_header_for_endpoint(self, endpoint: str, header: str):
#         """
#         Registers API header information for weight control, maintaining an inventory of headers for each endpoint.
#
#         :param endpoint: The API endpoint path.
#         :param header: The response header to be registered.
#         """
#         if header not in self.endpoint_headers.setdefault(endpoint, []):
#             self.endpoint_headers[endpoint].append(header)
#             self.logger.info(f"Endpoint header weight control updated: {endpoint} -> {header}")
#
#     @staticmethod
#     def get_server_time(base_url='https://api.binance.com', endpoint='/api/v3/time') -> int:
#         """
#         Fetches the current server time from the Binance API.
#
#         :return: The server time as a Unix timestamp in milliseconds.
#         """
#         url = urljoin(base_url, endpoint)
#         response = requests.get(url=url, params=None, headers=None)
#         return int(response.json()['serverTime'])
#
#     def parse_response_headers(self, response: requests.Response) -> Dict[str, int]:
#         """
#         Parses API response headers to obtain the weights of the requests.
#
#         :param response: The API response.
#         :return: A dictionary containing the weights of the requests.
#         """
#         weight_headers = {}
#         for k, v in response.headers.items():
#             if 'WEIGHT' in k.upper() or 'COUNT' in k.upper():
#                 try:
#                     weight_headers[k] = int(v)
#                 except ValueError:
#                     self.logger.debug(f"Failed to convert header value to integer: {k}={v}.")
#                     continue
#             self.logger.debug(f"Header from API response: {k}={v}")
#         return weight_headers
#
#     def update(self, response: requests.Response, endpoint: str):
#         """
#         Updates header weights based on the API response. This method is used for across-endpoint header weight control.
#         """
#         headers_weight = self.parse_response_headers(response)
#
#         for header, weight in headers_weight.items():
#             self.register_header_for_endpoint(endpoint=endpoint, header=header)
#             self.current_header_weights[header] = weight
#
#     def get_limit_refresh_timestamp_ms(self, header: str) -> int:
#         """
#         Calculates the timestamp in milliseconds when a header's limit will be refreshed.
#
#         :param header: The header name.
#         :return: The refresh timestamp in milliseconds.
#         """
#         limit_ms = self.rate_limits_ms[header]
#         now = int(time() * 1000) + self.time_server_offset
#         cycle_ms = now % limit_ms
#         remaining_ms = limit_ms - cycle_ms
#         return now + remaining_ms
#
#     def check_and_wait_timestamp(self, endpoint: str):
#         """
#         Checks and waits for a timestamp to become available for a given endpoint.
#
#         :param endpoint: The requested API endpoint.
#         """
#         for header in self.endpoint_headers.get(endpoint, []):
#             header_current_weight = self.current_header_weights.get(header, 0)
#             header_weight_limit = self.header_limits[header]
#
#             if header_current_weight < header_weight_limit:
#                 continue
#             else:
#                 self.logger.warning(f"Header {header} reached its limit of {header_weight_limit} with {header_current_weight}.")
#                 refresh_timestamp = self.get_limit_refresh_timestamp_ms(header=header)
#                 # Update the endpoint timestamp
#                 self.time_server_offset = self.get_server_time() - int(time() * 1000)
#                 now = int(time() * 1000) + self.time_server_offset
#                 seconds_wait = (refresh_timestamp - now) / 1000
#                 self.logger.warning(f"Waiting {seconds_wait} seconds until timestamp is available.")
#                 sleep(max(seconds_wait, 0))
#                 break  # Prevent multiple waits for endpoints with more than one header


class BinanceRateLimiter:
    def __init__(self,
                 rate_limit_per_minute: int = 1200,
                 rate_limit_per_second: int = 10,
                 orders_limit_per_ten_seconds: int = 10,
                 weight_limit_per_minute: int = 50000,
                 rate_limit_per_day: int = 65000,
                 info_level: str = "INFO"):
        """
        Initializes the class with specified limits.

        :param rate_limit_per_minute: Maximum number of requests allowed per minute.
        :param rate_limit_per_second: Maximum number of requests allowed per second.
        :param weight_limit_per_minute: Maximum total request weight allowed per minute.
        :param info_level: The log level for the logger.
        """
        self.logger = LogManager(filename='logs/limits.log', info_level=info_level)
        self.server_time_offset = 0

        # Request rate limits
        self.rate_limit_per_day = rate_limit_per_day
        self.rate_limit_per_minute = rate_limit_per_minute  # Max requests per minute
        self.rate_limit_per_second = rate_limit_per_second  # Max requests per second
        self.orders_limit_per_ten_seconds = orders_limit_per_ten_seconds  # 10s order quantity limit

        # Request weight limit
        self.weight_limit_per_minute = weight_limit_per_minute  # Max request weight per minute

        # Track current request counts and weights
        self.minutes_weights = {}

        self.seconds_counts = {}
        self.ten_seconds_orders_counts = {}
        self.minutes_counts = {}
        self.days_counts = {}

        # clean counters and offset updates
        self.clean_period_minutes = 5  # minutes
        self.minute_for_clean = minute(time_milliseconds=int(time() * 1000)) + self.clean_period_minutes
        self.hour_for_clean = hour(time_milliseconds=int(time() * 1000))
        self._update_server_time_offset()

    def _update_server_time_offset(self):
        """
        Updates the server time offset by fetching the current server time from the Binance API.

        :return: The updated server time offset in milliseconds.
        """
        if self.can_make_request(weight=1, is_order=False):
            if hasattr(self, 'server_time_offset'):
                self.server_time_offset = update_server_time_offset(self.server_time_offset)
            else:
                self.server_time_offset = update_server_time_offset()
            # update counts because of update of server time offset
            return self.server_time_offset
        else:
            self.logger.warning(f"Bypassed update server-local time offset. Rate limiter overload: \n{self.get()}")

    def _get_current_second(self):
        """
        Returns the current second using server time or local time,
        adjusted with the server time offset.

        :return: The current second (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return second(corrected_time)

    def _get_current_ten_seconds(self):
        """
        Returns the current ten seconds using server time or local time,
        adjusted with the server time offset.

        :return: The current ten seconds (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return ten_seconds(corrected_time)

    def _get_current_minute(self):
        """
        Returns the current minute using server time or local time,
        adjusted with the server time offset.

        :return: The current minute (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return minute(corrected_time)

    def _get_current_hour(self):
        """
        Returns the current hour using server time or local time,
        adjusted with the server time offset.

        :return: The current hour (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return hour(corrected_time)

    def _get_current_day(self):
        """
        Returns the current day using server time or local time,
        adjusted with the server time offset.

        :return: The current day (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return day(corrected_time)

    def _clean_counters(self):
        """Keep last 3 counters keys."""
        # Remove old entries
        self.minutes_weights = {k: self.minutes_weights[k] for k in sorted(self.minutes_weights.keys()[:-3])}
        self.seconds_counts = {k: self.seconds_counts[k] for k in sorted(self.seconds_counts.keys()[:-3])}
        self.ten_seconds_orders_counts = {k: self.ten_seconds_orders_counts[k] for k in sorted(self.ten_seconds_orders_counts.keys()[:-3])}
        self.minutes_counts = {k: self.minutes_counts[k] for k in sorted(self.minutes_counts.keys()[:-3])}
        self.days_counts = {k: self.days_counts[k] for k in sorted(self.days_counts.keys()[:-3])}

    def get(self):
        """Get current counter values."""
        return {
            "seconds_counts": self.seconds_counts,
            "ten_seconds_orders_counts": self.ten_seconds_orders_counts,
            "minutes_counts": self.minutes_counts,
            "days_counts": self.days_counts,
            "minutes_weights": self.minutes_weights
        }

    def can_make_request(self, weight: int, is_order: bool) -> bool:
        """
        Checks whether a request can be made without exceeding the rate or weight limits.

        :param weight: The weight of the current request.
        :param is_order: Whether the request is for an order. This adds to the ten seconds limit.
        :return: True if the request can be made, False otherwise.
        """
        current_second = self._get_current_second()
        current_ten_seconds = self._get_current_ten_seconds()
        current_minute = self._get_current_minute()
        current_hour = self._get_current_hour()
        current_day = self._get_current_day()

        current_minute_weight = self.minutes_weights.get(current_minute, 0)
        current_second_count = self.seconds_counts.get(current_second, 0)
        current_ten_seconds_orders_counts = self.ten_seconds_orders_counts.get(current_ten_seconds, 0)
        current_minute_count = self.minutes_counts.get(current_minute, 0)
        current_day_count = self.days_counts.get(current_day, 0)

        # Reset counters if minute or second changes
        if current_second_count + 1 > self.rate_limit_per_second:
            return False
        else:
            self.seconds_counts.update({current_second: current_second_count + 1})

        if is_order and (current_ten_seconds_orders_counts + 1) > self.orders_limit_per_ten_seconds:
            return False
        elif is_order:
            self.ten_seconds_orders_counts.update({current_ten_seconds: current_ten_seconds_orders_counts + 1})

        if current_minute_count + 1 > self.rate_limit_per_minute:
            return False
        else:
            self.minutes_counts.update({current_minute: current_minute_count + 1})

        if current_day_count + 1 > self.rate_limit_per_day:
            return False
        else:
            self.days_counts.update({current_day: current_day_count + 1})

        # weight limit per minute
        if current_minute_weight + weight > self.weight_limit_per_minute:
            return False
        else:
            self.minutes_weights.update({current_minute: current_minute_weight + weight})

        # cleaning and update offsets
        if current_minute > self.minute_for_clean or current_hour > self.hour_for_clean:
            self.minute_for_clean = current_minute + self.clean_period_minutes
            self.hour_for_clean = current_hour
            self._clean_counters()
            self._update_server_time_offset()
        return True

    def wrong_registered_value(self, header: str, normalized_headers: dict, registered_weight: int) -> Union[int, None]:
        """
        Compares the weight of a given header in the response headers with the registered weight.

        :param header: The header to compare.
        :param normalized_headers: The normalized response headers from a Binance API call.
        :param registered_weight: The registered weight for the header.
        :return: The delta deviation between the header value and the registered weight if there's a discrepancy. 0 if no discrepancy.
        """
        if not header in normalized_headers:
            # self.logger.debug(f"Header {header} not found in the response headers: {set(normalized_headers)}")
            return None
        header_value = int(normalized_headers.get(header, 0))
        if header_value != registered_weight:
            delta = header_value - registered_weight
            self.logger.warning(f"Rate limit {header} not synced with the server. Expected: {registered_weight}, "
                                f"Header: {header_value} Delta deviation: {delta}")
            return delta

    def verify_unknown_headers(self, normalized_headers: dict) -> None:
        """
        Verifies that not unknown headers are present in the response headers.

        :param normalized_headers: The normalized response headers from a Binance API call.
        """
        expected_headers = {'x-mbx-uuid', 'x-mbx-used-weight', 'x-mbx-used-weight-1m', 'x-mbx-order-count-10s', 'x-mbx-order-count-1d'}
        unexpected_headers = set(normalized_headers) - expected_headers
        if unexpected_headers:
            self.logger.error(f"Unexpected X-MBX headers: {unexpected_headers}")
            raise ValueError(f"Unexpected X-MBX headers: {unexpected_headers}")

    def update_from_headers(self, headers: dict) -> None:
        """
        Updates rate limiter's internal counters based on the response headers from the Binance API.

        :param headers: The response headers from a Binance API call.
        """
        current_ten_seconds = self._get_current_ten_seconds()
        current_minute = self._get_current_minute()
        current_day = self._get_current_day()

        # Normalize headers to lowercase for uniform access
        normalized_headers = {k.lower(): v for k, v in headers.items() if k.lower().startswith('x-mbx-')}

        # Get X-MBX-used-weight-1m
        registered = self.minutes_weights.get(current_minute, 0)
        delta1 = self.wrong_registered_value(header='x-mbx-used-weight-1m', normalized_headers=normalized_headers, registered_weight=registered)
        if delta1:
            self.minutes_weights.update({current_minute: int(normalized_headers['x-mbx-used-weight-1m'])})

        # Get X-MBX-used-weight-10s
        registered = self.ten_seconds_orders_counts.get(current_minute, 0)
        delta2 = self.wrong_registered_value(header='x-mbx-order-count-10s', normalized_headers=normalized_headers, registered_weight=registered)
        if delta2:
            self.ten_seconds_orders_counts.update({current_ten_seconds: int(normalized_headers['x-mbx-order-count-10s'])})

        # x-mbx-order-count-1d
        registered = self.days_counts.get(current_day, 0)
        delta3 = self.wrong_registered_value(header='x-mbx-order-count-1d', normalized_headers=normalized_headers, registered_weight=registered)
        if delta3:
            self.days_counts.update({current_day: int(normalized_headers['x-mbx-order-count-1d'])})

        # check for new headers
        self.verify_unknown_headers(normalized_headers)


if __name__ == "__main__":

    import requests
    from panzer.request import get, post

    # Define base URL for Binance API
    BASE_URL = 'https://api.binance.com'

    # Define public endpoints for testing
    CALLS = [
        ('/api/v3/time', 1, [], False, "GET"),
        ('/api/v3/exchangeInfo', 20, [], False, "GET"),
        ('/api/v3/ticker/price', 4, [], False, "GET"),
        ('/api/v3/order/test', 1, {'symbol': "BTCUSDT",
                                   'side': "SELL",
                                   'type': "LIMIT",
                                   'timeInForce': 'GTC',  # Good 'Til Canceled
                                   'quantity': 0.001,
                                   'price': 80000,
                                   'recvWindow': 5000,
                                   'timestamp': int(time() * 1000)},
         True, "POST"),
        ('/api/v3/order', 1, {'symbol': "BTCUSDT",
                              'side': "SELL",
                              'type': "LIMIT",
                              'timeInForce': 'GTC',  # Good 'Til Canceled
                              'quantity': 0.001,
                              'price': 80000,
                              'recvWindow': 5000,
                              'timestamp': int(time() * 1000)},
         True, "POST"),
    ]


    def test_rate_limiter(rate_limiter):
        for endpoint, weight, params, signed, method in CALLS:
            url = BASE_URL + endpoint

            can = rate_limiter.can_make_request(weight=weight, is_order=url == "/api/v3/order")
            print(f"\nCan make request to {endpoint} w={weight}: {can}\n{rate_limiter.get()}\n")

            # Make the API call
            if can:
                if method == "GET":
                    response, headers = get(url, params=params, full_sign=signed)
                elif method == "POST":
                    response, headers = post(url, params=params, full_sign=signed)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                x_headers = {h: v for h, v in headers.items() if h.startswith('x-mbx-')}
                print(f"Response Headers for {endpoint}: {x_headers}")
                rate_limiter.update_from_headers(headers)
            else:
                print(f"Cannot make request to {endpoint}. Rate limit exceeded.")
                continue


    # Initialize your BinanceRateLimiter
    rate_limiter = BinanceRateLimiter(
        rate_limit_per_minute=1200,
        rate_limit_per_second=10,
        orders_limit_per_ten_seconds=10,
        weight_limit_per_minute=50000,
        rate_limit_per_day=65000,
        info_level="DEBUG"
    )

    # Test the rate limiter with the public endpoints
    test_rate_limiter(rate_limiter)
