import inspect
import os
import yaml
from contextlib import contextmanager, nested
from fabric.api import put, run, sudo as sudo_run, local, settings
from fabric.exceptions import NetworkError
from os.path import dirname, isabs, join, normpath


KIMPIRA_ROOT = os.environ.get('KIMPIRA_ROOT', os.getcwd())


def loc(path, orig_path=None):
    if isabs(path):
        return normpath(join(KIMPIRA_ROOT, path.lstrip('/')))
    if orig_path is None:
        orig_path = inspect.getouterframes(inspect.currentframe())[1][1]
    return normpath(join(dirname(orig_path), path))


def load_yaml(path):
    with open(path) as f:
        return yaml.load(f)


class ErrorResult(str):
    @property
    def return_code(self):
        return -1


@contextmanager
def _node(node_fname):
    node_info = load_yaml(node_fname)
    with settings(host_string=node_info.get('host')):
        acc = node_info.get('account')
        if acc:
            with _account(loc(acc, node_fname)):
                yield
        else:
            yield


@contextmanager
def _account(acc_fname):
    acc_info = load_yaml(acc_fname)
    key_filename = acc_info.get('keyfile')
    if key_filename:
        key_filename = loc(key_filename, acc_fname)
    with settings(user=acc_info.get('user'),
                  password=acc_info.get('password'),
                  key_filename=key_filename):
        yield


def _get_context(node=None, account=None, sudo=False, host=None, user=None, password=None):
    managers = []
    if node:
        managers.append(_node(node))
    if account:
        managers.append(_account(account))
    if host:
        managers.append(settings(host_string=host))
    if user:
        managers.append(settings(user=user))
    if password:
        managers.append(settings(password=password))
    return managers


def run_script(script_file, args, node, account=None, sudo=False, host=None, user=None, password=None):
    managers = _get_context(node, account, sudo, host, user, password)
    with nested(*managers):
        try:
            remote_path = run('mktemp')
            try:
                put(script_file, remote_path, mirror_local_mode=True)
                command = remote_path + ' ' + args
                if sudo:
                    return sudo_run(command)
                else:
                    return run(command)
            finally:
                run('rm %s' % remote_path)
        except NetworkError, e:
            return ErrorResult(e)


def run_command(command, node=None, account=None, sudo=False, host=None, user=None, password=None, warn_only=False):
    managers = _get_context(node, account, sudo, host, user, password)
    if warn_only:
        managers.append(settings(warn_only=True))
    with nested(*managers):
        if node or host:
            try:
                if sudo:
                    return sudo_run(command)
                else:
                    return run(command)
            except NetworkError, e:
                return ErrorResult(e)
        else:
            return local(command, capture=True)
