import hashlib
import hmac
import time
from typing import Union, List, Tuple

from panzer.keys import SecureKeychain
from panzer.logs import APICallMapper, LogManager


class RequestSigner:
    """
    Manages the signing of requests for various Binance API endpoints with different security requirements. This class supports
    the automatic addition of API keys and the signing of requests with a secret key for endpoints requiring authentication.

    Security Types:
    - NONE: Endpoint can be accessed freely.
    - TRADE, MARGIN, USER_DATA: Endpoints require sending a valid API-Key and signature.
    - USER_STREAM, MARKET_DATA: Endpoints require sending a valid API-Key.
    """
    def __init__(self,
                 api_key_string_encoded: str = "api_key",
                 secret_key_string_encoded: str = "api_secret"):
        """
        Initializes the Binance request signer with API and secret keys retrieved from a secure storage.

        :param api_key_string_encoded: The name of the API key in the secret storage.
        :param secret_key_string_encoded: The name of the secret key in the secret storage.
        """

        self.api_key_string = api_key_string_encoded
        self.secret_key_string = secret_key_string_encoded

        self.secret_module_importer = SecretModuleImporter()
        self.api_key = self.secret_module_importer.get_secret(secret_name=api_key_string_encoded)
        self.secret_key = self.secret_module_importer.get_secret(secret_name=secret_key_string_encoded)

        self.key_manager = SecureKeychain()
        self.key_manager.add_key(key_name=self.api_key_string, key_value=self.api_key)
        self.key_manager.add_key(key_name=self.secret_key_string, key_value=self.secret_key)

        self.api_learn_logger = APICallMapper(log_file='api_learn_logger.csv')

    def get_api_key(self) -> str:
        """
        Retrieves the API key from the secure key manager.

        :return: The API key as a string.
        """
        return self.key_manager.get_decrypted_key(self.api_key_string)

    def get_secret_key(self) -> str:
        """
        Retrieves the secret key from the secure key manager.

        :return: The secret key as a string.
        """
        return self.key_manager.get_decrypted_key(self.secret_key_string)

    def add_api_key_to_headers(self, headers: dict) -> dict:
        """
        Adds the API key to the request headers.

        :param headers: The existing request headers.
        :return: The updated headers dictionary including the API key.
        """
        headers['X-MBX-APIKEY'] = self.get_api_key()
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
        signature = hmac.new(key=self.get_secret_key().encode(),
                             msg=query_string.encode(),
                             digestmod=hashlib.sha256).hexdigest()
        params.append((signature_field, signature))
        return params


if __name__ == "__main__":
    signer = RequestSigner()

    params = [('symbol', 'BTCUSDT'),]
    # ('side', 'SELL'),
    # ('type', 'LIMIT'),
    # ('timeInForce', 'GTC'),
    # ('quantity', '1'),
    # ('price', '0.1'),]

    signature = signer.sign_params(params=params, )
    #                                         endpoint='/api/v3/allOrders',
    #                                         url='https://api.binance.com/',
    #                                         method='GET')
    # print(response.status_code)
    # print(response.json())
    #
    # # muestra headers de respuesta
    # print(response.headers)
    print(signature)
