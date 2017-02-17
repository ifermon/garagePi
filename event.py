class Event(object):

    _event_groups = {}

    def __init__(self, name, msg, group_key="Default"):
        self._name = name
        self._msg = msg
        self._my_group = group_key 
        groups = Event._event_groups
        groups[group_key] = groups.get(group_key, []) + [self,]
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


if __name__ == "__main__":

    grp = "a group"
    a = Event("a", "a msg", grp)
    b = Event("b", "b msg")
    c = Event("c", "c msg", grp)

    print(c.__dict__)
