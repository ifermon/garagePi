

class Subscriber(object):
    """
        This class contains the data needed to interact with subscriber
        A subscriber is someone who can send and receive notifications regarding 
        the garage
    """
    def __init__(self, name, phone=None, ip=None):
        self._name = None
        self._phone = phone
        self._ip = ip
        return

    @property
    def name(self):
        return self._name

    @property
    def phone(self):
        return self._phone

    @phone.setter
    def phone(self, phone):
        self._phone = phone
        return

    @property
    def ip(self):
        return self._ip

    @ip.setter
    def ip(self, ip):
        self._ip = ip
        return

    def notify(self):
        pass


if __name__ == "__main__":
    print("Hello world")

    p = Subscriber("Ivan")
    print(p.__dict__)
    print(p.name)
    print(p.name)
    print(p.__dict__)
    print(p._name)

    print(p.phone)
    p.phone = "5551212"
    print(p.phone)
    print(p._phone)
