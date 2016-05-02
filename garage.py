'''
	This is the master base class for the garage project
	It is used to pass around shared objects
	These are class level references, not instance level
	All objects referenced here must be thread / multi process safe
'''
from multiprocessing import RLock, Queue
from Queue import Empty
import garage_shared as GS
from door import Door
from sets import Set
import time
import sms_monitor as SMS
import light_monitor as LM
import sys
import const
import logging
"""
    TO DO: Respond to texts to the number that it came from for help and status
"""

def _get_door(door_abbr):
    door = None
    if door_abbr == "i":
        door = ivan_door
    elif door_abbr == "h":
        door = heather_door
    else:
        l.error("Unknown door abbreviation: {}".format(door_abbr))
    return door

def help_text(from_number, cmds):
    """ Respond with the list of valid commands """
    ret_str = ("s, i, h"
               "[un]sub [i/h] [timer/open/close/error/button]"
               "si/sh [# minutes (optional)")
    GS.send_message(ret_str)
    GS.send_message(from_number)
    return

def subscribe(from_number, cmds):
    """
        Subscribe from events for user
        sub door_name event_type
    """
    door = _get_door(cmds[1])
    if door == None:
        GS.send_message("Invalid door name.", [from_number,])
        return
    return

def unsubscribe(from_number, cmds):
    """
        Unsubscribe from events for user
        unsub door_name event_type
    """
    return

def ret_status(from_number, cmds):
    """ Build the status message to send back to texter """
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
    GS.configure_logging()
    l = logging.getLogger(__name__)
    l.info("Just configured logger")
    GS.lock = RLock()
    q = Queue()

    # Trying to move configuration items into a config file
    #config = yaml.load("./config.yaml")

    # Setup the indivdiual garage doors
    """
    if not config.haskey("doors"):
        l.error("No garage doors configured in config.yaml")
        sys.exit(1)
    #for d in config["doors"]:
    """

    ivan_door = Door(23,18,"Ivan",GS.lock)
    ivan_door.sub_timer_event(const.Ivan_cell)
    ivan_door.sub_door_error_event(const.Ivan_cell)
    ivan_door.sub_door_button_event(const.Ivan_cell)
    heather_door = Door(17, 22, "Heather",GS.lock)
    heather_door.sub_timer_event(const.Ivan_cell)
    heather_door.sub_door_error_event(const.Ivan_cell)
    heather_door.sub_door_button_event(const.Ivan_cell)

    # Start the flask server so we can receive SMS messages
    l.debug("Starting sms_listener")
    sms_listener = SMS.SMS_Monitor(q, debug=False)
    sms_listener.daemon = True
    sms_listener.start()
    time.sleep(5)
    l.debug("Started sms_listener")

    # Start the light monitor
    l.debug("Starting light_monitor")
    light_monitor = LM.Light_Monitor(q)
    light_monitor.daemon = True
    light_monitor.start()
    time.sleep(5)
    l.debug("Started light_monitor")
    

    # This is our function map. Based on the type of message (which is just
    # the name of a class), call an associated function
    f_map = { 's': ret_status,
             'help': help_text,
              'sub': subscribe,
              'unsub': unsubscribe,
              'si': ivan_door.snooze_timer,
              'sh': heather_door.snooze_timer,
             'i': ivan_door.press_button,
             'h': heather_door.press_button}
    # Number map just gives a list of valid numbers for the from
    valid_numbers = Set([const.Ivan_cell, const.Heather_cell])

    # everything is set up, now wait for messages and process them as needed
    while keep_alive:
            # wait until we get a message
            l.debug("Waiting for message")
            try:
                    msg = q.get(True, 1800)
                    l.debug ("Recevied message <{0}>.".format(msg))
            except Empty:
                    l.debug("Queue get timed out after waiting")
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
            cmd_str = msg['Text'].lower().strip().split()
            msg_func = f_map.get(cmd_str[0])
            if msg_func is not None:
                    msg_func(msg['From'], cmd_str)
            else:
                    GS.send_message("I don't know that command. Sorry.")
                    l.info("Unknown msg <{0}>".format(msg))
    
