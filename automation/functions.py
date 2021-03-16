import os
from decimal import Decimal
from typing import Any, Dict

import yaml


def _to_decimal(values: Dict) -> None:
    for key, value in values.items():
        values[key] = Decimal(value)


def load_config(file_name: str = None) -> Dict[str, Any]:
    file_name = file_name if file_name is not None else 'config.yaml'
    current_dir = os.path.dirname(os.path.realpath(__file__))
    config_file = os.path.join(current_dir, '../', file_name)

    with open(config_file) as h:
        config = yaml.safe_load(h)

    _to_decimal(config['app']['spot']['trade_amount'])

    return config
