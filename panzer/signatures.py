import hashlib
import hmac
import time
from typing import Union, List, Tuple

from panzer.keys import SecureKeyManager, SecretModuleImporter
from panzer.logs import APICallLogger


class BinanceRequestSigner:
    """
    Security Type	Description
    ---------------------------
    NONE	Endpoint can be accessed freely.
    TRADE	Endpoint requires sending a valid API-Key and signature.
    MARGIN	Endpoint requires sending a valid API-Key and signature.
    USER_DATA	Endpoint requires sending a valid API-Key and signature.
    USER_STREAM	Endpoint requires sending a valid API-Key.
    MARKET_DATA	Endpoint requires sending a valid API-Key.
    """
    def __init__(self,
                 api_key_string: str = "api_key",
                 secret_key_string: str = "api_secret"):

        self.api_key_string = api_key_string
        self.secret_key_string = secret_key_string

        self.secret_module_importer = SecretModuleImporter()
        self.api_key = self.secret_module_importer.get_secret(secret_name=api_key_string)
        self.secret_key = self.secret_module_importer.get_secret(secret_name=secret_key_string)

        self.key_manager = SecureKeyManager()
        self.key_manager.add_encrypted_key(key_name=self.api_key_string, key_value=self.api_key)
        self.key_manager.add_encrypted_key(key_name=self.secret_key_string, key_value=self.secret_key)

        self.api_learn_logger = APICallLogger(log_file='api_learn_logger.csv')

    def get_api_key(self) -> str:
        return self.key_manager.get_key(self.api_key_string)

    def get_secret_key(self) -> str:
        return self.key_manager.get_key(self.secret_key_string)

    def add_api_key_to_headers(self, headers: dict) -> dict:
        headers['X-MBX-APIKEY'] = self.get_api_key()
        return headers

    def sign_params(self,
                    params: List[Tuple[str, Union[int, str]]],
                    add_timestamp: bool = False,
                    ) -> List[Tuple[str, Union[int, str]]]:
        if add_timestamp:
            now = int(time.time() * 1000)
            ts = ('timestamp', now,)
            params.append(ts)

        # Convertir la lista de tuplas a una cadena de consulta
        query_string = '&'.join([f'{key}={value}' for key, value in params])

        # Crear la firma
        signature = hmac.new(key=self.get_secret_key().encode(),
                             msg=query_string.encode(),
                             digestmod=hashlib.sha256).hexdigest()
        params.append(('signature', signature))
        return params


if __name__ == "__main__":
    signer = BinanceRequestSigner()

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
