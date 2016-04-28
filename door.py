import garage_shared as GS
import multiprocessing as mp
import os
import time
import RPi.GPIO as GPIO
from threading import Timer
import logging
import my_plivo
import plivo
#from constants_door import *

# Define constants
OPENED = 0 # Value of pin state when door is opened (circut open)
CLOSED = 1 # Value of pin state when door is closed (circut closed)
POWER_PIN = 24
INITIAL_WAIT_TIME = 300 # Time in secs before first nag msg is sent when door is left opened
REPEAT_WAIT_TIME = 1800 # Time in secs before repeat nag msg is sent
TRANSITION_WAIT_TIME = 30 # Time in secs to wait for door operation to complete (open/close)

# Events used for sending messages / publishing messages
# Event values are also designed to be the message text - I know this is horrible but it's easy
CLOSE_E = "{}'s door was closed at {}."
OPEN_E = "{}'s door was opened at {}."
TIMER_E = "{}'s door is still opened at {}."
DOOR_CLOSING_ERROR_E = "Error closing {}'s door at {}."
DOOR_OPENING_ERROR_E = "Error opening {}'s door at {}."

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

        # access the logger and set up logging
        self.name = door_name
        self.open_close_state_pin = open_close_state_pin
        self.push_button_pin = push_button_pin
        self.msg_timer = None
        self.event_notification_list = {CLOSE_E: [], OPEN_E: [], TIMER_E: [],
                                       DOOR_OPENING_ERROR_E: [], DOOR_CLOSING_ERROR_E: []}

        # Setup logging just for this door
        self.l = GS.getLogger(GS.loggerName)

        # We're going to make a new logger just for us
        #l = logging.getLogger(self.name)


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
            self.msg_timer = Timer(INITIAL_WAIT_TIME, self._quiet_time_over)
            self.door_last_opened = time.time()

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

    def press_button(self):
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
            self.l.info("{}'s door is closed, opening it".format(self.name))
            """ Door open will generate message, so no need to send another """
            if self.get_status() == CLOSED:
                """ Failed at opening door, send message """
                self._send_msg(DOOR_OPENING_ERROR_E)
        elif begin_state == OPENED:
            """ Let's confirm that the door was closed"""
            self.l.info("{}'s door is opened, closing it".format(self.name))
            if self.get_status() != CLOSED:
                self.l.error("{}'s door did not close as expected".format(self.name))
                self._send_msg(DOOR_CLOSING_ERROR_E)
            else: # Door closed as expected
                self.l.debug("{}'s door closed after pressing button".format(self.name))
                self._send_msg(CLOSE_E)
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
            self.door_last_opened = time.time()
            # Now send msg and set a msg timer so we don't send more messages
            self._send_msg(OPEN_E)

        # Set a timer so we don't bother with repeated messages
        self.msg_timer = Timer(INITIAL_WAIT_TIME, self._quiet_time_over)
        self.msg_timer.start()
        return

    def _quiet_time_over(self):
        ''' Clears the quiet time timer, checks to see if door is still opened, and sets another timer if it is '''
        # Clear the msg timer 
        self.msg_timer = None

        # Check to see if door is still opened, if so, set timer to check
        # again in 30 mins
        if self.get_status() == OPENED:
            self.msg_timer = Timer(REPEAT_WAIT_TIME, self._quiet_time_over)
            self.msg_timer.start()
        self.l.debug("Leaving quiet timer")
        return

    def _send_msg(self, event_type):
        ''' Sends a message via sms '''
        msg = event_type.format(self.name, time.ctime(self.door_last_opened))
        try:
            # Your Account Sid and Auth Token from plivo.com/user/account
            account_id = my_plivo.auth_id
            auth_token  = my_plivo.auth_token
            # List of numbers to send message to
            client = plivo.RestAPI(account_id, auth_token)
            number_list = self.event_notification_list[event_type]
            self.l.debug("Sending msg to the following numbers: {}".format(
                    ", ".join(map(str, number_list))))
            for n in number_list:
                    params = { 'src': my_plivo.number, 
                                    'dst': n, 
                                    'text': msg, 
                                    'type': 'sms', }
                    response = client.send_message(params)
        except Exception as e:
            self.l.error("Failed sending message {}".format(msg))
            self.l.error(e)
        self.l.debug("Sent message '{0}'".format(msg))
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
            self.msg_timer = None
        return

    def _sub_event(self, phone_number, event):
        self.event_notification_list[event].append(phone_number)
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

    def sub_door_error_event(self, phone_number):
        """ Add phone number to be notified when door fails to open / close """
        self._sub_event(phone_number, DOOR_CLOSING_ERROR_E)
        self._sub_event(phone_number, DOOR_OPENING_ERROR_E)
        return


if __name__ == "__main__":
    pass
