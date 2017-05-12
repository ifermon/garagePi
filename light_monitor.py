import time
import smbus
import threading as thread
from threading import Timer
import datetime
import os
import garage_shared as GS
import logging
import shelve
import const

_addr_default = 0x23
_trigger_value = 5
POLL_TIME = 5
# Default timer time (in seconds = 7 minutes)
TIMER_INTERVAL = 420

ON = 1
OFF = 2
UNKNOWN = 3


# Events
ON_E = "Light on event"
OFF_E = "Light off event"
TIMER_E = "Timer event"

class Light_Monitor(thread.Thread):
    def __init__(self, queue, addr=_addr_default):
        """ 
         Some basic setup
        """
        super(Light_Monitor, self).__init__()
        self.queue = queue
        self._addr = addr
        self.light_state = UNKNOWN
        self.keep_going = True
        self.bus = smbus.SMBus(1)
        self.light_left_on_timer = None
        self.l = logging.getLogger(__name__)
        #self.l.setLevel(logging.DEBUG)

        # Get preferences
        pref_file_name = const.light_pref_file
        self.l.debug("Preference file name: {}".format(pref_file_name))
        self.notification_list = shelve.open(pref_file_name, writeback=True)

        if ON_E not in self.notification_list:
            e = [ON_E, OFF_E, TIMER_E]
            for k in e:
                self.notification_list[k] = []
        else:
            self.l.info("Light notification prefs: {}".format(
                    self.notification_list))
        return

    def get_light(self):
        """ 
         Shortcut to check on the current state, this doesn't check the sensor,
         it just checks what the last update was (on or off)
        """
        return self.light_state
    
    def get_light_str(self):
        if self.get_light() == ON:
            ret_str = "On"
        elif self.get_light() == OFF:
            ret_str = "Off"
        else:
            ret_str = "Unknown"
        return ret_str

    def get_light_state(self):
        """ 
            Set the light level and update the current state (on vs. off)
        """

        GS.lock.acquire()
        state = self.light_state

        # Read the value of the light sensor
        data = self.bus.read_i2c_block_data(self._addr, 0x11)
        light_level = int((data[1] + (256 * data[0])) / 1.2)

        if light_level > _trigger_value:
            self.light_state = ON
        else:
            self.light_state = OFF

        GS.lock.release()
        return self.light_state

    def run(self):
        """ 
         Monitor the light level. Change the status if the measurement (on vs.
         vs. off) is different that what is currently set
         Only operate at night
        """

        self.get_light_state()

        self.l.info("\n\tLight monitor:\n" +
                "\tProcess name: {0}\n".format(thread.current_thread().name) +
                "\tParent PID: {0}\n".format(os.getppid()) +
                "\tPID: {0}\n".format(os.getpid()) +
                "\tPoll time: {0}\n".format(POLL_TIME) +
                "\tTrigger value: {0}\n".format(_trigger_value) +
                "\tIs night: {0}\n".format(GS.is_dark()) +
                "\tLight is: {0}\n".format(self.get_light_str()))

        log_skip_count = 0

        while self.keep_going:
            # Check to see if I should even be checking, sensor only
            # works when it's dark
            if not GS.is_dark():
                now = datetime.datetime.now(GS.my_tz())
                secs_till_sunset =  int((GS.sunset() - now).total_seconds())
                self.l.info("Sleeping till sunset at <{0}> for {1} seconds".
                        format(GS.sunset(), secs_till_sunset))
                # now I should just sleep till one hour afer sunset 
                time.sleep(secs_till_sunset + 3600)

            # Store the "current" as the last state, check the new state
            old_light_state = self.light_state
            if self.get_light_state() == ON and old_light_state == OFF:
                # Light just turned on
                self.l.debug("Light turned on (was off).")
                self.light_left_on_timer = Timer(TIMER_INTERVAL, 
                        self.check_light_still_on)
                self.light_left_on_timer.start()

            # Just log once in a while to know we are alive
            if log_skip_count % 60 == 0:
                self.l.debug("Going to sleep for {} seconds.".format(POLL_TIME))
            log_skip_count += 1
            time.sleep(POLL_TIME)
        return

    def check_light_still_on(self):
        """
            Check to see if light is still on
            This runs after timer expired, if light is on then send message
        """
        GS.lock.acquire()
        self.light_left_on_timer = None
        if self.get_light_state() == ON and GS.is_dark():
            self.l.debug("Sending light message")
            GS.send_message("Garage light left on.")
            self.light_left_on_timer = Timer(TIMER_INTERVAL, 
                    self.check_light_still_on)
            self.light_left_on_timer.start()
        GS.lock.release()
        return

    def stop(self):
        self.keep_going = False
        return

