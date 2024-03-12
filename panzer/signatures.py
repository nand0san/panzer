import hmac
import hashlib
import time
import requests
from typing import Union, List, Tuple
from panzer.keys import SecureKeyManager, SecretModuleImporter
from urllib.parse import urljoin
from panzer.logs import APICallLogger


class BinanceRequestSigner:
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

    def sign_and_send_request(self,
                              params: List[Tuple[str, Union[int, str]]],
                              endpoint: str,
                              url: str = 'https://api.binance.com/',
                              method: str = 'POST') -> requests.Response:

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

        full_url = urljoin(url, endpoint)
        headers = {'X-MBX-APIKEY': self.get_api_key()}
        data = dict(params)

        # Enviar la petición
        if method.upper() == 'POST':
            response = requests.post(url=full_url, headers=headers, data=data)
        elif method.upper() == 'GET':
            response = requests.get(url=full_url, headers=headers, params=data)
        else:
            raise ValueError(f"Unsupported request method: {method}")

        self.api_learn_logger.log(method=method,
                                  base_url=url,
                                  endpoint=endpoint,
                                  url=full_url,
                                  status_code=response.status_code,
                                  params=params,
                                  request_headers=headers,
                                  response_headers=response.headers,
                                  body=response.text,
                                  json_response=response.json(),
                                  error=response.text if response.status_code != 200 else None)
        return response


if __name__ == "__main__":
    signer = BinanceRequestSigner()

    params = [('symbol', 'BTCUSDT'),]
    # ('side', 'SELL'),
    # ('type', 'LIMIT'),
    # ('timeInForce', 'GTC'),
    # ('quantity', '1'),
    # ('price', '0.1'),]

    response = signer.sign_and_send_request(params=params,
                                            endpoint='/api/v3/allOrders',
                                            url='https://api.binance.com/',
                                            method='GET')
    print(response.status_code)
    print(response.json())

    # muestra headers de respuesta
    print(response.headers)
