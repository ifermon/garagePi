class Event(object):

    def __init__(self, name, msg):
        self._name = name
        self._msg = msg
        return

    @property
    def name(self):
        return self._name

    @property
    def msg(self):
        return self._msg
