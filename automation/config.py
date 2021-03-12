import os

import yaml

automation_dir = os.path.dirname(os.path.realpath(__file__))
config_file = os.path.join(automation_dir, '../config.yaml')

with open(config_file) as h:
    config = yaml.safe_load(h)
