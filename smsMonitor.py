from flask import Flask, request, redirect
import multiprocessing 
import sys
import os
import garageShared as GS
import plivo
import base64
import hmac
import hashlib
import shelve
import datetime
import myPlivo

	
###############################################################################
"""
	This class sets up a web server and waits for messages. They are sent
	from a service called twilio, they are sms messages. No messages are 
	processed here, only sent on to the main program.
"""
class SMS_Monitor(multiprocessing.Process):

	def __init__(self, queue, debug=True):
		super(SMS_Monitor, self).__init__(name="SMS_Monitor")
		self.queue = queue
		self.debug = debug
		return

	"""
	  This is a function that calcualtes the hash key for the plivo message
	  Essentially it ensures that the message is from plivo
	"""
	def validate_signature (uri, post_params, signature, auth_token):
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
		self.l = GS.configureLogger("GaragePiFlaskLogger")

		l = self.l
		log_name = "{0}|{1}".format(
				self.__class__.__name__, sys._getframe().f_code.co_name)
		l.info("{0}: Name <{1}> Parent <l{2}> PID <{3}>".format(log_name,
				multiprocessing.current_process().name, os.getppid(), 
				os.getpid()))

		app = Flask(__name__)

		"""
			This gets called when I receive a message (i.e. someone posts to my
			web server). Get the message and process it
		"""
		@app.route("/", methods=['GET', 'POST'])
		def get_message():
			# This is the uri used by plivo. The port translation is from 
			# the gateway. The ddns is by ddns.net
			uri = "http://ifermon.ddns.net:6000/"
			self.l.info("Got message on {0}\nmsg: \"{1}\"".format(uri, 
					request.values))

			# Validate the message
			if not request.headers.has_key('X-Plivo-Signature'):
				# This is very bad. It may mean that someone is trying to hack
				# the system. Shut it down.
				self.l.info("No plivo sig. Possible hack. Shutting down")
				GS.send_message("Shutting down system. Possible hack.")
				self.queue.put({"Msg:": "Shutting down"})
				sys.exit(1)

			signature = request.headers['X-Plivo-Signature']
			if not self.validate_signature(uri, request.form, signature, 
					myPlivo.auth_token):
				# This is very bad. It may mean that someone is trying to hack
				# the system. Shut it down.
				self.l.info("Invalid hash. Possible hack. Shutting down")
				GS.send_message("Shutting down system. Possible hack.")
				self.queue.put({"Msg:": "Shutting down"})
				sys.exit(1)

			# Signature is validated, now make sure it's not a duplicate
			# message
			uuid = str(request.form['MessageUUID'])
			if uuid_store.has_key(uuid):
				# This is very bad. It may mean that someone is trying to hack
				# the system. Shut it down.
				self.l.info("Duplicate msg. Possible hack. Shutting down")
				GS.send_message("Shutting down system. Possible hack.")
				self.queue.put({"Msg:": "Shutting down"})
				sys.exit(1)

			# Add the uuid to the message store
			uuid_store[uuid] = request.form + [datetime.datetime.now()]

			self.queue.put(request.values)
			self.l.info("Put msg into queue")
			return "Received"

		@app.route("/zane", methods=['GET'])
		def zane_open_door():
			self.l.info("Zane is requesting open door")
			self.queue.put({'Text':'h', 'From':'16509968841'})
			GS.send_message('Zane triggered door.')
			self.l.info("Put msg in queue to open Heather's door from Zane.")
			return "Received"

		uuid_store = shelve.open("./uuid_store")
		app.run(host='0.0.0.0', debug=self.debug)
		return



	#--------------------------------------------------------------------------
	#--------------------------------------------------------------------------
	"""
		Holder function for now
	"""
	def send_cmd(self, cmd):
		return "Got command <{0}>.".format(cmd)

