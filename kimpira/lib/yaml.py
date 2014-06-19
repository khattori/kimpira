from __future__ import absolute_import
import yaml


def load(runtime, args, op):
    with open(args[0]) as f:
        return yaml.load(f)
