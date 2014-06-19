#!/usr/bin/env python
import optparse
import sys

from kimpira.core import Runtime
from kimpira.version import get_version


def parse_args():
    usage = "usage: %prog [options] <jobfile>"
    p = optparse.OptionParser(usage)
    p.add_option('-V', '--version', action='store_true', dest='show_version', default=False, help='show version number and exit')
    p.add_option('-t', '--task', dest='task_name', default=None, help='task name to run')
    return p.parse_args()


def main():
    options, args = parse_args()

    if options.show_version:
        print("Kimpira {0}".format(get_version()))
        sys.exit(0)

    if len(args) > 0:
        Runtime().run(args[0], options.task_name, *args[1:])


if __name__ == '__main__':
    main()
