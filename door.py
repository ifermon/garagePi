import garage_shared as GS
import multiprocessing as mp
import os
import time
import RPi.GPIO as GPIO
from threading import Timer
import logging
import const
import plivo
import shelve

# Define constants
OPENED = 0 # Value of pin state when door is opened (circut open)
CLOSED = 1 # Value of pin state when door is closed (circut closed)
POWER_PIN = 24
INITIAL_WAIT_TIME = 300 # Time in secs before first nag msg is sent when door is left opened
REPEAT_WAIT_TIME = 1800 # Time in secs before repeat nag msg is sent
TRANSITION_WAIT_TIME = 30 # Time in secs to wait for door operation to complete (open/close)
OPEN_HIST_KEY = "Open"
CLOSE_HIST_KEY = "Close"
DEFAULT_HIST_COUNT = 5

# Events used for sending messages / publishing messages
# Event values are also designed to be the message text - I know this is horrible but it's easy
CLOSE_E = "{}'s door was closed on {}."
OPEN_E = "{}'s door was opened on {}."
TIMER_E = "{}'s door is still opened at {}."
DOOR_CLOSING_ERROR_E = "Error closing {}'s door on {}."
DOOR_OPENING_ERROR_E = "Error opening {}'s door on {}."
BUTTON_CLOSE_E = "Confirming {}'s door closed."
BUTTON_OPEN_E = "Confirming {}'s door opened."

class Door(object):
    '''
        This module controls a garage door. It does the following:
            open - open the door
            close - close the door
            get_status - returns status of door opened or door closed
            sends change - sends a change in status message

            OPENED is the status for garage door opened. Technically it means
            that the signal pin cooresponding to the reed switch for the door
            is an open circut, CLOSED is the opposite.
    '''

    def get_event_name(self, event):
        if event == CLOSE_E:
            ret_str = "Close Event"
        elif event == OPEN_E:
            ret_str = "Open Event"
        elif event == TIMER_E:
            ret_str = "Timer Event"
        elif event == DOOR_CLOSING_ERROR_E:
            ret_str = "Door Closing Error Event"
        elif event == DOOR_OPENING_ERROR_E:
            ret_str = "Door Opening Error Event"
        elif event == BUTTON_CLOSE_E:
            ret_str = "Button Close Event"
        elif event == BUTTON_OPEN_E:
            ret_str = "Button Open Event"
        else:
            ret_str = event
        return ret_str
    
    def get_state_str(self, state=None):
        '''
            Utility method to get string versions of state
            Default to value of current_state
            :param state:
            :return: Returns string value of state (Opened or Closed).
        '''
        if state == None:
            state = self.current_state
        if state == OPENED:
            ret_str = "Opened"
        else:
            ret_str = "Closed"
        return ret_str

    def __str__(self):
        return self.name

    def set_log_level(log_level=logging.INFO):
        """ Set logging level for this door """
        self.log_level = log_level
        return

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

        # access the logger and set up logging
        self.name = door_name
        self.open_close_state_pin = open_close_state_pin
        self.push_button_pin = push_button_pin
        self.msg_timer = None
        self.door_last_opened = None

        # Load any previous preferences for subscriptions
        pref_file_name = const.door_pref_dir + "/.door_preferences_" + self.name
        self.l.debug ("Preference file name: {}".format(pref_file_name))
        self.event_notification_list = shelve.open(pref_file_name, 
                writeback=True)

        # Load any existing history
        hist_file_name = const.door_hist_dir + "/.door_hist_" + self.name
        self.l.debug ("History file name: {}".format(hist_file_name))
        self.history = shelve.open(hist_file_name, writeback=True)
        if not self.history.has_key(OPEN_HIST_KEY):
            self.history[OPEN_HIST_KEY] = []
        if not self.history.has_key(CLOSE_HIST_KEY):
            self.history[CLOSE_HIST_KEY] = []

        # If this is the first time then load empty notification lists
        if CLOSE_E not in self.event_notification_list:
            e = [CLOSE_E, OPEN_E, TIMER_E, BUTTON_OPEN_E, BUTTON_CLOSE_E,
                    DOOR_OPENING_ERROR_E, DOOR_CLOSING_ERROR_E]
            for k in e:
                self.event_notification_list[k] = []
        else: # Log the loaded preferences
            self.l.info("Preferences for {}'s door:".format(self.name))
            lstr = ""
            for k, v in self.event_notification_list.iteritems():
                lstr = "{}\n\t{}: {}".format(lstr, self.get_event_name(k), v)
            self.l.info(lstr)

        # Now set up the pins
        # Multiple processes are setting up pins, so supress warnings
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Settings for reed switch
        #GPIO.setup(self.open_close_state_pin, GPIO.IN, initial=GPIO.LOW,
        GPIO.setup(self.open_close_state_pin, GPIO.IN, 
                pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(POWER_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(POWER_PIN, True)

        # Settings for relay switch (door switch)
        GPIO.setup(self.push_button_pin, GPIO.OUT, initial=GPIO.HIGH)

        # Set a callback function, when it detects a change
        # this function will be called
        GPIO.add_event_detect(self.open_close_state_pin, GPIO.RISING,
                callback = self._door_moving_callback, bouncetime=2000)

        # Now get and set the current state of the door
        self.last_state = self.get_status()
        if self.last_state == OPENED:
            self.l.info("Door already opened at startup")
            self.msg_timer = Timer(INITIAL_WAIT_TIME, self._quiet_time_over)
            self.msg_timer.start()
            self.door_last_opened = time.ctime()

        self.l.info("\n\tName: {0}\n".format(door_name) +
                "\tProcess name: {0}\n".format(mp.current_process().name) +
                "\tParent PID: {0}\n".format(os.getppid()) +
                "\tPID: {0}\n".format(os.getpid()) +
                "\tPower pin: {0}\n".format(POWER_PIN) +
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

        time.sleep(TRANSITION_WAIT_TIME)
        if begin_state == CLOSED:
            if self.get_status() == CLOSED:
                """ Failed at opening door, send message """
                self._send_msg(DOOR_OPENING_ERROR_E)
            else:
                self.l.info("{}'s door was closed, we opened it".format(self.name))
                self._send_msg(BUTTON_OPEN_E)
        elif begin_state == OPENED:
            """ Let's confirm that the door was closed"""
            if self.get_status() != CLOSED:
                self.l.error("{}'s door did not close as expected".format(self.name))
                self._send_msg(DOOR_CLOSING_ERROR_E)
            else: # Door closed as expected
                self.l.debug("{}'s door closed after pressing button".format(self.name))
                self._send_msg(BUTTON_CLOSE_E)
        else:
            self.l.err("Unknown error pushing button - door in unknown state")
        return

    def open(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already open
        '''
        if self.get_status() == CLOSED:
            self.press_button()
        return

    def close(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already closed
        '''
        if self.get_status() == OPENED:
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
            if self.current_state == OPENED:
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
        
        if self.msg_timer != None:
            # This should never happen. We should have removed timer when closed
            self.l.error("Door opened and we already have msg_timer - error of some kind")
            self.msg_timer.cancel()
        else:
            # Record the time last opened if event is "new"
            self.door_last_opened = time.ctime()
            self.history[OPEN_HIST_KEY].insert(0, self.door_last_opened)
            self.history.sync()
            # Now send msg and set a msg timer so we don't send more messages
            self._send_msg(OPEN_E)

        # Set a timer so we don't bother with repeated messages
        self.msg_timer = Timer(INITIAL_WAIT_TIME, self._quiet_time_over)
        self.msg_timer.start()
        return

    def _quiet_time_over(self):
        ''' Clears the quiet time timer, checks to see if door is still opened, and sets another timer if it is '''
        # Clear the msg timer
        self.l.debug("Quiet time is over - send a message if door still open")
        self.msg_timer = None

        # Check to see if door is still opened, if so, set timer to check
        # again in 30 mins
        if self.get_status() == OPENED:
            self._send_msg(TIMER_E)
            self.msg_timer = Timer(REPEAT_WAIT_TIME, self._quiet_time_over)
            self.msg_timer.start()
        self.l.debug("Leaving quiet timer")
        return

    def _get_event_msg(self, event_type):
        now = time.ctime(time.time())
        if self.door_last_opened == None:
            dlo = now
        else:
            dlo = self.door_last_opened
        if event_type == TIMER_E:
            ret_str = TIMER_E.format(self.name, now)
        elif event_type == DOOR_OPENING_ERROR_E:
            ret_str = DOOR_OPENING_ERROR_E.format(self.name, now)
        elif event_type == BUTTON_OPEN_E:
            ret_str = BUTTON_OPEN_E.format(self.name)
        elif event_type == DOOR_CLOSING_ERROR_E:
            ret_str = DOOR_CLOSING_ERROR_E.format(self.name, now)
        elif event_type == BUTTON_CLOSE_E:
            ret_str = BUTTON_CLOSE_E.format(self.name)
        elif event_type == OPEN_E:
            ret_str = OPEN_E.format(self.name, dlo)
        else:
            ret_str = "Invalid event"
        return ret_str

    def _send_msg(self, event_type):
        ''' Sends a message via sms '''
        msg = self._get_event_msg(event_type)
        self.l.debug("Sending message '{0}'".format(msg))
        GS.send_message(msg, self.event_notification_list[event_type])
        return

    def _door_closed(self):
        '''
            This function is called when the garage door is detected to have
            closed. 
        '''
        self.l.info("Door closed")
        if self.msg_timer == None:
            self.l.error("Door closed and no open msg_timer - should not happen")
        else:
            self.msg_timer.cancel()
            self.history[CLOSE_HIST_KEY].insert(0, time.ctime())
            self.history.sync()
            self.msg_timer = None
        return

    def get_open_history(self, count=DEFAULT_HIST_COUNT):
        """ Return a string of the last n times door opened """
        count = min(count, len(self.history[OPEN_HIST_KEY]))
        str_list = ["{}'s door open history:".format(self.name),] + self.history[OPEN_HIST_KEY][:count]
        ret_str = "\t\n".join(str_list)
        return ret_str

    def _sub_event(self, phone_number, event):
        if phone_number not in self.event_notification_list[event]:
            self.event_notification_list[event].append(phone_number)
            self.event_notification_list.sync()
        self.l.debug("Event notification list: {}".format(self.event_notification_list))
        return 

    def sub_open_event(self, phone_number):
        """ Add a phone number to be notified when door is opened """
        self._sub_event(phone_number, OPEN_E)
        return

    def sub_close_event(self, phone_number):
        """ Add a phone number to be notified when door is closed"""
        self._sub_event(phone_number, CLOSE_E)
        return

    def sub_timer_event(self, phone_number):
        """
            Add a phone number to be notified when door is opened at
            a particular time (set with set_timer_time)
        """
        self._sub_event(phone_number, TIMER_E)
        return

    def sub_error_event(self, phone_number):
        """ Add phone number to be notified when door fails to open / close """
        self._sub_event(phone_number, DOOR_CLOSING_ERROR_E)
        self._sub_event(phone_number, DOOR_OPENING_ERROR_E)
        return

    def sub_button_event(self, phone_number):
        """ Add phone number to be notified when door button is pressed via sms """
        self._sub_event(phone_number, BUTTON_CLOSE_E)
        self._sub_event(phone_number, BUTTON_OPEN_E)
        return

    def _unsub_event(self, phone_number, event):
        """ Remove phone number from notifications """
        if phone_number in self.event_notification_list[event]:
            self.event_notification_list[event].remove(phone_number)
            self.event_notification_list.sync()
        self.l.debug("Event notification list: {}".format(self.event_notification_list))
        return

    def unsub_button_event(self, phone_number):
        """ Remove phone number from notifications """
        self._unsub_event(phone_number, BUTTON_CLOSE_E)
        self._unsub_event(phone_number, BUTTON_OPEN_E)
        return

    def unsub_error_event(self, phone_number):
        """ Remove phone number from notifications """
        self._unsub_event(phone_number, DOOR_CLOSING_ERROR_E)
        self._unsub_event(phone_number, DOOR_OPENING_ERROR_E)
        return

    def unsub_timer_event(self, phone_number):
        """ Remove phone number from notifications """
        self._unsub_event(phone_number, TIMER_E)
        return

    def unsub_close_event(self, phone_number):
        """ Remove phone number from notifications """
        self._unsub_event(phone_number, CLOSE_E)
        return

    def unsub_open_event(self, phone_number):
        """ Remove phone number from notifications """
        self._unsub_event(phone_number, OPEN_E)
        return

    def is_sub_open_event(self, phone_number):
        """ Return true if phone number is subscribed """
        return phone_number in self.event_notification_list[OPEN_E]

    def is_sub_close_event(self, phone_number):
        """ Return true if phone number is subscribed """
        return phone_number in self.event_notification_list[CLOSE_E]

    def is_sub_error_event(self, phone_number):
        """ Return true if phone number is subscribed to either error type """
        ret_val = (phone_number in self.event_notification_list[DOOR_CLOSING_ERROR_E] or
                phone_number in self.event_notification_list[DOOR_OPENING_ERROR_E])
        return ret_val

    def is_sub_timer_event(self, phone_number):
        """ Return true if phone number is subscribed """
        return phone_number in self.event_notification_list[TIMER_E]

    def is_sub_button_event(self, phone_number):
        """ Return true if phone number is subscribed to either button event """
        ret_val = (phone_number in self.event_notification_list[BUTTON_CLOSE_E] or
                phone_number in self.event_notification_list[BUTTON_OPEN_E])
        return ret_val

if __name__ == "__main__":
    pass
