from typing import Union, List, Tuple, Dict, Optional
import requests

from panzer.logs import LogManager
from panzer.errors import BinanceRequestHandler
from panzer.signatures import RequestSigner

logger = LogManager(filename="logs/request.log", name="request", info_level="INFO")
signer = RequestSigner()


def params_clean_none(params: Union[List[Tuple[str, Union[str, int]]], Dict[str, Union[str, int]]],
                      recvWindow: int) -> Dict[str, Union[str, int]]:
    """
    Cleans the parameters by removing any with a value of `None` and adds 'recvWindow' to the set of parameters.

    :param params: The parameters to be cleaned, can be a dictionary or a list of tuples.
    :type params: Union[List[Tuple[str, Union[str, int]]], Dict[str, Union[str, int]]]
    :param recvWindow: The 'recvWindow' value to be added to the parameters.
    :type recvWindow: int
    :return: The cleaned parameters as a dictionary with no `None` values and 'recvWindow' added.
    :rtype: Dict[str, Union[str, int]]
    """
    if isinstance(params, dict):
        params['recvWindow'] = recvWindow
        return {k: v for k, v in params.items() if v is not None}
    elif isinstance(params, list):
        params.append(('recvWindow', recvWindow))
        return {k: v for k, v in params if v is not None}
    return {}


def sign_request(params: Union[Dict[str, Union[str, int]], List[Tuple[str, Union[str, int]]]],
                 full_sign: bool = True,
                 recvWindow: Optional[int] = None,
                 server_time_offset: int = 0) -> Tuple[List[Tuple[str, Union[str, int]]], Dict[str, str]]:
    """
    Adds a signature to the request. Returns a list of parameters as tuples and a headers dictionary.

    :param params: Parameters for the request, either as a dictionary or a list of tuples.
    :type params: Union[Dict[str, Union[str, int]], List[Tuple[str, Union[str, int]]]]
    :param full_sign: Whether to sign the request. This is True by default.
    :type full_sign: bool
    :param recvWindow: The request's time-to-live in milliseconds. For some endpoints like /api/v3/historicalTrades, it is not required.
    :type recvWindow: Optional[int]
    :param server_time_offset: The server time offset to avoid calling the time API frequently.
    :type server_time_offset: int
    :return: A tuple containing the list of parameters (as tuples) and a dictionary of headers.
    :rtype: Tuple[List[Tuple[str, Union[str, int]]], Dict[str, str]]
    """
    logger.debug(f"sign_request: {params}")

    params = params_clean_none(params, recvWindow) if recvWindow else params
    timestamped = False
    params_tuples: List[Tuple[str, Union[str, int]]] = []
    for k, v in params.items():
        if isinstance(v, list):
            for i in v:
                params_tuples.append((k, i))
        else:
            if k == "timestamp":
                timestamped = True
            params_tuples.append((k, v))

    headers = signer.add_api_key_to_headers(headers={})
    if full_sign:
        params_tuples = signer.sign_params(params=params_tuples,
                                           add_timestamp=not timestamped,
                                           server_time_offset=server_time_offset)
    else:
        headers = signer.add_api_key_to_headers(headers=headers)
    return params_tuples, headers


def call(mode: str,
         url: str,
         params: Optional[List[Tuple[str, Union[str, int]]]] = None,
         headers: Optional[Dict[str, str]] = None,
         semi_signed: Optional[bool] = False,
         full_sign: bool = False,
         server_time_offset: int = 0,
         recvWindow: int = 10000) -> Union[Tuple[Dict, Dict], Tuple[List, Dict]]:
    """
    Sends a GET request to the Binance API. Before the request, it calculates the weight and waits enough time
    to avoid exceeding the rate limit for that endpoint.

    :param mode: Request type like a GET, POST, DELETE, etc.
    :type mode: str
    :param url: API endpoint URL.
    :type url: str
    :param params: Request parameters as a list of tuples, defaults to None.
    :type params: Optional[List[Tuple[str, Union[str, int]]]]
    :param headers: Request headers as a dictionary, defaults to None.
    :type headers: Optional[Dict[str, str]]
    :param semi_signed: Whether to send a semi-signed request, defaults to None.
    :type semi_signed: Optional[bool]
    :param full_sign: Whether to send a fully signed request, defaults to False.
    :type full_sign: bool
    :param server_time_offset: Server to host time delay (server - host)
    :param recvWindow: Milliseconds the request is valid for, defaults to 10000.
    :type recvWindow: int
    :return: The API response as a dictionary or list and headers.
    :rtype: Union[Tuple[Dict, Dict], Tuple[List, Dict]]
    """
    mode = mode.strip().upper()
    logger.debug(f"{mode}: {locals()}")
    if full_sign:
        params, headers = sign_request(params=params or [],
                                       full_sign=True,
                                       recvWindow=recvWindow,
                                       server_time_offset=server_time_offset)
    elif semi_signed:
        headers = sign_request(params=params or [],
                               full_sign=False,
                               recvWindow=recvWindow,
                               server_time_offset=server_time_offset)
    if mode == "GET":
        response = requests.get(url=url, params=params, headers=headers)
    elif mode == "POST":
        response = requests.post(url=url, params=params, headers=headers)
    elif mode == "DELETE":
        response = requests.delete(url=url, params=params, headers=headers)
    else:
        logger.error(f"Invalid mode: {mode}")
        raise ValueError(f"Invalid mode: {mode}")

    BinanceRequestHandler.handle_exception(response=response)
    return response.json(), dict(response.headers)


def get(url: str,
        params: Optional[List[Tuple[str, Union[str, int]]]] = None,
        headers: Optional[Dict[str, str]] = None,
        full_sign: bool = False,
        semi_signed: bool = False,
        server_time_offset: int = 0,
        recvWindow: int = 10000) -> Union[Tuple[Dict, Dict], Tuple[List, Dict]]:
    """
    Sends a GET request to the Binance API. Before the request, it calculates the weight and waits enough time
    to avoid exceeding the rate limit for that endpoint.

    :param url: API endpoint URL.
    :type url: str
    :param params: Request parameters as a list of tuples, defaults to None.
    :type params: Optional[List[Tuple[str, Union[str, int]]]]
    :param headers: Request headers as a dictionary, defaults to None.
    :type headers: Optional[Dict[str, str]]
    :param full_sign: Whether to send a fully signed request, defaults to False.
    :type full_sign: bool
    :param semi_signed: Whether to send a semi-signed request, defaults to None.
    :type semi_signed: Optional[bool]
    :param server_time_offset: Server to host time delay (server - host)
    :param recvWindow: Milliseconds the request is valid for, defaults to 10000.
    :type recvWindow: int
    :return: The API response as a dictionary or list and headers.
    :rtype: Union[Tuple[Dict, Dict], Tuple[List, Dict]]
    """
    return call(mode="GET", url=url, params=params, headers=headers, semi_signed=semi_signed, full_sign=full_sign,
                server_time_offset=server_time_offset, recvWindow=recvWindow)


def post(url: str,
         params: Optional[List[Tuple[str, Union[str, int]]]] = None,
         headers: Optional[Dict[str, str]] = None,
         full_sign: bool = False,
         semi_signed: bool = False,
         server_time_offset: int = 0,
         recvWindow: int = 10000) -> Union[Tuple[Dict, Dict], Tuple[List, Dict]]:
    """
    Sends a POST request to the Binance API. Before the request, it calculates the weight and waits enough time
    to avoid exceeding the rate limit for that endpoint.

    :param url: API endpoint URL.
    :type url: str
    :param params: Request parameters as a list of tuples, defaults to None.
    :type params: Optional[List[Tuple[str, Union[str, int]]]]
    :param headers: Request headers as a dictionary, defaults to None.
    :type headers: Optional[Dict[str, str]]
    :param full_sign: Whether to send a fully signed request, defaults to False.
    :type full_sign: bool
    :param semi_signed: Whether to send a semi-signed request, defaults to None.
    :type semi_signed: Optional[bool]
    :param server_time_offset: Server to host time delay (server - host), defaults to 0.
    :type server_time_offset: int
    :param recvWindow: Milliseconds the request is valid for, defaults to 10000.
    :type recvWindow: int
    :return: The API response as a dictionary or list and headers.
    :rtype: Union[Tuple[Dict, Dict], Tuple[List, Dict]]
    """
    return call(mode="POST", url=url, params=params, headers=headers, semi_signed=semi_signed, full_sign=full_sign,
                server_time_offset=server_time_offset, recvWindow=recvWindow)


def delete(url: str,
           params: Optional[List[Tuple[str, Union[str, int]]]] = None,
           headers: Optional[Dict[str, str]] = None,
           full_sign: bool = False,
           semi_signed: bool = False,
           server_time_offset: int = 0,
           recvWindow: int = 10000) -> Union[Tuple[Dict, Dict], Tuple[List, Dict]]:
    """
    Sends a DELETE request to the Binance API. Before the request, it calculates the weight and waits enough time
    to avoid exceeding the rate limit for that endpoint.

    :param url: API endpoint URL.
    :type url: str
    :param params: Request parameters as a list of tuples, defaults to None.
    :type params: Optional[List[Tuple[str, Union[str, int]]]]
    :param headers: Request headers as a dictionary, defaults to None.
    :type headers: Optional[Dict[str, str]]
    :param full_sign: Whether to send a fully signed request, defaults to False.
    :type full_sign: bool
    :param semi_signed: Whether to send a semi-signed request, defaults to None.
    :type semi_signed: Optional[bool]
    :param server_time_offset: Server to host time delay (server - host), defaults to 0.
    :type server_time_offset: int
    :param recvWindow: Milliseconds the request is valid for, defaults to 10000.
    :type recvWindow: int
    :return: The API response as a dictionary or list and headers.
    :rtype: Union[Tuple[Dict, Dict], Tuple[List, Dict]]
    """
    return call(mode="DELETE", url=url, params=params, headers=headers, semi_signed=semi_signed, full_sign=full_sign,
                server_time_offset=server_time_offset, recvWindow=recvWindow)


if __name__ == "__main__":
    # Example of an unsigned request (public API endpoint)
    url = "https://api.binance.com/api/v3/ticker/price"
    params = [('symbol', 'BTCUSDT')]

    try:
        response = get(url=url, params=params)
        print(f"Price of BTCUSDT: {response}")
    except Exception as e:
        logger.error(f"Error fetching BTCUSDT price: {str(e)}")

    # Example of a signed request (private API endpoint)
    private_url = "https://api.binance.com/api/v3/account"

    try:
        # Assuming proper API keys are set in RequestSigner
        response = get(url=private_url, full_sign=True)
        print(f"Account information: {response}")
    except Exception as e:
        logger.error(f"Error fetching account information: {str(e)}")
