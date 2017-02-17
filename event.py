class Event(object):

    _event_groups = {}

    def __init__(self, name, msg, group_key="Default"):
        self._name = name
        self._msg = msg
        self._my_group = group_key 
        groups = Event._event_groups
        l = groups.get(group_key, [])
        groups[group_key] = l.append(self)
        print(Event._event_groups)
        return

    @property
    def name(self):
        return self._name

    @property
    def msg(self):
        return self._msg

    @classmethod
    def get_events(cls, key="Default"):
        return cls._event_groups.get(key, [])

    def __str__(self):
        return self._name
