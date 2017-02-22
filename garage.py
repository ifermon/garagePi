#!/home/garage/garagePi/venv/bin/python
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
import time
import sms_monitor as SMS
import light_monitor as LM
import sys
import const
import logging
import sdnotify
"""
    TO DO: Respond to texts to the number that it came from for help and status
"""

def list_current_subscriptions(from_number, cmds):
    msg_str = "You'll be notified of the following events:\n"
    for d in ivan_door, heather_door:
        e_str = "{}'s door:\n".format(d.name)
        e_check = len(e_str) # We'll check for changes later
        if d.is_sub_event(Door.OPEN_E, from_number):
            e_str += " - When door opens\n"
        if d.is_sub_event(Door.CLOSE_E, from_number):
            e_str += " - When door closes\n"
        if d.is_sub_event(Door.TIMER_E, from_number):
            e_str += " - When door is left open\n"
        if d.is_sub_event(Door.BUTTON_OPEN_E, from_number):
            e_str += " - Confirmation of open\n"
        if d.is_sub_event(Door.BUTTON_CLOSE_E, from_number):
            e_str += " - Confirmation of close\n"
        if d.is_sub_event(Door.DOOR_OPENING_ERROR_E, from_number) or d.is_sub_event(Door.DOOR_CLOSING_ERROR_E, from_number):
            e_str += " - If there is an error\n"
        if len(e_str) == e_check:
            # You are not subscribed to anything for this door
            msg_str += "Nothing for {}'s door.\n".format(d.name)
        else:
            msg_str += e_str
    GS.send_message(msg_str, [from_number,])
    return

def _get_door(door_abbr):
    door = None
    if door_abbr == "i":
        door = ivan_door
    elif door_abbr == "h":
        door = heather_door
    else:
        l.info("Unknown door abbreviation: {}".format(door_abbr))
    return door

def help_text(from_number, cmds):
    """ Respond with the list of valid commands """
    ret_str = ("s, i, h\n"
               "[un]sub [i/h] [timer/open/close/error/button]\n"
               "list\n"
               "?\n"
               "hist i/h [count]\n"
               "si/sh [# minutes (optional)")
    GS.send_message(ret_str)
    GS.send_message(from_number)
    return

def get_history(from_number, cmds):
    """
        Get the history of open / close events for door
    """
    l.info("Got a history command: {}".format(cmds))
    if len(cmds) < 2:
        door = None
    else:
        door = _get_door(cmds[1])
    if door is None:
        GS.send_message("Invalid door name '{}'. Use i or h.".format(door), [from_number,])
        return

    if len(cmds) > 2: #We should have a count
        count = cmds[2]
    else:
        count = None
    ret_str = door.get_open_history(count)
    l.info("In get_history: return msg is: {}".format(ret_str))
    GS.send_message(ret_str)
    return


def subscribe(from_number, cmds):
    """
        Subscribe from events for user
        sub door_name event_type
    """
    l.info("Got a subscribe command: {}".format(cmds))
    door = _get_door(cmds[1])
    if door is None:
        GS.send_message("Invalid door name '{}'. Use i or h.".format(cmds[1]), [from_number,])
        return

    event_type = cmds[2]
    if event_type == "timer":
        door.sub_event(Door.TIMER_E, from_number)
    elif event_type == "open":
        door.sub_event(Door.OPEN_E, from_number)
    elif event_type == "close":
        door.sub_event(Door.CLOSE_E, from_number)
    elif event_type == "error":
        door.sub_event(Door.DOOR_OPENING_ERROR_E, from_number)
        door.sub_event(Door.DOOR_CLOSING_ERROR_E, from_number)
    elif event_type == "button":
        door.sub_event(Door.BUTTON_CLOSE_E, from_number)
        door.sub_event(Door.BUTTON_OPEN_E, from_number)
    else: # Should not happen, but users can do typos
        l.info("Unknown event type {}.".format(event_type))
        GS.send_message("Unknown event type {}. Use timer, open, close, error or button".format(event_type),
                        [from_number])
        return
    GS.send_message("Subscribe to {} events for {}'s door confirmed!".format(event_type, door))
    return

def unsubscribe(from_number, cmds):
    """
        Unsubscribe from events for user
        unsub door_name event_type
    """
    l.info("Got an unsubscribe command: {}".format(cmds))
    door = _get_door(cmds[1])
    if door is None:
        GS.send_message("Invalid door name '{}'. Use i or h.".format(cmds[1]), [from_number, ])
        return

    event_type = cmds[2]
    if event_type == "timer":
        door.unsub_event(Door.TIMER_E, from_number)
    elif event_type == "open":
        door.unsub_event(Door.OPEN_E, from_number)
    elif event_type == "close":
        door.unsub_event(Door.CLOSE_E, from_number)
    elif event_type == "error":
        door.unsub_event(Door.DOOR_OPENING_ERROR_E, from_number)
        door.unsub_event(Door.DOOR_CLOSING_ERROR_E, from_number)
    elif event_type == "button":
        door.unsub_event(Door.BUTTON_CLOSE_E, from_number)
        door.unsub_event(Door.BUTTON_OPEN_E, from_number)
    else:
        l.info("Unknown event type {}.".format(event_type))
        GS.send_message("Unknown event type {}. Use timer, open, close, error or button".format(event_type),
                        [from_number])
        return
    GS.send_message("Unsubscribe to {} events for {}'s door confirmed!".format(event_type, door))
    return

def ret_status(from_number, cmds):
    """ Build the status message to send back to texter """
    s1 = "Ivan's door is {0}.".format(ivan_door.get_state_str().lower())
    s2 = "Heather's door is {0}.".format(heather_door.get_state_str().lower())
    if GS.is_dark(): # i.e. it's night time
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

    # Setup the indivdiual garage doors
    """
    if not config.haskey("doors"):
        l.error("No garage doors configured in config.yaml")
        sys.exit(1)
    #for d in config["doors"]:
    """

    ivan_door = Door(23,18,"Ivan",GS.lock)
    heather_door = Door(17, 22, "Heather",GS.lock)

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
              'status': ret_status,
             'help': help_text,
              '?': help_text,
              'sub': subscribe,
              'unsub': unsubscribe,
              'hist': get_history,
              'list': list_current_subscriptions,
              'si': ivan_door.snooze_timer,
              'sh': heather_door.snooze_timer,
             'i': ivan_door.press_button,
             'h': heather_door.press_button}
    # Number map just gives a list of valid numbers for the from
    valid_numbers = [const.Ivan_cell, const.Heather_cell]

    # We are a service, so tell them that we have started up successfully
    n = sdnotify.SystemdNotifier()
    n.notify("READY=1")
    n.notify("WATCHDOG_USEC=80")

    # everything is set up, now wait for messages and process them as needed
    while keep_alive:
            n.notify("WATCHDOG=1")
            # wait until we get a message
            l.debug("Waiting for message")
            try:
                    msg = q.get(True, 60)
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
    
