**garagePi:**

A set of code to allow a user to monitor and control one or more garage doors via SMS commands. Meant for manual installation using a RaspberryPi and some additional hardware. Also requires a (very cheap) subscription to a service called Plivo. 

I'm happy to respond to questions if someone else would like to to use this as a start for their own project. 

Uses Raspberry Pi running Jessie. Needs additional hardware (relay(s), light sensor, reed switch(es).

Currently can support the following events:
 - Door opened 
 - Door closed
 - Door still opened after x minutes
 - Light on
 - Button pushed (vs. using door remote)

User can "subscribe" to each of these events on a door by door basis via SMS messages. Security is possible to limit the phone nubmers that will work. User can also "snooze" and alarm - e.g. if the door open nag timer is reminding you every five minutes you can snooze it to either shut it off or remind you again in xx minutes if the door is still open.

The file const.py.gpg has any values that you don't want generally available.  To refresh this file, use the command gpg -c const.py 

To Do:
 - Add ability to subscribe to light monitor events
 - Add ability to "register" a phone number on the system
 - Add interface for phone on register
 - Add ability to feed openhab

