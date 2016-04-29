'''
	This is the parent class for all classes in this project
	Used to share objects that are common
'''
from dateutil import tz
import ephem
import plivo
import const
import logging
import sys
import datetime as dt

# Name for logger
loggerName = "GaragePi"
LOG_DIR = "/home/garage/garagePi/logs/"

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
def send_message(msg, number_list=['+16509968841']):
	# Your Account Sid and Auth Token from plivo.com/user/account
	account_id = const.auth_id
	auth_token  = const.auth_token
	# List of numbers to send message to
	client = plivo.RestAPI(account_id, auth_token)
	for n in number_list:
		params = { 'src': const.number, 
				'dst': n, 
				'text': msg, 
				'type': 'sms', }
		response = client.send_message(params)
	return


# Utility to configure a logger instance
def configure_logging()
	l = logging.getLogger()
	l.setLevel(logging.INFO)
	fh = logging.FileHandler("{0}{1}.log".format(LOG_DIR, name))
	fh.setLevel(logging.INFO)
	sh = logging.StreamHandler()
	sh.setLevel(logging.DEBUG)
	formatter = logging.Formatter(datefmt="%a %y%m%d%z %H%M%S",
			format="%(asctime)-22s %(levelname)-8s%(name)-8s %(message)s [%(filename)s@%(lineno)s]")
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
