import hashlib
import hmac
import time
# from fileinput import filename
from typing import Union, List, Tuple

# from win32comext.adsi.demos.scp import logger

from panzer.keys import CredentialManager
from panzer.logs import LogManager


class RequestSigner:
    """
    Manages the signing of requests for various Binance API endpoints with different security requirements. This class supports
    the automatic addition of API keys and the signing of requests with a secret key for endpoints requiring authentication.

    Security Types:
    - NONE: Endpoint can be accessed freely.
    - TRADE, MARGIN, USER_DATA: Endpoints require sending a valid API-Key and signature.
    - USER_STREAM, MARKET_DATA: Endpoints require sending a valid API-Key.
    """
    def __init__(self, info_level="INFO"):
        """
        Initializes the Binance request signer with API and secret keys retrieved from a secure storage.

        :param info_level: The level of information being logged.
        """

        self.credentials = CredentialManager()
        self.logger = LogManager(filename='logs/request_signer.log', info_level=info_level)

    def __api_key(self) -> str:
        """
        Retrieves the API key from the secure key manager.

        :return: The API key as a string.
        """
        return self.credentials.get("api_key", decrypt=True)

    def __secret_key(self) -> str:
        """
        Retrieves the secret key from the secure key manager.

        :return: The secret key as a string.
        """
        return self.credentials.get("api_secret", decrypt=True)

    def add_api_key_to_headers(self, headers: dict) -> dict:
        """
        Adds the API key to the request headers.

        :param headers: The existing request headers.
        :return: The updated headers dictionary including the API key.
        """
        headers['X-MBX-APIKEY'] = self.__api_key()
        return headers

    def sign_params(self,
                    params: List[Tuple[str, Union[int, str]]],
                    add_timestamp: bool = True,
                    timestamp_field: str = 'timestamp',
                    signature_field: str = 'signature',
                    server_time_offset: int = 0,
                    ) -> List[Tuple[str, Union[int, str]]]:
        """
        Signs the request parameters with the secret key, optionally adding a timestamp to the parameters.

        :param params: The list of parameters (key-value pairs) to be signed.
        :param add_timestamp: Whether to add the current timestamp to the parameters before signing.
        :param timestamp_field: The name of the timestamp field to be added to the parameters.
        :param signature_field: The name of the signature field to be added to the parameters.
        :param server_time_offset: The offset to apply to the server time to adjust for clock skew. Positive values mean the
                                   server time is ahead of the local time. Negative values mean the server time is behind the local time.
        :return: The list of parameters including the timestamp (if added) and the signature.
        """
        if add_timestamp:
            now = int(time.time() * 1000) + server_time_offset
            ts = (timestamp_field, now,)
            params.append(ts)

        # Convert the list of tuples into a query string
        query_string = '&'.join([f'{key}={value}' for key, value in params])

        # Create the signature
        signature = hmac.new(key=self.__secret_key().encode(),
                             msg=query_string.encode(),
                             digestmod=hashlib.sha256).hexdigest()

        params.append((signature_field, signature))
        self.logger.debug(params)
        return params


if __name__ == "__main__":
    signer = RequestSigner("DEBUG")
    params = [('symbol', 'BTCUSDT'),]
    signature = signer.sign_params(params=params, )
    print(signature)
