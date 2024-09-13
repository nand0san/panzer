from typing import Union
from time import time, sleep

from panzer.request import get
from panzer.logs import LogManager
from panzer.time import second, ten_seconds, minute, five_minutes, hour, day, update_server_time_offset


def fetch_rate_limits():
    """
    Fetches the rate limits from Binance API and returns them as a dictionary.

    API example response:

        [{'rateLimitType': 'REQUEST_WEIGHT',
          'interval': 'MINUTE',
          'intervalNum': 1,
          'limit': 6000},
         {'rateLimitType': 'ORDERS',
          'interval': 'SECOND',
          'intervalNum': 10,
          'limit': 100},
         {'rateLimitType': 'ORDERS',
          'interval': 'DAY',
          'intervalNum': 1,
          'limit': 200000},
         {'rateLimitType': 'RAW_REQUESTS',
          'interval': 'MINUTE',
          'intervalNum': 5,
          'limit': 61000}]

    :return: A dictionary with different rate limits for requests and orders.
    """
    url = 'https://api.binance.com/api/v3/exchangeInfo'

    try:
        # Make a request to fetch exchange information
        data, headers = get(url)
        rate_limits = {}

        # Parse the rate limits from the response
        print(f"Rate limits: {data['rateLimits']}")

        for limit_ in data.get('rateLimits', []):
            limit_type = limit_.get('rateLimitType')
            interval = limit_.get('interval')
            interval_num = limit_.get('intervalNum')
            limit_value = limit_.get('limit')

            # Fill in the dictionary with appropriate values
            if limit_type == 'REQUEST_WEIGHT' and interval == 'MINUTE':
                assert interval_num == 1, f"Invalid interval number for REQUEST_WEIGHT 1 MINUTE: {interval_num}"
                rate_limits['weight_limit_per_minute'] = limit_value

            elif limit_type == 'ORDERS' and interval == 'SECOND':
                assert interval_num == 10, f"Invalid interval number for ORDERS 10 SECOND: {interval_num}"
                rate_limits['orders_limit_per_ten_seconds'] = limit_value

            elif limit_type == 'ORDERS' and interval == 'DAY':
                assert interval_num == 1, f"Invalid interval number for ORDERS 1 DAY: {interval_num}"
                rate_limits['orders_limit_per_day'] = limit_value

            elif limit_type == 'RAW_REQUESTS' and interval == 'MINUTE':
                assert interval_num == 5, f"Invalid interval number for RAW_REQUESTS 5 MINUTE: {interval_num}"
                rate_limits['raw_limit_per_5_minutes'] = limit_value

        return rate_limits

    except Exception as e:
        print(f"Error fetching rate limits: {e}")
        return None


class BinanceRateLimiter:
    def __init__(self,
                 rate_limits: dict = None,
                 info_level: str = "INFO"):
        """
        Initializes the class with specified limits.

        Example of expected rate_limits:

            {'weight_limit_per_minute': 6000,
                'orders_limit_per_ten_seconds': 100,
                'orders_limit_per_day': 200000,
                'raw_limit_per_5_minutes': 61000}

        :param rate_limits: A dictionary with rate limits.
        :param info_level: The log level for the logger.
        """
        self.logger = LogManager(filename='logs/limits.log', info_level=info_level)
        self.server_time_offset = 0

        # Request rate limits
        boot_weight = 0
        if rate_limits is None:
            rate_limits = fetch_rate_limits() | dict()
            boot_weight += 20

        self.raw_limit_per_5_minutes = rate_limits.get('raw_limit_per_5_minutes', 50000)
        self.orders_limit_per_ten_seconds = rate_limits.get('orders_limit_per_ten_seconds', 10)
        self.orders_limit_per_day = rate_limits.get('orders_limit_per_day', 150000)
        self.weight_limit_per_minute = rate_limits.get('weight_limit_per_minute', 5000)

        # Track current request counts and weights
        self.minutes_weights = {self._get_current_minute(): boot_weight}

        # self.seconds_counts = {}
        # self.minutes_counts = {}
        self.five_minutes_counts = {self._get_current_five_minutes(): 1}
        self.ten_seconds_orders_counts = {}
        self.daily_orders_count = {}

        # clean counters and offset updates
        self.clean_period_minutes = 7  # minutes para actualizar offset y limpieza de limites registrados
        self.minute_for_clean = minute(time_milliseconds=int(time() * 1000)) + self.clean_period_minutes
        self.hour_for_clean = hour(time_milliseconds=int(time() * 1000)) + 1
        self._update_server_time_offset()

    def _update_server_time_offset(self):
        """
        Updates the server time offset by fetching the current server time from the Binance API.

        :return: The updated server time offset in milliseconds.
        """
        # current_second = self._get_current_second()
        current_minute = self._get_current_minute()
        current_five_minutes = self._get_current_five_minutes()

        # seconds_count = self.seconds_counts.get(current_second, 0) + 1
        # minutes_count = self.minutes_counts.get(current_minute, 0) + 1
        five_minutes_count = self.five_minutes_counts.get(current_five_minutes, 0) + 1
        minutes_weights = self.minutes_weights.get(current_minute, 0) + 1

        if five_minutes_count <= self.raw_limit_per_5_minutes and minutes_weights <= self.weight_limit_per_minute:
            if hasattr(self, 'server_time_offset'):
                self.server_time_offset = update_server_time_offset(self.server_time_offset)
            else:
                self.server_time_offset = update_server_time_offset()
            # update counts because of update of server time offset
            # self.seconds_counts.update({current_second: seconds_count})
            # self.minutes_counts.update({current_minute: minutes_count})
            self.minutes_weights.update({current_minute: minutes_weights})
            self.five_minutes_counts.update({current_five_minutes: five_minutes_count})
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

    def _get_current_five_minutes(self):
        """
        Returns the current five minutes using server time or local time,
        adjusted with the server time offset.

        :return: The current five minutes (server time).
        """
        # Get current UTC time
        current_time = int(time() * 1000)
        corrected_time = current_time + self.server_time_offset
        return five_minutes(corrected_time)

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
        self.minutes_weights = {k: self.minutes_weights[k] for k in sorted(list(self.minutes_weights.keys()))[-3:]}

        # self.seconds_counts = {k: self.seconds_counts[k] for k in sorted(list(self.seconds_counts.keys()))[-3:]}
        # self.minutes_counts = {k: self.minutes_counts[k] for k in sorted(list(self.minutes_counts.keys()))[-3:]}
        self.five_minutes_counts = {k: self.five_minutes_counts[k] for k in sorted(list(self.five_minutes_counts.keys()))[-3:]}

        self.ten_seconds_orders_counts = {k: self.ten_seconds_orders_counts[k] for k in
                                          sorted(list(self.ten_seconds_orders_counts.keys()))[-3:]}
        self.daily_orders_count = {k: self.daily_orders_count[k] for k in sorted(list(self.daily_orders_count.keys()))[-3:]}

        self.logger.debug(f"Cleaned counters: {self.get()}")

    def get(self):
        """Get current counter values."""
        return {
            "orders_limit_per_ten_seconds": self.orders_limit_per_ten_seconds,
            "orders_limit_per_day": self.orders_limit_per_day,
            "weight_limit_per_minute": self.weight_limit_per_minute,
            "raw_limit_per_5_minutes": self.raw_limit_per_5_minutes,

            "server_time_offset": self.server_time_offset,

            "five_minutes_counts": self.five_minutes_counts,
            "minutes_weights": self.minutes_weights,
            "ten_seconds_orders_counts": self.ten_seconds_orders_counts,
            "daily_orders_count": self.daily_orders_count,
        }

    def _check_limit(self, current_value: int, limit: int, current_interval: int, interval_duration: int) -> Union[int, None]:
        """
        Verifies if the current value exceeds the limit for a given interval and returns the wait time if needed.

        :param current_value: The current number of requests/orders/weight within the interval.
        :param limit: The allowed limit within the interval.
        :param current_interval: The current time unit (in seconds) for the interval (e.g., minute, hour, etc.).
        :param interval_duration: The duration of the interval (e.g., 60 seconds for minute, 300 seconds for 5 minutes).
        :return: The number of seconds to wait if the limit is exceeded, or None if the limit is not exceeded.
        """
        if current_value >= limit:
            next_interval_start = (current_interval + interval_duration)  # Calculate the next interval start time
            current_time = int(time())  # utc seconds
            wait_time = next_interval_start - current_time
            self.logger.warning(f"Limit exceeded: waiting for {wait_time} seconds.")
            return wait_time
        return None

    def wait_for_api(self):
        """Identifies which limit is overloaded and waits until the end of the limit cycle to renew the limit."""

        current_ten_seconds = self._get_current_ten_seconds()
        current_minute = self._get_current_minute()
        current_five_minutes = self._get_current_five_minutes()
        current_day = self._get_current_day()

        # Check minute weight limit
        wait_time = self._check_limit(current_value=self.minutes_weights.get(current_minute, 0),
                                      limit=self.weight_limit_per_minute,
                                      current_interval=current_minute,
                                      interval_duration=60)
        if wait_time:
            self.logger.warning(f"Minute weight limit exceeded: waiting for {wait_time} seconds.")
            sleep(wait_time)

        # Check ten-second orders limit
        wait_time = self._check_limit(current_value=self.ten_seconds_orders_counts.get(current_ten_seconds, 0),
                                      limit=self.orders_limit_per_ten_seconds,
                                      current_interval=current_ten_seconds,
                                      interval_duration=10)
        if wait_time:
            self.logger.warning(f"Ten-second orders limit exceeded: waiting for {wait_time} seconds.")
            sleep(wait_time)

        # Check five-minute raw request limit
        wait_time = self._check_limit(current_value=self.five_minutes_counts.get(current_five_minutes, 0),
                                      limit=self.raw_limit_per_5_minutes,
                                      current_interval=current_five_minutes,
                                      interval_duration=300)
        if wait_time:
            self.logger.warning(f"Five-minute raw request limit exceeded: waiting for {wait_time} seconds.")
            sleep(wait_time)

        # Check daily orders limit
        wait_time = self._check_limit(current_value=self.daily_orders_count.get(current_day, 0),
                                      limit=self.orders_limit_per_day,
                                      current_interval=current_day,
                                      interval_duration=86400)
        if wait_time:
            self.logger.warning(f"Daily orders limit exceeded: waiting for {wait_time} seconds.")
            sleep(wait_time)

        self.logger.info("API limits reset, proceeding with requests.")

    def can_make_request(self, weight: int, is_order: bool, wait_mode: bool = True) -> bool:
        """
        Checks whether a request can be made without exceeding the rate or weight limits.

        :param weight: The weight of the current request.
        :param is_order: Whether the request is for an order. This adds to the ten seconds limit.
        :param wait_mode: If True, waits for the limit to reset before making the request.
        :return: True if the request can be made, False otherwise.
        """
        # current_second = self._get_current_second()
        current_ten_seconds = self._get_current_ten_seconds()
        current_minute = self._get_current_minute()
        current_five_minutes = self._get_current_five_minutes()
        current_hour = self._get_current_hour()
        current_day = self._get_current_day()

        current_minute_weight = self.minutes_weights.get(current_minute, 0)
        # current_second_count = self.seconds_counts.get(current_second, 0)
        current_ten_seconds_orders_count = self.ten_seconds_orders_counts.get(current_ten_seconds, 0)
        current_day_count = self.daily_orders_count.get(current_day, 0)
        # current_minute_count = self.minutes_counts.get(current_minute, 0)
        current_five_minutes_count = self.five_minutes_counts.get(current_five_minutes, 0)

        # weight limit per minute
        if current_minute_weight + weight > self.weight_limit_per_minute:
            if wait_mode:
                self.wait_for_api()
                return self.can_make_request(weight, is_order, wait_mode)
            else:
                return False
        else:
            self.minutes_weights.update({current_minute: current_minute_weight + weight})

        if current_five_minutes_count + 1 > self.raw_limit_per_5_minutes:
            if wait_mode:
                self.wait_for_api()
                return self.can_make_request(weight, is_order, wait_mode)
            else:
                return False
        else:
            self.five_minutes_counts.update({current_five_minutes: current_five_minutes_count + 1})

        if is_order and (current_ten_seconds_orders_count + 1) > self.orders_limit_per_ten_seconds:
            if wait_mode:
                self.wait_for_api()
                return self.can_make_request(weight, is_order, wait_mode)
            else:
                return False
        elif is_order:
            self.ten_seconds_orders_counts.update({current_ten_seconds: current_ten_seconds_orders_count + 1})

        if is_order and current_day_count + 1 > self.orders_limit_per_day:
            if wait_mode:
                self.wait_for_api()
                return self.can_make_request(weight, is_order, wait_mode)
            else:
                return False
        elif is_order:
            self.daily_orders_count.update({current_day: current_day_count + 1})

        # cleaning and update offsets
        if current_minute >= self.minute_for_clean or current_hour >= self.hour_for_clean:
            self.minute_for_clean = current_minute + self.clean_period_minutes
            self.hour_for_clean = current_hour + 1
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
        expected_headers = {'x-mbx-uuid',
                            'x-mbx-traceid',
                            'x-mbx-used-weight',
                            'x-mbx-used-weight-1m',
                            'x-mbx-order-count-10s',
                            'x-mbx-order-count-1d'}
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
        registered = self.ten_seconds_orders_counts.get(current_ten_seconds, 0)
        delta2 = self.wrong_registered_value(header='x-mbx-order-count-10s', normalized_headers=normalized_headers, registered_weight=registered)
        if delta2:
            self.ten_seconds_orders_counts.update({current_ten_seconds: int(normalized_headers['x-mbx-order-count-10s'])})

        # x-mbx-order-count-1d
        registered = self.daily_orders_count.get(current_day, 0)
        delta3 = self.wrong_registered_value(header='x-mbx-order-count-1d', normalized_headers=normalized_headers, registered_weight=registered)
        if delta3:
            self.daily_orders_count.update({current_day: int(normalized_headers['x-mbx-order-count-1d'])})

        # check for new headers
        self.verify_unknown_headers(normalized_headers)

    def __repr__(self):
        """
        Returns a string representation of the BinanceRateLimiter object.

        The string representation includes the current rate limits for requests and orders, as well as the server time offset.

        :return: A string representation of the BinanceRateLimiter object.
        """
        return f"BinanceRateLimit(weight_limit_per_minute={self.weight_limit_per_minute}, " \
               f"raw_limit_per_5_minutes={self.raw_limit_per_5_minutes}, " \
               f"orders_limit_per_ten_seconds={self.orders_limit_per_ten_seconds}, " \
               f"orders_limit_per_day={self.orders_limit_per_day}, " \
               f"clean_period_minutes={self.clean_period_minutes}, " \
               f"server_time_offset={self.server_time_offset}, "


if __name__ == "__main__":
    from panzer.request import get, post

    # Define base URL for Binance API
    BASE_URL = 'https://api.binance.com'

    # Define public endpoints for testing
    CALLS = [
        ('/api/v3/time', 1, [], False, "GET"),
        ('/api/v3/exchangeInfo', 20, [], False, "GET"),
        ('/api/v3/ticker/price', 4, [], False, "GET"),
        # ('/api/v3/order/test', 1, {'symbol': "BTCUSDT",
        #                            'side': "SELL",
        #                            'type': "LIMIT",
        #                            'timeInForce': 'GTC',  # Good 'Til Canceled
        #                            'quantity': 0.001,
        #                            'price': 80000,
        #                            'recvWindow': 10000,
        #                            'timestamp': int(time() * 1000)},
        #  True, "POST"),
        # ('/api/v3/order', 1, {'symbol': "BTCUSDT",
        #                       'side': "SELL",
        #                       'type': "LIMIT",
        #                       'timeInForce': 'GTC',  # Good 'Til Canceled
        #                       'quantity': 0.001,
        #                       'price': 80000,
        #                       'recvWindow': 5000,
        #                       'timestamp': int(time() * 1000)},
        #  True, "POST"),
        # ('/api/v3/order', 1, {'symbol': "BTCUSDT",
        #                       'side': "SELL",
        #                       'type': "LIMIT",
        #                       'timeInForce': 'GTC',  # Good 'Til Canceled
        #                       'quantity': 0.001,
        #                       'price': 80000,
        #                       'recvWindow': 5000,
        #                       'timestamp': int(time() * 1000)},
        #  True, "POST"),
        # ('/api/v3/order', 1, {'symbol': "BTCUSDT",
        #                       'side': "SELL",
        #                       'type': "LIMIT",
        #                       'timeInForce': 'GTC',  # Good 'Til Canceled
        #                       'quantity': 0.001,
        #                       'price': 80000,
        #                       'recvWindow': 5000,
        #                       'timestamp': int(time() * 1000)},
        #  True, "POST"),
    ]


    def test_rate_limiter(rate_limiter):
        for endpoint, weight, params, signed, method in CALLS:
            url = BASE_URL + endpoint
            is_order = url.endswith("/api/v3/order")
            can = rate_limiter.can_make_request(weight=weight, is_order=is_order)
            print(f"\n----------------\n"
                  f"Can make request to {endpoint} w={weight} is_order={is_order} can_make={can}\n{rate_limiter.get()}\n")

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
                raise Exception(f"Cannot make request to {endpoint}. Rate limit exceeded.")
        # loop for overcharging
        # test_rate_limiter(rate_limiter)


    # Initialize your BinanceRateLimiter
    rate_limiter = BinanceRateLimiter(info_level="DEBUG")

    # Test the rate limiter with the public endpoints
    test_rate_limiter(rate_limiter)
