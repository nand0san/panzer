import requests
from socket import gethostname
from requests.exceptions import HTTPError, ConnectionError, Timeout

from panzer.logs import LogManager


exceptions_logger = LogManager(filename='logs/exceptions.log', name='exceptions', info_level='DEBUG')
hostname = gethostname() + ' exceptions '


class BinanceAPIException(Exception):
    """
    Excepción personalizada para manejar errores específicos de la API de Binance y otras excepciones.
    """

    def __init__(self, message: str, code=None, status_code=None):
        self.code = code
        self.status_code = status_code
        self.message = message
        self.msg = f"BinanceAPIException {hostname}: {self.message} (Código: {self.code}, Status: {self.status_code})"
        exceptions_logger.error(self.msg)
        super().__init__(self.msg)

    def __str__(self):
        return f"BinanceAPIException(code={self.code}, status_code={self.status_code}): {self.message}"


class BinanceRequestHandler:
    """
    Clase centralizada para manejar excepciones de la API de Binance y otras posibles excepciones de red.
    Esta clase maneja automáticamente los errores devolviendo los códigos de error y mensajes dinámicamente.
    """

    @staticmethod
    def handle_exception(response=None, exception=None):
        """
        Método estático que maneja las excepciones. Recibe una respuesta HTTP o una excepción directa.

        :param response: Objeto de respuesta HTTP de la API.
        :param exception: Excepción de requests u otros errores del sistema.
        """
        # Si hay una excepción de requests, manejarla
        if exception:
            if isinstance(exception, ConnectionError):
                raise BinanceAPIException("Error de conexión con el servidor", status_code=503)
            elif isinstance(exception, Timeout):
                raise BinanceAPIException("Tiempo de espera agotado para la respuesta", status_code=504)
            elif isinstance(exception, HTTPError):
                raise BinanceAPIException("Error HTTP recibido", status_code=exception.response.status_code)
            else:
                raise BinanceAPIException(f"Error desconocido: {str(exception)}", status_code=500)

        # Si hay una respuesta HTTP pero no es 200 OK
        if response is not None:
            if response.status_code != 200:
                try:
                    json_res = response.json()
                    code = json_res.get('code', None)
                    message = json_res.get('msg', 'Error no especificado')

                    # Registro del error y mensaje dinámico según la respuesta
                    raise BinanceAPIException(message, code=code, status_code=response.status_code)

                except ValueError:
                    # Si no es un JSON válido
                    raise BinanceAPIException(f"Respuesta inválida: {response.text}", status_code=response.status_code)


if __name__ == '__main__':

    try:
        response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDTX')
        BinanceRequestHandler.handle_exception(response=response)  # Maneja errores si existen

    except BinanceAPIException as e:
        print(e)

    except Exception as e:
        exceptions_logger.error(f"Error inesperado {hostname}: {str(e)}")
        print(f"Ocurrió un error inesperado: {str(e)}")
