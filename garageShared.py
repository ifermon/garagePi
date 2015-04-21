'''
	This is the parent class for all classes in this project
	Used to share objects that are common
'''
from dateutil import tz
import ephem
import plivo
import myPlivo
import logging
import sys
import datetime as dt

# Name for logger
loggerName = "GaragePi"

# Placeholder for lock
lock = None

# utility function for getting sunrise
def sunrise():
	utc_datetime = ephem.city('New York').next_rising(
			ephem.Sun()).datetime()
	utc_datetime = utc_datetime.replace(tzinfo=tz.gettz('UTC'))
	return utc_datetime.astimezone(my_tz())

# utility function for getting sunset
def sunset():
	utc_datetime = ephem.city('New York').next_setting(
			ephem.Sun()).datetime()
	utc_datetime = utc_datetime.replace(tzinfo=tz.gettz('UTC'))
	return utc_datetime.astimezone(my_tz())

# utility function for getting my timezone
def my_tz():
	return tz.gettz('America/New_York')

# utility function to see if it's dark
def is_dark():
	return (sunrise() < sunset())
	
# Utility function to send out an SMS message
def send_message(msg):
	# Your Account Sid and Auth Token from twilio.com/user/account
	account_id = myPlivo.auth_id
	auth_token  = myPlivo.auth_token
	# List of numbers to send message to
	number_list = ['+16509968841']
	client = plivo.RestAPI(account_id, auth_token)
	for n in number_list:
		params = { 'src': myPlivo.number, 
				'dst': n, 
				'text': msg, 
				'type': 'sms', }
		response = client.send_message(params)
	return


# Utility to configure a logger instance
def configureLogger(name=loggerName):
	l = logging.getLogger(name)
	l.setLevel(logging.DEBUG)
	fh = logging.FileHandler("{0}.log".format(name))
	fh.setLevel(logging.INFO)
	sh = logging.StreamHandler()
	sh.setLevel(logging.DEBUG)
	#formatter = logging.Formatter("%(asctime)s|%(name)s|" +
	#	"%(levelname)s|%(message)s")
	formatter = logging.Formatter("%(message)s |%(asctime)s|%(process)d" +
			"|%(thread)d|%(lineno)s|%(filename)s", "%y%m%d|%H%M%S")
	fh.setFormatter(formatter)
	sh.setFormatter(formatter)
	l.addHandler(fh)
	l.addHandler(sh)
	l.info("Initializing with python version <{0}>".format(
			sys.version))
	return l

# Return reference to logger by name
def getLogger(name=loggerName):
	return logging.getLogger(name)

# Utility function to get seconds until 10pm (time to wake and check door)
def secs_until_10pm():
	next_10pm = dt.datetime.today().replace(hour=22, minute=0, 
			second=0, microsecond=0)
	# if it's past 10pm now we need to get tomorrow's 10pm
	if dt.datetime.today().hour >= 22:
		next_10pm = next_10pm + dt.timedelta(days=1)

	# get the time difference between now and the next 10pm
	td = next_10pm - dt.datetime.today()
	return td.seconds
