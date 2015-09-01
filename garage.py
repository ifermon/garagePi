'''
	This is the master base class for the garage project
	It is used to pass around shared objects
	These are class level references, not instance level
	All objects referenced here must be thread / multi process safe
'''
from multiprocessing import RLock, Queue
from Queue import Empty
import garageShared as GS
from door import Door
from sets import Set
import time
import smsMonitor as sms
import lightMonitor
import sys

def ret_status():
	s1 = "Ivan's door is {0}.".format(ivan_door.get_state_str().lower())
	s2 = "Heather's door is {0}.".format(heather_door.get_state_str().lower())
	if GS.is_dark() == True: # i.e. it's night time
		s3 = "The light is {0}.".format(light_monitor.get_light_str().lower())
	else:
		s3 = "It's daytime so light state is unknown."
	GS.send_message("{0}\n{1}\n{2}".format(s1, s2, s3))
	return
	

if __name__ == "__main__":

	# get things set up
	keep_alive = True
	l = GS.configureLogger(GS.loggerName)
	l.info("Just configured logger")
	GS.lock = RLock()
	q = Queue()
	ivan_door = Door(23,18,"Ivan")
	heather_door = Door(17, 22, "Heather")

	# Start the flask server so we can receive SMS messages
	sms_listener = sms.SMS_Monitor(q, debug=False)
	sms_listener.daemon = True
	sms_listener.start()
	time.sleep(5)

	# Start the light monitor
	light_monitor = lightMonitor.Light_Monitor(q)
	light_monitor.daemon = True
	light_monitor.start()
	time.sleep(5)
	

	# This is our function map. Based on the type of message (which is just
	# the name of a class), call an associated function
	f_map = {'DoorOpened': Door.door_opened,
			'DoorClosed': Door.door_closed,
			'status': ret_status,
			's': ret_status,
			'i': ivan_door.press_button,
			'h': heather_door.press_button}
	# Number map just gives a list of valid numbers for the from
	valid_numbers = Set(['16509968841', '5184787802'])

	# Send myself a message that we are starting up
	#GS.send_message("Starting up garagePi")
	# Removed sep 1 2015 - moved to startup script so that I can ignore
	# msg during nightly reboots

	# everything is set up, now wait for messages and process them as needed
	while keep_alive:
		# wait until we get a message
		#l.info("Waiting for message")
		try:
			msg = q.get(True, 10)
			l.debug ("Recevied message <{0}>.".format(msg))
		except Empty:
			#l.info("Queue get timed out after waiting for a day")
			continue

		# We might be asked to shut down (e.g. in case of attempted hack)
		if not msg.has_key('From'):
			l.info("Invalid message <{0}>".format(msg))
			sys.exit(1)

		# check to see if message came from allowed number
		if msg['From'] not in valid_numbers:
			l.info("Got command from invalid number")
			GS.send_message("Got msg from invalid number {0}".format(
					msg['From']))
			continue

		# now process the message
		msg_func = f_map.get(msg['Text'].lower(), None)
		if msg_func is not None:
			msg_func()
		else:
			GS.send_message("I don't know that command. Sorry.")
			l.info("Unknown msg <{0}>".format(msg))
	
