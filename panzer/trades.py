from urllib.parse import urljoin
import requests

from panzer.limits import BinanceAPILimitsManager
from panzer.signatures import RequestSigner
from panzer.logs import LogManager


class BinanceTradeFetcher:
    def __init__(self, symbol: str, api_limits: BinanceAPILimitsManager):
        """
        Initialize the trade fetcher with the trading symbol and API limits manager.

        :param symbol: The trading pair symbol (e.g., 'BTCUSDT').
        :param api_limits: Instance of BinanceAPILimitsManager to handle API weight limits.
        """
        self.base_url = 'https://api.binance.com'
        self.endpoint = '/api/v3/trades'
        self.symbol = symbol
        self.signer = RequestSigner()  # Handles API key and request signing
        self.limits_manager = api_limits
        self.logger = LogManager(filename=f'trades_{symbol}.log', info_level='INFO')

    def fetch_trades(self, limit=1000, start_time: int = None, end_time: int = None):
        """
        Fetch trades from the Binance API with optional time filters and automatic pagination.

        :param limit: Max number of trades per request (500 max allowed by Binance).
        :param start_time: Start timestamp for filtering trades.
        :param end_time: End timestamp for filtering trades.
        :return: List of trades.
        """
        trades = []
        params = {
            'symbol': self.symbol,
            'limit': limit,
        }

        if start_time:
            params['startTime'] = int(start_time * 1000)  # Convert to milliseconds

        if end_time:
            params['endTime'] = int(end_time * 1000)  # Convert to milliseconds

        while True:
            # Prepare the request headers and sign the parameters
            url = urljoin(self.base_url, self.endpoint)
            headers = self.signer.add_api_key_to_headers({})
            signed_params = self.signer.sign_params(params=list(params.items()), add_timestamp=True)

            # Check API weight limits before making the request
            self.limits_manager.check_and_wait_timestamp(endpoint=self.endpoint)

            # Make the API request
            response = requests.get(url, params=signed_params, headers=headers)

            # Log and handle the response
            self.limits_manager.update(response=response, endpoint=self.endpoint)
            self.logger.info(f"Fetched trades for symbol {self.symbol}: {len(response.json())} trades.")

            if response.status_code == 200:
                trades_batch = response.json()
                if not trades_batch:
                    break  # No more trades to fetch

                trades.extend(trades_batch)
                params['fromId'] = trades_batch[-1]['id']  # Get the last trade ID for pagination
            else:
                self.logger.error(f"Error fetching trades: {response.status_code} - {response.text}")
                break  # Stop fetching if there's an error

        return trades


# Example Usage
if __name__ == "__main__":
    api_limits = BinanceAPILimitsManager(info_level='INFO')
    trade_fetcher = BinanceTradeFetcher(symbol='BTCUSDT', api_limits=api_limits)
    trades = trade_fetcher.fetch_trades(limit=500, start_time=1622505600, end_time=1625097600)  # Fetch trades for a time range
    print(f"Total trades fetched: {len(trades)}")
