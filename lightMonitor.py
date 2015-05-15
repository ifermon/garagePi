import time
import smbus
import threading as thread
from threading import Timer
import datetime
import os
import sys
import garageShared as GS
import lightLevelLogging as LLL

_addr_default = 0x23
_trigger_value = 5
POLL_TIME = 5

ON = 1
OFF = 2
UNKNOWN = 3

class Light_Monitor(thread.Thread):
# -----------------------------------------------------------------------
# Some basic setup
# -----------------------------------------------------------------------
	def __init__(self, queue, addr=_addr_default):
		super(Light_Monitor, self).__init__()
		self.queue = queue
		self._addr = addr
		self.light_state = UNKNOWN
		self.keep_going = True
		self.bus = smbus.SMBus(1)
		self.light_left_on_timer = None

		# Added this for light level logging
		self.day_light_levels = None

		# we log light levels, but don't want too much
		self.log_counter = 0
		return

# -----------------------------------------------------------------------
# Shortcut to check on the current state, this doesn't check the sensor,
# it just checks what the last update was (on or off)
# -----------------------------------------------------------------------
	def get_light(self):
		return self.light_state
	
	def get_light_str(self):
		if self.get_light() == ON:
			ret_str = "On"
		elif self.get_light() == OFF:
			ret_str = "Off"
		else:
			ret_str = "Unknown"
		return ret_str

# -----------------------------------------------------------------------
# Set the light level and update the current state (on vs. off)
# -----------------------------------------------------------------------
	def check_light_level(self):
		state = self.light_state

		# Read the value of the light sensor
		data = self.bus.read_i2c_block_data(self._addr, 0x11)
		light_level = int((data[1] + (256 * data[0])) / 1.2)

		GS.lock.acquire()

		# First log the light level 
		if self.log_counter % 20 == 0:
			self.l.debug("Light level is: {0}".format(light_level))
		self.log_counter += 1

		if light_level > _trigger_value and self.light_state != ON:
			self.light_state = ON
			if GS.is_dark():
				self.light_left_on_timer = Timer(300, self.check_light_still_on)
		elif light_level < _trigger_value and self.light_state != OFF:
			if self.light_left_on_timer != None:
				self.light_left_on_timer.cancel()
				self.light_left_on_timer = None
			self.light_state = OFF
		GS.lock.release()
		return light_level

# -----------------------------------------------------------------------
# Monitor the light level. Change the status if the measurement (on vs.
# vs. off) is different that what is currently set
# Only operate at night
# -----------------------------------------------------------------------
	def run(self):
		
		# User the default logger
		self.l = GS.getLogger()
		l = self.l

		self.check_light_level()

		l.info("\n\tLight monitor:\n" +
				"\tProcess name: {0}\n".format(thread.current_thread().name) +
				"\tParent PID: {0}\n".format(os.getppid()) +
				"\tPID: {0}\n".format(os.getpid()) +
				"\tPoll time: {0}\n".format(POLL_TIME) +
				"\tTrigger value: {0}\n".format(_trigger_value) +
				"\tIs night: {0}\n".format(GS.is_dark()) +
				"\tLight is: {0}\n".format(self.get_light_str()))

		while self.keep_going:
			
			# Check to see if I should even be checking, sensor only
			# works when it's dark
			if not GS.is_dark():
				now = datetime.datetime.now(GS.my_tz())
				secs_till_sunset =  int((GS.sunset() - now).total_seconds())
				l.info("Sleeping till sunset at <{0}> for {1} seconds".	
						format(GS.sunset(), secs_till_sunset))
				# now I should just sleep till one hour afer sunset 
				time.sleep(secs_till_sunset + 3600)
				''' Removed may 15 2015 since weather is working
				# BEG OF NEW STUFF FOR LIGHT LEVEL
				now = datetime.datetime.now(GS.my_tz())
				# Should only happen the first time, create light level logger
				if self.day_light_levels == None:
					self.day_light_levels = LLL.DayLightValue(now)
				# Log a new value, sleep a minute, continue
				elif now.day == self.day_light_levels.day_no():
					self.day_light_levels.add_value(self.check_light_level())
					time.sleep(60)
				# New day, close old one, create new one
				elif now.day != self.day_light_levels.day_no():
					self.day_light_levels.close_day()
					self.day_light_levels = LLL.DayLightValue(now)
				continue
				# END OF NEW STUFF FOR LIGHT LEVEL
				'''

			# Set a 10pm check
			self.n10pm_timer = Timer(GS.secs_until_10pm(), self.n10pm_check)

			# Get the current light level
			self.check_light_level()

			# If we changed state then set timer and check again in 5 mins
			# If light was turned off then cancel the timer and change state
			time.sleep(POLL_TIME)
		return

	# It's 10pm, check to see if the lights are still on
	def n10pm_check(self):
		# Ensure that when we look for secs till 10pm it takes the next one
		time.sleep(5)
		GS.lock.acquire()
		if self.light_state == ON:
			GS.send_message("Garage light is on")
		self.n10pm_timer = Timer(GS.secs_until_10pm(), self.n10pm_check)
		self.l.info("10pm light check finsihed")
		return

	# Check to see if light is still on
	# This runs after timer expired, if light is on then send message
	def check_light_still_on(self):
		GS.lock.acquire()
		if light_level > _trigger_value and self.light_state != ON:
			GS.send_message("Garage light on.")
		self.light_left_on_timer = None
		return

	def stop(self):
		self.keep_going = False
		return

