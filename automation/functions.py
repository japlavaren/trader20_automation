import os
from decimal import Decimal
from typing import Any, Dict

import yaml


def load_config(file_name: str = None) -> Dict[str, Any]:
    file_name = file_name if file_name is not None else 'config.yaml'
    current_dir = os.path.dirname(os.path.realpath(__file__))
    config_file = os.path.join(current_dir, '../', file_name)

    with open(config_file) as h:
        config = yaml.safe_load(h)

    def to_decimal(values: Dict) -> None:
        for key, value in values.items():
            values[key] = Decimal(value)

    to_decimal(config['app']['spot']['trade_amount'])

    return config


def parse_decimal(value: str) -> Decimal:
    if '.' in value:
        value = value.rstrip('0')

    return Decimal(value)


def precision_round(num: Decimal, precision: int) -> Decimal:
    assert isinstance(num, Decimal)

    return round(num, precision)
