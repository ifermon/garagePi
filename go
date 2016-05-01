#!/bin/bash

HOME_DIR="/home/garage"
BASE_DIR="${HOME_DIR}/garagePi"

# Check to see if we stop , this is in case we just need to stop restarting
# You can just log in and touch stop, remove stop to keep going
if [ "$1" != "skipcheck" ]; then
    if [ -f ${HOME_DIR}/stop ]; then
        echo "$(date): Stopping go... file stop exists"
        exit 0
    fi
fi

# Put in a little delay before we start, gives us time to shut things down if
# we are getting repeated reboots
echo "$(date): Starting up ... going to sleep for 30 seconds"
sleep 30

# cd to my working directory and setup virtualenv
date
echo "BASE_DIR = $BASE_DIR"
cd ${BASE_DIR}
echo "PWD = $(pwd)"
. ${BASE_DIR}/venv/bin/activate
date

echo "Starting garage.py"
#sudo ${BASE_DIR}/venv/bin/python ${BASE_DIR}/garage.py >> ${BASE_DIR}/logs/go.out 2>&1 &
${BASE_DIR}/venv/bin/python ${BASE_DIR}/garage.py 

# Send msg re: restart if it's not a crontab reboot
if [ -f /home/pi/garage/cronboot ]; then
    echo "Not sending text, removing cronboot"
    rm /home/pi/garage/cronboot
else
    date
    echo "Sending text regarding reboot"
    wget --quiet --delete --no-check -t 1 "https://192.168.0.215:5000/send_message?msg=Starting garagePi"
fi
