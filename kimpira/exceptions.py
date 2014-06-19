class ParseError(Exception): pass


class TaskFileError(Exception):
    def __init__(self, task_file, mesg='invalid task file'):
        self.task_file = task_file
        self.mesg = mesg

    def __str__(self):
        return '{0}: {1}'.format(self.task_file, self.mesg)


class TaskError(Exception):
    def __init__(self, task, mesg):
        self.task = task
        self.mesg = mesg

    def __str__(self):
        return '{0}: {1}'.format(self.task, self.mesg)
