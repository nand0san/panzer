import json
from panzer.logs import LogManager
import requests


class APIErrorLogger:
    def __init__(self,
                 log_file: str = None,
                 name: str = 'APIErrorLogger'):
        self.logger = LogManager(filename=log_file,
                                 name=name,
                                 folder='errors_learning',
                                 info_level='ERROR')

    def log_error(self, endpoint: str, response: requests.Response) -> None:
        error_data = {
            'endpoint': endpoint,
            'status_code': response.status_code,
            'error_message': response.text,
        }
        self.logger.error(json.dumps(error_data))
