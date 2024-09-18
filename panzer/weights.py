import csv
from typing import Dict, Tuple
from os import path
from panzer.logs import LogManager


class WeightControl:

    def __init__(self):
        """
        Initializes the WeightControl class.

        Args:
        - weights_file (str): The path to the weights file (default is '~/.panzer_weights.csv').

        Attributes:
        - logger (LogManager): An instance of the LogManager class for logging.
        - weights_file (str): The path to the weights file.
        - weights (Dict[Tuple[str, int], int]): A dictionary containing URLs and params quantity in a tuple as keys and their corresponding weights as values.

        Raises:
        - None

        Returns:
        - None: This function does not return any value. It initializes the class attributes.
        """
        self.logger = LogManager(filename='logs/weights.log', name='weights', info_level='INFO')
        self.weights_file = self._file_exists()
        self.weights: Dict[Tuple[str, int], int] = self._load_weights()

    def _file_exists(self) -> str:
        """
        Checks if the weights file exists and if not, creates it.

        :return: The absolute path to the weights file.
        """
        # get user home directory in windows or linux
        home = path.expanduser('~')
        weights_file = path.join(home, ".panzer_weights.csv")
        if not path.exists(weights_file) or path.getsize(weights_file) == 0:
            with open(weights_file, 'w') as file:
                file.write("url,params_quantity,weight\n")
            self.logger.info(f"Weights file '{weights_file}' created.")
        return weights_file

    def _load_weights(self) -> Dict[Tuple[str, int], int]:
        """
        Loads the weights from the weights file and returns them as a dictionary.

        :return: A dictionary containing URLs and params quantity in a tuple as keys and their corresponding weights as values.
        """
        weights = {}
        with open(self.weights_file, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Saltar los encabezados
            for row in reader:
                url, qty, weight = row
                k = (url, int(qty))
                weights[k] = int(weight)
        return weights

    def _delete_weight_from_file(self, url: str, params_qty: int) -> None:
        """
        Deletes the row for the given URL and parameters quantity if it exists in the file.
        """
        deleted = False
        rows_to_keep = []
        with open(self.weights_file, 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == url and int(row[1]) == params_qty:
                    deleted = True  # Marcar para mensaje
                    continue  # Saltar la línea a eliminar
                rows_to_keep.append(row)

        with open(self.weights_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerows(rows_to_keep)

        if deleted:
            self.logger.info(f"Deleted weight entry for {url} with {params_qty} parameters from weights file.")

    def _add_new_weight_to_file(self, url: str, params_qty: int, weight: int) -> None:
        """
        Adds a new weight entry to the weights file.

        :param str url: The API endpoint URL.
        :param int params_qty: The number of parameters to add to the weight dictionary entry in the weights dictionary.
        :param int weight: The weight associated with the given URL and parameters quantity.
        :return: This function does not return any value. It updates the weights file directly.
        """
        # Eliminar cualquier entrada existente para el mismo URL y params_qty
        self._delete_weight_from_file(url, params_qty)

        # Agregar la nueva entrada
        with open(self.weights_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([url, params_qty, weight])
        self.logger.info(f"New weight database entry for {url} with {params_qty} parameters to weight of '{weight}' saved to file.")

    def get(self, url: str, params_qty: int) -> int:
        """
        Gets registered weight, but if expected_weight is provided, checks if it matches the registered weight. 
        If not, updates the weight in the weights file and in the weights variable.

        :param str url: The API endpoint URL.
        :param int params_qty: The number of parameters to get the weight for.
        :return: The registered weight for the given URL and parameters quantity, or 0 if not found.
        """
        k = (url, params_qty)
        return self.weights.get(k, 0)

    def update_weight(self, url: str, params_qty: int, new_weight: int) -> None:
        """
        Updates the weight for a given URL and parameters quantity in the weights file and in the weights variable.

        :param str url: The API endpoint URL.
        :param int params_qty: The number of parameters to update the weight for.
        :param int new_weight: The new weight to update the given URL and parameters quantity with.
        :return: This function does not return any value. It updates the weights file directly.
        """
        k = (url, params_qty)
        old_value = self.weights.get(k, 0)
        if old_value != new_weight:
            self._add_new_weight_to_file(url, params_qty, new_weight)
        self.weights[k] = new_weight

