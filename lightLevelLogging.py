'''
	We want to take light level measurements every 60 seconds
	We want to average the light levels together to create an hourly average
	We want to log the hourly average
	We want to log the minute average
	We want to create a daily average incl nighttime hours
	We want a daily count of minutes with sun (first light - last light)
	We want to log the daily average and the daily count of minutes
'''

from __future__ import print_function
import datetime
import pytz
import ephem

eastern = pytz.timezone('US/Eastern')
utc = pytz.timezone('UTC')

# ----------------------------------------------------------------------------
# This class manages readings over an hour
# ----------------------------------------------------------------------------
class HourLightValue(object):

	def __init__(self, hour_datetime, log_file_pointer):
		self.lp = log_file_pointer
		self.hour_dt = hour_datetime
		self.count = 0
		self.total = 0
		self.avg = 0.0
		self.readings = []
		self.closed = False
		return

	def add_value(self, light_level):
		self.count += 1
		self.total += light_level
		self.avg = self.total / self.count
		msg = "minute,{0},{1}".format(
			datetime.datetime.now(eastern),
			light_level)
		print (msg, file=self.lp)
		self.readings.append(msg)
		return

	def get_avg(self):
		return self.avg

	def get_count(self):
		return self.count

	def close_hour(self):
		if self.closed == False:
			msg = "hour,{0},{1}".format(
					self.hour_dt, self.avg)
			print(msg, file=self.lp)
			self.closed = True
		return
	
	def is_closed(self):
		return self.closed

# ----------------------------------------------------------------------------
# This class manages readings over a day
# We are using daily log files, logic hard coded into this class
# ----------------------------------------------------------------------------
class DayLightValue(object):
	
	def __init__(self, dt, log_file_name=None, log_file_dir=None):
		self.day = datetime.date(dt.year, dt.month, dt.day)

		if log_file_name == None:
			log_file_name = "LightLevelReadings-{0}.csv".format(
					dt.strftime("%Y-%m-%d"))
		if log_file_dir == None:
			log_file_dir = "./"
		log_file_name = "{0}{1}".format(log_file_dir, log_file_name)
		self.lp = open(log_file_name, "a", 0)
		self.closed = False
		self.sunset = ephem.city('New York').next_setting(ephem.Sun(), 
				start=self.day).datetime().replace(
				tzinfo=utc).astimezone(eastern)
		self.sunrise = ephem.city('New York').next_rising(ephem.Sun(), 
				start=self.day).datetime().replace(
				tzinfo=utc).astimezone(eastern)
		self.mins_of_daylight = None
		self.hour_values = []
		for h in range(24):
			hdt = datetime.datetime(dt.year, dt.month, dt.day, h)
			self.hour_values.append(HourLightValue(hdt, self.lp))
		return

	'''
		This function adds a light level value, which should be minute
		readings.
		Only add values if it is daytime
	'''
	def add_value(self, light_level):
		dt = datetime.datetime.now(eastern)
		if dt > self.sunrise and dt < self.sunset:
			self.hour_values[dt.hour].add_value(light_level)
		return

	def get_avg(self):
		total_ll = 0
		total_count = 0
		for ll in self.hour_values:
			total_ll += (ll.get_avg() * ll.get_count())
			total_count += ll.get_count()
		return total_ll / total_count

	def close_day(self):
		if self.is_closed() == False:
			dt = datetime.datetime.now(eastern)
			if self.hour_values[dt.hour].is_closed() == False:
				self.hour_values[dt.hour].close_hour()
			msg = "day,{0},{1}".format(
					self.day, self.get_avg())
			print(msg, file=self.lp)
			self.lp.close()
			self.closed = True
		return

	def is_closed(self):
		return self.closed

	def day_no(self):
		return self.day.day
		

