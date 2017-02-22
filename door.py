import garage_shared as GS
import multiprocessing as mp
import os
import time
import RPi.GPIO as GPIO
from threading import Timer
import logging
import const
import shelve
from event import Event

# Set up module logging
l = logging.getLogger(__name__)
l.setLevel(logging.DEBUG)


# noinspection PyProtectedMember
class Door(object):
    '''
        This module controls a garage door. It does the following:
            open - open the door
            close - close the door
            get_status - returns status of door opened or door closed
            sends change - sends a change in status message

            _OPENED is the status for garage door opened. Technically it means
            that the signal pin cooresponding to the reed switch for the door
            is an open circut, _CLOSED is the opposite.
    '''

    # Define class constants
    _OPENED = 0 # Value of pin state when door is opened (circut open)
    _CLOSED = 1 # Value of pin state when door is closed (circut closed)
    _OPEN_HIST_KEY = "Open"
    _CLOSE_HIST_KEY = "Close"
    _EVENT_NOTIFICATION_LIST_KEY = "Event notifications"
    _default_hist_count = 5
    _power_pin = 24
    _initial_wait_time = 300 # Time in secs before first nag msg is sent when door is left opened
    _repeat_wait_time = 1800 # Time in secs before repeat nag msg is sent
    _transition_wait_time = 30 # Time in secs to wait for door operation to complete (open/close)

    # Events support by class
    CLOSE_E = Event("Close Event")
    OPEN_E = Event("Open Event")
    TIMER_E = Event("Timer Event")
    DOOR_CLOSING_ERROR_E = Event("Door Closing Error Event")
    DOOR_OPENING_ERROR_E = Event("Door Opening Error Event")
    BUTTON_CLOSE_E = Event("Button Close Event")
    BUTTON_OPEN_E = Event("Button Open Event")

    @classmethod
    def supported_events(cls):
        '''
            Utility method to return a list of all valid events for class Door
        '''
        return [Door.CLOSE_E, Door.OPEN_E, Door.TIMER_E, Door.DOOR_CLOSING_ERROR_E,
                Door.DOOR_OPENING_ERROR_E, Door.BUTTON_CLOSE_E, Door.BUTTON_OPEN_E]


    @staticmethod
    def now_str():
        ''' Return string representation of right now'''
        return time.strftime("%a %b %d %Y @ %I:%M:%S %p")

    def get_state_str(self, state=None):
        '''
            Utility method to get string versions of state
            Default to value of current_state
            :param state:
            :return: Returns string value of state (Opened or Closed).
        '''
        if state is None:
            state = self.current_state
        if state == Door._OPENED:
            ret_str = "Opened"
        else:
            ret_str = "Closed"
        return ret_str

    def __str__(self):
        return self.name

    def set_log_level(self, log_level=logging.INFO):
        """ Set logging level for this door """
        self.log_level = log_level
        return

    @property
    def id(self):
        ''' persistent id for pickling event notifications'''
        return self._id

    def __init__(self, open_close_state_pin, push_button_pin, door_name,
            resource_lock):
        '''
            Initialize the door - set pins, set up logging, etc
            All pin numbering is in BCM mode
            open_close_state_pin: the pin on the PI that indicates if the door
              is closed or not closed (may be partially opened)
            push_putting_pin: the pin on the PI that triggers the door
            door_name: The name of this door. Used or messaging
            resource_lock: a shared RLock that prevents contention from
              multiple doors
        '''
        self.lock = resource_lock
        self.lock.acquire()

        # Setup logging just for this door
        self.l = logging.getLogger(door_name)
        self.l.setLevel(logging.DEBUG)

        # Set up basic instance vars
        self.name = door_name
        self.open_close_state_pin = open_close_state_pin
        self.push_button_pin = push_button_pin
        self.msg_timer = None
        self.door_last_opened = None
        self._id = str(type(self)) + self.name

        # Create the events with customized messages
        self.CLOSE_E = Door.CLOSE_E.localize("{}'s door was closed.".format(self.name))
        self.OPEN_E = Door.OPEN_E.localize("{}'s door was opened.".format(self.name))
        self.TIMER_E = Door.TIMER_E.localize("{}'s door is still opened.".format(self.name))
        self.DOOR_CLOSING_ERROR_E = Door.DOOR_CLOSING_ERROR_E.localize("Error closing {}'s door.".format(self.name))
        self.DOOR_OPENING_ERROR_E = Door.DOOR_OPENING_ERROR_E.localize("Error opening {}'s door.".format(self.name))
        self.BUTTON_CLOSE_E = Door.BUTTON_CLOSE_E.localize("Confirming {}'s door closed.".format(self.name))
        self.BUTTON_OPEN_E = Door.BUTTON_OPEN_E.localize("Confirming {}'s door opened.".format(self.name))

        # Load any existing history
        hist_file_name = const.door_hist_dir + "/.door_hist_" + self.name
        self.l.debug ("History file name: {}".format(hist_file_name))
        self.history = shelve.open(hist_file_name, writeback=True)
        if not self.history.has_key(Door._OPEN_HIST_KEY):
            self.history[Door._OPEN_HIST_KEY] = []
        if not self.history.has_key(Door._CLOSE_HIST_KEY):
            self.history[Door._CLOSE_HIST_KEY] = []

        # Load any previous preferences for subscriptions
        pref_file_name = const.door_pref_dir + "/.door_preferences_" + self.name
        self.l.debug ("Preference file name: {}".format(pref_file_name))
        self.preferences = shelve.open(pref_file_name, writeback=True)

        if self.preferences.has_key(Door._EVENT_NOTIFICATION_LIST_KEY):
            self.event_notification_list = self.preferences[Door._EVENT_NOTIFICATION_LIST_KEY]
            self.l.info("Preferences for {}'s door:".format(self.name))
            lstr = ""
            for e in self.event_notification_list:
                # noinspection PyProtectedMember
                lstr = "{}\n\t{}: {}".format(lstr, e.name)
            self.l.info(lstr)
        else:
            # If this is the first time then load empty notification lists
            self.event_notification_list = {}
            for e in Door.supported_events():
                l.debug("e is now {}".format(e))
                self.event_notification_list[e] = []
            self.preferences[Door._EVENT_NOTIFICATION_LIST_KEY] = self.event_notification_list
            self.preferences.sync()

        # Now set up the pins
        # Multiple processes are setting up pins, so supress warnings
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Settings for reed switch
        #GPIO.setup(self.open_close_state_pin, GPIO.IN, initial=GPIO.LOW,
        GPIO.setup(self.open_close_state_pin, GPIO.IN,
                pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(Door._power_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(Door._power_pin, True)

        # Settings for relay switch (door switch)
        GPIO.setup(self.push_button_pin, GPIO.OUT, initial=GPIO.HIGH)

        # Set a callback function, when it detects a change
        # this function will be called
        GPIO.add_event_detect(self.open_close_state_pin, GPIO.RISING,
                callback = self._door_moving_callback, bouncetime=2000)

        # Now get and set the current state of the door
        self.last_state = self.get_status()
        if self.last_state == Door._OPENED:
            self.l.info("Door already opened at startup")
            self.msg_timer = Timer(Door._initial_wait_time, self._quiet_time_over)
            self.msg_timer.start()
            self.door_last_opened = Door.now_str()

        self.l.info("\n\tName: {0}\n".format(door_name) +
                "\tProcess name: {0}\n".format(mp.current_process().name) +
                "\tParent PID: {0}\n".format(os.getppid()) +
                "\tPID: {0}\n".format(os.getpid()) +
                "\tPower pin: {0}\n".format(Door._power_pin) +
                "\tSignal pin: {0}\n".format(open_close_state_pin) +
                "\tSwitch pin: {0}\n".format(push_button_pin) +
                "\tCurrent state {0}\n".format(self.get_state_str()))

        self.lock.release()
        return

    def get_status(self):
        ''' Get and set the current state of the door (open/close) '''
        self.lock.acquire()
        self.current_state = GPIO.input(self.open_close_state_pin)
        self.lock.release()
        return self.current_state

    def snooze_timer(self, from_number, cmds):
        ''' Either cancel or snooze the timer'''
        self.l.debug("In snooze with these commands: {}".format(cmds))
        snooze_time = None

        # If there is a timer then cancel it
        if self.msg_timer is not None:
            self.msg_timer.cancel()

        # If # of minutes was specififed (cmds[1]) then set new timer with that delay
        try:
            snooze_time = cmds[1] # Did user give a time?
            int(snooze_time) # Is the argument an int?
        except IndexError:
            GS.send_message("Okay, {}'s door won't bother you again.", [from_number,])
            return # No snooze time specified, just return
        except ValueError:
            # Snooze time is not a number, I should send a msg back to user
            self.l.debug("Invalid snooze time: {}".format(snooze_time))
            GS.send_message("Snooze time ({}) must be a number.".format(snooze_time),
                            [from_number,])
            return

        # User specified sleep time - set a timer to check again
        self.msg_timer = Timer(snooze_time, self._quiet_time_over)
        self.msg_timer.start()
        GS.send_message("Okay, I'll remind you in {} minutes if {}'s door is still open".format(snooze_time, self.name),
                        [from_number,])
        return

    def press_button(self, from_number, cmds):
        ''' Press the door open/close switch '''
        self.lock.acquire()
        begin_state = self.get_status()
        self.l.info("Pushing button {0}'s door".format(self.name))
        GPIO.output(self.push_button_pin, GPIO.LOW)
        time.sleep(1)
        GPIO.output(self.push_button_pin, GPIO.HIGH)
        self.lock.release()

        time.sleep(Door._transition_wait_time)
        if begin_state == Door._CLOSED:
            if self.get_status() == Door._CLOSED:
                """ Failed at opening door, send message """
                self._send_msg(self.DOOR_OPENING_ERROR_E)
            else:
                self.l.info("{}'s door was closed, we opened it".format(self.name))
                self._send_msg(self.BUTTON_OPEN_E)
        elif begin_state == Door._OPENED:
            """ Let's confirm that the door was closed"""
            if self.get_status() != Door._CLOSED:
                self.l.error("{}'s door did not close as expected".format(self.name))
                self._send_msg(self.DOOR_CLOSING_ERROR_E)
            else: # Door closed as expected
                self.l.debug("{}'s door closed after pressing button".format(self.name))
                self._send_msg(self.BUTTON_CLOSE_E)
        else:
            self.l.error("Unknown error pushing button - door in unknown state")
        return

    def open(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already open
        '''
        if self.get_status() == Door._CLOSED:
            self.press_button()
        return

    def close(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already closed
        '''
        if self.get_status() == Door._OPENED:
            self.press_button()
        return

    def _door_moving_callback(self, channel):
        '''
            This function is called when the reed switch senses a change
            (i.e. door closes or opens). It's possible that it gets false
            alarms, so do a second check after waiting for the door to finish
            moving.
        '''
        self.lock.acquire()
        self.l.debug("Got a callback")
        # 20 secs should be enough time for the door to complete either
        # opening or closing, wait till it's done, this also helps us
        # avoid "floating" calls that may happen from time to time
        time.sleep(20)

        # Now see if the door state has changed
        self.get_status()
        if self.current_state != self.last_state:
            if self.current_state == Door._OPENED:
                self._door_opened()
                self.l.debug("In callback, door opened")
            else:
                self._door_closed()
                self.l.debug("In callback, door closed")
            self.last_state = self.current_state
        else:
            self.l.debug("In callback, nothing changed")

        self.lock.release()
        self.l.debug("Done processing callback")
        return

    def _door_opened(self):
        '''
            This function is called when the garage door is detected to have
            opened. Sends a text message and logs event
        '''
        self.l.info("Got door opened event")

        if self.msg_timer is not None:
            # This should never happen. We should have removed timer when closed
            self.l.error("Door opened and we already have msg_timer - error of some kind")
            self.msg_timer.cancel()
        else:
            # Record the time last opened if event is "new"
            self.door_last_opened = Door.now_str()
            self.history[Door._OPEN_HIST_KEY].insert(0, self.door_last_opened)
            self.history.sync()
            # Now send msg and set a msg timer so we don't send more messages
            self._send_msg(self.OPEN_E)

        # Set a timer so we don't bother with repeated messages
        self.msg_timer = Timer(Door._initial_wait_time, self._quiet_time_over)
        self.msg_timer.start()
        return

    def _quiet_time_over(self):
        ''' Clears the quiet time timer, checks to see if door is still opened, and sets another timer if it is '''
        # Clear the msg timer
        self.l.debug("Quiet time is over - send a message if door still open")
        self.msg_timer = None

        # Check to see if door is still opened, if so, set timer to check
        # again in 30 mins
        if self.get_status() == Door._OPENED:
            self._send_msg(self.TIMER_E)
            self.msg_timer = Timer(Door._repeat_wait_time, self._quiet_time_over)
            self.msg_timer.start()
        self.l.debug("Leaving quiet timer")
        return

    def _send_msg(self, event):
        ''' Sends a message via sms '''
        # REMOVE IF WORKING msg = self._get_event_msg(event_type)
        msg = event.msg
        self.l.debug("Sending message '{0}'".format(msg))
        GS.send_message(msg, self.event_notification_list[event_type])
        return

    def _door_closed(self):
        '''
            This function is called when the garage door is detected to have
            closed.
        '''
        self.l.info("Door closed")
        if self.msg_timer is None:
            self.l.error("Door closed and no open msg_timer - should not happen")
        else:
            self.msg_timer.cancel()
            self.history[Door._CLOSE_HIST_KEY].insert(0, Door.now_str())
            self.history.sync()
            self.msg_timer = None
        return

    def get_open_history(self, count):
        """ Return a string of the last n times door opened """
        if count is None: # calling arg will always send count
            count = Door._default_hist_count
        count = min(count, len(self.history[Door._OPEN_HIST_KEY]))
        str_list = ["{}'s door open history:".format(self.name),] + self.history[Door._OPEN_HIST_KEY][:count]
        ret_str = "\n  ".join(str_list)
        return ret_str

    def sub_event(self, event, phone_number):
        if phone_number not in self.event_notification_list[event]:
            self.event_notification_list[event].append(phone_number)
            self.preferences.sync()
        self.l.debug("Event notification list: {}".format(self.event_notification_list))
        return

    def unsub_event(self, event, phone_number):
        """ Remove phone number from notifications """
        if phone_number in self.event_notification_list[event]:
            self.event_notification_list[event].remove(phone_number)
            self.preferences.sync()
        self.l.debug("Event notification list: {}".format(self.event_notification_list))
        return

    def is_sub_event(self, event, phone_number):
        """ Return true if phone number is subscribed """
        return phone_number in self.event_notification_list[event]


if __name__ == "__main__":
    pass
