


class Subscriber(object):
    """
        This modudule contains the data needed to interact with subscriber 
        A subscriber is someone who can send and receive notifications regarding 
        the garage
    """


    def __init__(self, name, phone, ip):
        self.name = name
        self.phone = phone
        self.ip = ip
        return

    def get_name(self):
        return self.name

    def get_phone(self):
        return self.phone

    def get_ip(self):
        return self.ip
