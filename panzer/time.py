from typing import Union
from time import time
import requests

from panzer.logs import LogManager

logger = LogManager(filename='logs/time.log', name='time', info_level='INFO')


def get_server_time() -> Union[int, None]:
    """
    Get the current server time from Binance API.

    :return int: A Unix timestamp in milliseconds.
    """
    base_url = 'https://api.binance.com'  # Base URL for the Binance API
    endpoint = '/api/v3/time'  # API endpoint to get server time

    try:
        response = requests.get(url=base_url + endpoint)
        response.raise_for_status()  # Raise an error for bad status codes (4xx/5xx)

        # Parse the JSON response and extract serverTime
        server_time = response.json()['serverTime']
        return int(server_time)

    except requests.exceptions.RequestException as e:
        # Handle potential request errors
        logger.error(f"Error fetching server time: {e}")
        return None


def second(time_milliseconds: int) -> int:
    """
    Returns the second part of a given time in milliseconds.

    :param time_milliseconds: The time in milliseconds.
    :return: The second part of the given time.
    """
    return int(time_milliseconds // 1000)


def ten_seconds(time_milliseconds: int) -> int:
    """
    Returns the ten-second part of a given time in milliseconds.

    :param time_milliseconds: The time in milliseconds.
    :return: The ten-second part of the given time.
    """
    return int(time_milliseconds // 10000)


def minute(time_milliseconds: int) -> int:
    """
    Returns the minute part of a given time in milliseconds.

    :param time_milliseconds: The time in milliseconds.
    :return: The minute part of the given time.
    """
    return int(time_milliseconds / 60000) * 60000


def hour(time_milliseconds: int) -> int:
    """
    Returns the hour part of a given time in milliseconds.

    :param time_milliseconds: The time in milliseconds.
    :return: The hour part of the given time.
    """
    return int(time_milliseconds / 3600000) * 3600000


def day(time_milliseconds: int) -> int:
    """
    Returns the day part of a given time in milliseconds.

    :param time_milliseconds: The time in milliseconds.
    :return: The day part of the given time.
    """
    return int(time_milliseconds / 86400000) * 86400000


def update_server_time_offset(server_time_offset: int = 0):
    """
    Updates the server time offset by fetching the current server time from the Binance API.

    :return: The updated server time offset in milliseconds.
    """
    server_time = get_server_time()
    if server_time is not None:
        server_time_offset = server_time - (int(time() * 1000))
        logger.info(f"Updated server-local time offset: {server_time_offset} ms")
    return server_time_offset
