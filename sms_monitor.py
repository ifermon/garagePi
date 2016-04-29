from flask import Flask, request, redirect
import multiprocessing as MP
import sys
import os
import garage_shared as GS
import plivo
import base64
import hmac
import hashlib
import shelve
import datetime
import const

LOG_DIR="/home/garage/garagePi/logs/"
    
###############################################################################
"""
    This class sets up a web server and waits for messages. They are sent
    from a service called twilio, they are sms messages. No messages are 
    processed here, only sent on to the main program.
"""
class SMS_Monitor(MP.Process):

    def __init__(self, queue, debug=True):
        super(SMS_Monitor, self).__init__(name="SMS_Monitor")
        self.queue = queue
        self.debug = debug

        #self.l = GS.configureLogger("GaragePiFlaskLogger")
        self.l = GS.getLogger()
        self.l.info("Just configured logger")

        return

    """
      This is a function that calcualtes the hash key for the plivo message
      Essentially it ensures that the message is from plivo
    """
    def validate_signature (self, uri, post_params, signature, auth_token):
        for k, v in sorted(post_params.items()):
            uri += k + v
        s = base64.encodestring(hmac.new(auth_token, uri, 
                hashlib.sha1).digest()).strip()
        return s == signature


    #--------------------------------------------------------------------------
    #--------------------------------------------------------------------------
    """
        This is the main logic for this object. It sits and waits for someone
        to post (this would be twilio). When it posts, it's a SMS message. 
        Read the message and send to main process
    """
    def run(self):

        l = self.l
        log_name = "{0}|{1}".format(
                self.__class__.__name__, sys._getframe().f_code.co_name)
        l.info("{0}: Name <{1}> Parent <l{2}> PID <{3}>".format(log_name,
                MP.current_process().name, os.getppid(), 
                os.getpid()))

        app = Flask(__name__)

        """
            This gets called when I receive a message (i.e. someone posts to my
            web server). Get the message and process it
        """
        @app.route("/", methods=['GET', 'POST'])
        def get_message():
            try:
                # This is the uri used by plivo. The port translation is from 
                # the gateway. The ddns is by ddns.net
                uri = "https://ifermon.ddns.net:6000/"
                self.l.info("Got message on {0}\nmsg: \"{1}\"".format(uri, 
                        request.values))

                # Validate the message
                self.l.debug("Checking plivo signature exists")
                if not request.headers.has_key('X-Plivo-Signature'):
                    # This is very bad. It may mean that someone is trying to hack
                    # the system. Shut it down.
                    self.l.error("No plivo sig. Possible hack. Shutting down")
                    GS.send_message("Shutting down system. Possible hack.")
                    self.queue.put({"Msg:": "Shutting down"})
                    self.terminate()

                signature = request.headers['X-Plivo-Signature']
                self.l.debug("Checking signature hash is valid")
                if not self.validate_signature(uri, request.form, signature, 
                        const.auth_token):
                    # This is very bad. It may mean that someone is trying to hack
                    # the system. Shut it down.
                    self.l.error("Invalid hash. Possible hack. Shutting down")
                    GS.send_message("Shutting down system. Possible hack.")
                    self.queue.put({"Msg:": "Shutting down"})
                    self.terminate()

                # Signature is validated, now make sure it's not a duplicate
                # message
                self.l.debug("Checking the message is not a duplicate")
                uuid = str(request.form['MessageUUID'])
                if uuid_store.has_key(uuid):
                    # This is very bad. It may mean that someone is trying to hack
                    # the system. Shut it down.
                    self.l.info("Duplicate msg. Possible hack. Shutting down")
                    GS.send_message("Shutting down system. Possible hack.")
                    self.queue.put({"Msg:": "Shutting down"})
                    self.terminate()

                # Add the uuid to the message store
                self.l.debug("Adding to msg id list")
                d = dict(request.form).update({'Datestamp':datetime.datetime.now()})
                uuid_store[uuid] = d

                self.l.debug("Putting message into queue")
                self.queue.put_nowait(request.values)
                self.l.info("Put msg into queue")
            except Exception as e:
                self.l.error("Some kind of error")
                self.l.error(e)
            return "Received"

        '''
            The irony with all the security in the above function is this
            wide open security hole. At least it texts me when used.
        '''
        @app.route("/zane", methods=['GET'])
        def zane_open_door():
            self.l.info("Zane is requesting open door")
            self.queue.put({'Text':'h', 'From':'16509968841'})
            GS.send_message('Zane triggered door.')
            self.l.info("Put msg in queue to open Heather's door from Zane.")
            return "Received"

        '''
            Send text - using to monitor up time of other devices
        '''
        @app.route("/send_message", methods=['GET', 'POST'])
        def send_msg():
            self.l.info("Got msg: {0}".format(request.args))
            if request.args.has_key('msg'):
                msg = request.args['msg']
                GS.send_message(msg)
            return "Received"

        # Very bad style hard-coding this. Some day I'll fix it
        uuid_store = shelve.open("{0}{1}".format(LOG_DIR, "uuid_store"))
        app.run(host='0.0.0.0', debug=self.debug, ssl_context='adhoc')
        return



    #--------------------------------------------------------------------------
    #--------------------------------------------------------------------------
    """
        Holder function for now
    """
    def send_cmd(self, cmd):
        return "Got command <{0}>.".format(cmd)


if __name__ == "__main__":
    mon = SMS_Monitor(MP.Queue())
    mon.daemon = False
    mon.start()
