from __future__ import absolute_import
import json


def load(runtime, args, op):
    return json.loads(args[0])

