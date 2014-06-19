import inspect
import functools
import os
import re
import shlex
import sys
import time
import yaml
from Cheetah.Template import Template
from Cheetah.NameMapper import NotFound
from ordereddict import OrderedDict
from os.path import dirname, isabs, join, normpath
from .utils import loc, run_command, run_script
from .exceptions import TaskError, TaskFileError, ParseError


def represent_odict(dumper, instance):
    return dumper.represent_mapping(u'tag:yaml.org,2002:map', instance.items())
yaml.add_representer(OrderedDict, represent_odict)


def construct_odict(loader, node):
    return OrderedDict(loader.construct_pairs(node))
yaml.add_constructor(u'tag:yaml.org,2002:map', construct_odict)


def is_ident(ident):
    return re.match(r'[^\W0-9]\w*$', ident) is not None


class Task(object):
    def __init__(self, name, params, body, task_file):
        self._name = name
        self._task_file = task_file
        self._params = self._parse_params(params)
        self._body = self._parse_body(body)

    def __str__(self):
        return '{0}: {1}'.format(self._task_file, self._name)

    def _parse_params(self, params):
        _params = OrderedDict()
        for p in params:
            if not isinstance(p, basestring):
                raise TaskError(self, 'invalid parameter: {0}'.format(p))
            try:
                key, default = p.split('=', 2)
            except ValueError:
                key, default = p, None
            if not is_ident(key):
                raise TaskError(self, 'invalid parameter name: {0}'.format(key))
            _params[key] = default
        return _params

    def _parse_body(self, body):
        for b in body:
            if not isinstance(b, dict):
                raise TaskError(self, 'invalid task body: {0}'.format(b))
        return body

    @property
    def body(self):
        return self._body

    def call(self, args):
        dic = {}
        for i, k in enumerate(self._params):
            try:
                dic[k] = args[i]
            except IndexError:
                dic[k] = self._params[k]
        return dic


class TaskFile(object):
    def __init__(self):
        self._file_name = None
        self._tasks = OrderedDict()

    def __str__(self):
        return '{0}'.format(self._file_name)

    def load(self, file_name):
        self._file_name = file_name
        with open(self._file_name) as f:
            tasks = yaml.load(f)
        if isinstance(tasks, list):
            for task in tasks:
                self._register_task(task)
        elif isinstance(tasks, dict):
            self._register_task(tasks)
        else:
            raise TaskFileError(file_name)

    def _register_task(self, task):
        try:
            name = task['TASK']
        except KeyError:
            raise TaskFileError(self._file_name)

        params = task.get('PARAMS') or []
        if not isinstance(params, list):
            params = params.split()

        body = task.get('DO') or []
        if not isinstance(body, list):
            body = [body]

        self._tasks[name] = Task(name, params, body, self)
        
    def get_task(self, task_name=None):
        try:
            if task_name:
                return self._tasks[task_name]
            else:
                return self._tasks[self._tasks.keys()[0]]
        except KeyError:
            raise TaskFileError(self._file_name, 'no such task: {0}'.format(task_name))


class Environ(object):
    def __init__(self):
        self._frame_stack = []

    def push_frame(self, file_path, params=None):
        params = params or {}
        self._frame_stack.append((file_path, params, []))

    def pop_frame(self):
        self._frame_stack.pop()

    @property
    def current_task_file(self):
        return self._frame_stack[-1][0]

    @property
    def locals(self):
        return self._frame_stack[-1][1]

    @property
    def current_contexts(self):
        return self._frame_stack[-1][2]

    def push_context(self, **kwargs):
        self.current_contexts.append(kwargs)

    def pop_context(self):
        self.current_contexts.pop()

    def set_vars(self, **kwargs):
        for k, v in kwargs.items():
            saved = False
            for ctx in reversed(self.current_contexts):
                if k in ctx:
                    ctx[k] = v
                    saved = True
                    break
            if not saved:
                self.locals[k] = v

    @property
    def vars(self):
        dic = {}
        for _fp, _p, contexts in self._frame_stack[:-1]:
            for ctxt in contexts:
                dic.update(ctxt)
        dic.update(self.locals)
        for ctxt in self.current_contexts:
            dic.update(ctxt)
        return dic


class Return(Exception):
    def __init__(self, result):
        self.result = result


class Continue(Exception):
    pass


class Break(Exception):
    pass


class Runtime(object):
    def __init__(self):
        self._environ = Environ()

    def run(self, file_name, task_name=None, *args, **kwargs):
        task_file = TaskFile()
        task_file.load(file_name)
        return self._call(task_file, task_name, args)

    def get_var(self, k):
        return self._environ.vars(k)

    def _call(self, task_file, task_name, args):
        task = task_file.get_task(task_name)

        print """
***
*** execute TASK: {0}
***
""".format(task)

        self._environ.push_frame(task_file, task.call(args))
        try:
            return self._do(task.body)
        except Return, e:
            return e.result
        finally:
            self._environ.pop_frame()

    def _parse_args(self, args):
        if args is None:
            return
        if isinstance(args, list):
            return args
        if isinstance(args, basestring):
            return shlex.split(args)
        return [args]

    def _expand_path(self, path):
        if not isinstance(path, basestring):
            return path
        if path.startswith('@'):
            if path.startswith('@@'):
                return path[1:]
            return loc(path[1:], str(self._environ.current_task_file))
        return path

    def _args_to_kvs(self, args):
        kvs = {}
        for arg in args:
            try:
                key, val = arg.split('=', 2)
                kvs[key] = self._expand_path(val)
            except ValueError:
                raise RuntimeError('invalid argument: {0}'.format(arg))
        return kvs

    def _expand_vars(self, args):
        if isinstance(args, basestring):
            return str(Template(args, searchList=self._environ.vars))
        return args

    def _do(self, body):
        ret = None
        if not isinstance(body, list):
            body = [body]
        for op in body:
            try:
                opcode = op.keys()[0]
                args = self._parse_args(op[opcode])
                if args:
                    args = [self._expand_vars(arg) for arg in args]
            except NotFound, e:
                raise RuntimeError('invalid args: {0}'.format(e))
            try:
                if '.' in opcode:
                    mod_name, meth_name = opcode.rsplit('.', 1)
                    mod_name = 'kimpira.lib.' + mod_name
                    mod = __import__(mod_name, fromlist=[meth_name])
                    method = functools.partial(getattr(mod, meth_name), self)
                else:
                    method = getattr(self, '_do_' + opcode)
            except AttributeError:
                raise RuntimeError('invalid operation code: {0}'.format(opcode))
            ret = method(args, op)
            result = op.get('RESULT', 'RESULT')
            if not is_ident(result):
                raise RuntimeError('invalid result var name: {0}'.format(result))
            self._environ.set_vars(**{result: ret})
        return ret

    def _do_SET(self, args, op):
        self._environ.set_vars(**self._args_to_kvs(args))

    def _do_WITH(self, args, op):
        self._environ.push_context(**self._args_to_kvs(args))
        body = op.get('DO') or []
        try:
            return self._do(body)
        finally:
            self._environ.pop_context()

    def _do_DEFAULT(self, args, op):
        for k, v in self._args_to_kvs(args).items():
            if k not in self._environ.vars:
                self._environ.set_vars(**{k: v})

    def _do_PRINT(self, args, op):
        print ' '.join(self._expand_path(p) for p in args)

    def _do_CALL(self, args, op):
        task_name = args[0]
        args = [self._expand_path(p) for p in args[1:]]
        file_name = op.get('IN')
        if file_name:
            task_file = TaskFile()
            task_file.load(self._expand_path(file_name))
        else:
            task_file = self._environ.current_task_file
        return self._call(task_file, task_name, args)

    def _do_RETURN(self, args, op):
        if len(args) == 1:
            result = self._expand_path(args[0])
        else:
            result = [self._expand_path(p) for p in args]
        raise Return(result)

    def _do_COMMAND(self, args, op):
        node = self._environ.vars.get('NODE')
        account = self._environ.vars.get('ACCOUNT')
        sudo = self._environ.vars.get('SUDO')
        host = self._environ.vars.get('HOST')
        user = self._environ.vars.get('USER')
        password = self._environ.vars.get('PASSWORD')
        warn_only = op.get('WARN_ONLY')
        return run_command(' '.join(args), node, account, sudo, host, user, password, warn_only)

    def _do_SCRIPT(self, args, op):
        node = self._environ.vars.get('NODE')
        account = self._environ.vars.get('ACCOUNT')
        sudo = self._environ.vars.get('SUDO')
        host = self._environ.vars.get('HOST')
        user = self._environ.vars.get('USER')
        password = self._environ.vars.get('PASSWORD')
        if node or host:
            raise RuntimeError('failed to run script: NODE or HOST is not specified')
        script_file = self._expand_path(args[0])
        return run_script(script_file, ' '.join(args[1:]), node, account, sudo, host, user, password)

    def _do_SLEEP(self, args, op):
        t = int(args[0])
        time.sleep(t)

    def _do_IF(self, args, op):
        """
        - IF: <conditional expression>
          THEN: <operation>*

        or

        - IF: <conditional expression>
          THEN: <operation>*
          ELSE: <operation>
        """
        if args is not None:
            args = args[0]
        if args != 'False' and args:
            then_close = op.get('THEN') or []
            return self._do(then_close)
        else:
            else_close = op.get('ELSE') or []
            return self._do(else_close)
        
    def _do_REPEAT(self, args, op):
        """
        - REPEAT: <max repeat #>?
          DO: <operation>*
          UNTIL: <conditional expression>

        or

        - REPEAT: <max repeat #>?
          WHILE: <conditional expression>
          DO: <operation>*

        or

        - REPEAT: <max repeat #>?
          DO: <operation>*
        """
        max_repeat = None
        if args is not None:
            max_repeat = int(args[0])
        
        body = op.get('DO') or []
        result = None
        i = 0
        while max_repeat is None or i < max_repeat:
            while_cond = self._expand_vars(op.get('WHILE', True))
            if while_cond == 'False' or not while_cond:
                break
            result = self._do(body)
            until_cond = self._expand_vars(op.get('UNTIL'))
            if until_cond != 'False' and until_cond:
                break
            i += 1
        return result

    def _do_FOR(self, args, op):
        """
        - FOR: <ident>
          IN: <sequential expression>
          DO: <operation>*
        """
        loop_var = args[0]
        if not is_ident(loop_var):
            raise RuntimeError('invalid for loop var name: {0}'.format(loop_var))

        body = op.get('DO') or []
        result = None
        in_expr = self._parse_args(op.get('IN') or [])
        if len(in_expr) == 1 and in_expr[0].startswith('$') and is_ident(in_expr[0][1:]):
            in_expr = self._environ.vars[in_expr[0][1:]]
        else:
            in_expr = [self._expand_vars(v) for v in in_expr]
        for v in in_expr:
            self._environ.set_vars(**{loop_var: v})
            result = self._do(body)
        return result

    def _do_SAVE(self, args, op):
        to_file = self._expand_vars(op.get('TO'))
        if to_file:
            with open(self._expand_path(to_file), 'w') as f:
                f.write(args[0])
        return to_file

    def _do_ABORT(self, args, op):
        mesg = ''
        if args is not None:
            mesg = ' '.join(args)
        raise RuntimeError('ABORT: {0}'.format(mesg))

    def _do_DATA(self, args, op):
        return self.convert_data(op)

    def convert_data(self, data):
        def _conv_dict(dic):
            d = {}
            for k, v in dic.items():
                d[k] = self.convert_data(v)
            return d

        def _conv_list(lst):
            return [self.convert_data(v) for v in lst]

        if isinstance(data, dict):
            return _conv_dict(data)
        elif isinstance(data, list):
            return _conf_list(data)
        else:
            return self._expand_vars(data)
