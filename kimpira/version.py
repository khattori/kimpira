VERSION = (0, 0, 1, 'alpha', 0)

def get_version():
    main = '.'.join(str(x) for x in VERSION[:3])
    sub = ''
    if VERSION[3] != 'final':
        mapping = {'alpha': 'a', 'beta': 'b', 'rc': 'c'}
        sub = mapping[VERSION[3]] + str(VERSION[4])
    return main + sub
