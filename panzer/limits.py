import time
import requests
from binance_api_map import *
from panzer.logs import LogManager


class APILimitsManager:
    def __init__(self,
                 limits_url: str = BINANCE_LIMITS_URL,
                 limits_key: str = BINANCE_LIMITS_RESPONSE_KEY):

        self.logger = LogManager(filename="limits.log", info_level="INFO")
        self.limits_url = limits_url
        self.limits = self.fetch_exchange_limits(limits_key=BINANCE_LIMITS_RESPONSE_KEY)

        self.usage = {key: 0 for key in self.limits_url.keys()}  # Inicializa el contador de uso
        self.last_reset = time.time()

    def fetch_exchange_limits(self, limits_key: str) -> dict:
        """
        Realiza una solicitud al endpoint /api/v3/exchangeInfo de Binance y muestra la información de los límites.

        - REQUEST_WEIGHT: Este límite se aplica al peso total de las solicitudes hechas a la API dentro de un intervalo de tiempo
          determinado. Binance asigna un "peso" a cada tipo de solicitud para reflejar el coste de procesamiento de esa solicitud
          en sus sistemas. Por lo tanto, algunas solicitudes pueden contar más que otras hacia este límite. Este límite se aplica
          a la mayoría de las solicitudes de la API.
        - ORDERS: Este límite se aplica específicamente a las solicitudes que crean o cancelan órdenes. Es importante para las
          aplicaciones que realizan operaciones de trading frecuente, asegurando que no se sobrepasen los límites de creación
          o cancelación de órdenes en un intervalo de tiempo.
        - RAW_REQUESTS: Este límite parece referirse a la cantidad total de solicitudes HTTP a la API, independientemente de su
          peso o si son solicitudes de creación de órdenes. Este límite es más general y se enfoca en el número total de solicitudes
          enviadas.

        Ejemplo de respuesta:

        .. code-block:: python

            {'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 6000}
            {'rateLimitType': 'ORDERS', 'interval': 'SECOND', 'intervalNum': 10, 'limit': 100}
            {'rateLimitType': 'ORDERS', 'interval': 'DAY', 'intervalNum': 1, 'limit': 200000}
            {'rateLimitType': 'RAW_REQUESTS', 'interval': 'MINUTE', 'intervalNum': 5, 'limit': 61000}

        """
        response = requests.get(self.limits_url)
        response_data = response.json()

        # Extrae y muestra la información de los límites
        limits_info = response_data.get('rateLimits', [])
        print("Información de límites obtenida del endpoint /api/v3/exchangeInfo:")
        print(limits_info, type(limits_info))
        for limit in limits_info:
            print(limit)

    def update_usage(self, response_headers):
        """
        Actualiza el contador de uso basado en las cabeceras de respuesta de la API.

        Args:
            response_headers (dict): Las cabeceras de respuesta de la API.
        """
        for key in self.usage.keys():
            header_key = f"X-MBX-USED-WEIGHT-{key[0]}{key[1]}"
            if header_key in response_headers:
                self.usage[key] = int(response_headers[header_key])

    def should_wait(self):
        """
        Determina si se debe esperar antes de realizar la siguiente solicitud para no sobrepasar los límites.

        Returns:
            float: El número de segundos a esperar, o 0 si no es necesario esperar.
        """
        now = time.time()
        wait_time = 0
        for key, limit in self.limits_info.items():
            interval_seconds = self._get_interval_seconds(key)
            elapsed = now - self.last_reset
            if elapsed > interval_seconds:
                # Si ha pasado el intervalo, reinicia el contador de uso
                self.usage[key] = 0
                self.last_reset = now
            else:
                # Calcula si es necesario esperar para no sobrepasar el límite
                remaining_usage = limit - self.usage[key]
                if remaining_usage <= 0:
                    wait_time = max(wait_time, interval_seconds - elapsed)
        return wait_time

    def wait_if_needed(self):
        """
        Espera si es necesario antes de realizar la siguiente solicitud.
        """
        wait_time = self.should_wait()
        if wait_time > 0:
            time.sleep(wait_time)

    @staticmethod
    def _get_interval_seconds(interval):
        """
        Convierte un intervalo en segundos.

        Args:
            interval (tuple): Una tupla (intervalNum, intervalLetter).

        Returns:
            int: El intervalo en segundos.
        """
        interval_num, interval_letter = interval
        if interval_letter == 'S':
            return interval_num
        elif interval_letter == 'M':
            return interval_num * 60
        elif interval_letter == 'H':
            return interval_num * 60 * 60
        elif interval_letter == 'D':
            return interval_num * 60 * 60 * 24


def fetch_limits(self):
    """
    Hace una solicitud a la API para obtener la información actual de los límites
    y actualiza la información de los límites en la clase.
    """
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    response_data = response.json()

    # Asume que la estructura de la respuesta incluye un campo 'rateLimits' que es una lista de límites
    new_limits = {}
    for limit_info in response_data.get('rateLimits', []):
        if limit_info['rateLimitType'] in ['REQUEST_WEIGHT', 'ORDERS', 'RAW_REQUESTS']:
            interval = (limit_info['intervalNum'], limit_info['interval'])
            limit = limit_info['limit']
            new_limits[interval] = limit

    # Actualiza la información de los límites en la clase
    self.limits_info = new_limits
    self.usage = {key: 0 for key in new_limits.keys()}  # Reinicia el contador de uso


# Ejecuta la prueba para ver la respuesta de la API


if __name__ == "__main__":
    def fetch_all_orders(api_key, api_secret, symbol='BTCUSDT'):
        url = "https://api.binance.com/api/v3/allOrders"
        params = {
            'symbol': symbol,
            'timestamp': int(time.time() * 1000)
        }
        # Aquí deberías añadir la firma a params según los requisitos de Binance
        headers = {
            'X-MBX-APIKEY': api_key
        }
        response = requests.get(url, params=params, headers=headers)
        print("Cabeceras de respuesta:", response.headers)
        print("Cuerpo de respuesta:", response.json())
        return response.json()


    orders = fetch_all_orders(api_key='your_api_key', api_secret='your_api_secret')

    api = APILimitsManager()
