import garageShared as GS
import multiprocessing as mp
import os
import time
import RPi.GPIO as GPIO
from threading import Timer
import logging

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
    
    # Define class constants
    OPENED = 0
    CLOSED = 1
    POWER_PIN = 24 

    def get_state_str(self, state=None):
        '''
            Utility method to get string versions of state
            Default to value of current_state
        '''
        if state == None:
            state = self.current_state
        if state == Door.OPENED:
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
        self.nag_timer = None
        self.event_notfication_lists = {"open": [], "nag": [], "timer": []}

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
        GPIO.setup(Door.POWER_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(Door.POWER_PIN, True)

        # Settings for relay switch (door switch)
        GPIO.setup(self.push_button_pin, GPIO.OUT, initial=GPIO.HIGH)

        # Set a callback function, when it detects a change
        # this function will be called
        GPIO.add_event_detect(self.open_close_state_pin, GPIO.RISING,
                callback = self.door_moving_callback, bouncetime=2000)

        # Now get and set the current state of the door
        self.last_state = self.get_status()

        # Add a timer to wake at 10pm and check the door
        self.n10pm_timer = Timer(GS.secs_until_10pm(), self.n10pm_check)
        self.n10pm_timer.start()

        self.l.info("\n\tName: {0}\n".format(door_name) +
                "\tProcess name: {0}\n".format(mp.current_process().name) +
                "\tParent PID: {0}\n".format(os.getppid()) +
                "\tPID: {0}\n".format(os.getpid()) +
                "\tPower pin: {0}\n".format(Door.POWER_PIN) +
                "\tSignal pin: {0}\n".format(open_close_state_pin) +
                "\tSwitch pin: {0}\n".format(push_button_pin) +
                "\tCurrent state {0}\n".format(self.get_state_str()))

        self.lock.release()
        return

    def n10pm_check(self):
        ''' Checks status of door, sends message if open, resets timer '''
        self.l.info("Starting 10pm check")
        time.sleep(5) # Make sure we are past 10pm
        if self.get_status() == Door.OPENED:
            self.send_msg(Door.OPENED)
            self.l.debug("10pm check, door opened.")

        # Set a new timer for the next 10pm
        self.l.info("Setting 10pm timer for {} secs from now.".format(
                GS.secs_until_10pm()))
        self.n10pm_timer = Timer(GS.secs_until_10pm(), self.n10pm_check)
        self.n10pm_timer.start()
        self.l.debug("10pm door check finished for {0}".format(self.name))
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
        self.l.info("Pushing button {0}'s door".format(self.name))
        GPIO.output(self.push_button_pin, GPIO.LOW)
        time.sleep(1)
        GPIO.output(self.push_button_pin, GPIO.HIGH)
        self.lock.release()
        return

    def open(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already open
        '''
        if self.get_status() == Door.CLOSED:
            self.press_button()
        return

    def close(self):
        '''
            Public method that can be called from outside unsynched process
            Locking handled by press_button and get state functions
            Presses button to toggle door if door state is not already closed
        '''
        if self.get_status() == Door.OPENED:
            self.press_button()
        return

    def door_moving_callback(self, channel):
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
            if self.current_state == Door.OPENED:
                self.door_opened()
                self.l.debug("In callback, door opened")
            else:
                self.door_closed()
                self.l.debug("In callback, door closed")
            self.last_state = self.current_state
        else:
            self.l.debug("In callback, nothing changed")

        self.lock.release()
        self.l.debug("Done processing callback")
        return

    def door_opened(self):
        '''
            This function is called when the garage door is detected to have
            opened. Sends a text message and logs event
        '''
        self.l.info("Got door opened event")
        
        # If there is a timer set, that means that I recently opened the door
        # So don't spam texts. Reset timer and move on
        if self.msg_timer != None:
            self.l.debug("Msg pending already, ignore")
            self.msg_timer.cancel()

        else:
            # Record the time last opened if event is "new"
            self.door_last_opened = time.time()
            # Now send msg and set a msg timer so we don't send more messages
            self.send_msg(Door.OPENED)

        # Set a timer so we don't bother with repeated messages
        quiet_time_in_secs = 300
        self.msg_timer = Timer(quiet_time_in_secs, self.quiet_time_over)
        self.msg_timer.start()
        return

    def quiet_time_over(self):
        ''' Clears the quiet time timer '''
        # Clear the msg timer 
        self.msg_timer = None

        # Check to see if door is still opened, if so, set timer to check
        # again in 30 mins
        if self.get_status() == Door.OPENED:
            nag_time_in_secs = 1800
            if self.nag_timer != None:
                self.nag_timer.cancel()
            self.nag_timer = Timer(nag_time_in_secs, self.door_nag )
            self.nag_timer.start()
        self.l.debug("Leaving quiet timer")
        return

    def send_msg(self, event_type):
        ''' Sends a message via sms '''
        if event_type == Door.OPENED:
            msg = "{0}'s door was opened at {1}".format(self.name,
                time.ctime(self.door_last_opened))
        else:
            msg = "{0}'s door was closed at {1}".format(self.name,
                time.ctime(time.time()))
        try:
            GS.send_message(msg)
        except:
            self.l.debug("Failed sending message {1}".format(msg))
        self.l.debug("Sent message '{0}'".format(msg))
        return

    def door_nag(self):
        ''' This is called when the timer goes off '''
        # Clear the nag timer
        self.nag_timer = None
        
        if self.get_status() == Door.OPENED:
            GS.send_message("{0}'s door is still opened.".format(self.name))
        self.l.debug("Leaving nag timer")
        return

    def door_closed(self):
        '''
            This function is called when the garage door is detected to have
            closed. 
        '''
        self.l.info("Door closed")
        return

    def _sub_event(self, phone_number, event):
        self.event_notification_list[event].append(phone_number)
        return 

    def sub_open_event(self, phone_number):
        """ Add a phone number to be notified when door is opened """
        self._sub_event(phone_number, "open")
        return

    def sub_nag_event(self, phone_number):
        """ Add a phone number to be notified when door is opened 
            more than nag minutes (set with set_nag_time)
        """
        self._sub_event(phone_number, "nag")
        return

    def sub_timer_event(self, phone_number):
        """
            Add a phone number to be notified when door is opened at
            a particular time (set with set_timer_time)
        """
        self._sub_event(phone_number, "timer")
        return

    def set_timer_time(self, time):
        return

    def set_nag_time(self, minutes):
        return

if __name__ == "__main__":
    pass
