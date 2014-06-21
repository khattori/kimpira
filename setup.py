#!/usr/bin/env python
import sys
from setuptools import setup, find_packages
from kimpira.version import get_version


min_python = (2, 6)
if sys.version_info < min_python:
    print "Kimpira requries Python %d.%d or later" % min_python
    sys.exit(1)
if sys.version_info >= (3,):
    print "Kimpira does not support Python 3 (yet)"
    sys.exit(1)


setup(
    name='Kimpira',
    version=get_version(),
    packages=find_packages(),
    install_requires=[
        "Cheetah==2.4.4",
        "Fabric==1.8.3",
        "PyYAML==3.11",
        "requests==2.3.0"
    ],
    entry_points={
        'console_scripts': [
            'kimpira = kimpira.main:main',
        ]
    },
)

