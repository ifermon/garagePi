#!/bin/bash
BASE_DIR='/home/garage/garagePi'
date
echo "BASE_DIR = $BASE_DIR"
cd ${BASE_DIR}
echo "PWD = $(pwd)"
. ${BASE_DIR}/venv/bin/activate
date

echo "Starting garage.py"
sudo ${BASE_DIR}/venv/bin/python ${BASE_DIR}/garage.py >> ${BASE_DIR}/logs/go.out 2>&1 &

# Send msg re: restart if it's not a crontab reboot
if [ -f /home/pi/garage/cronboot ]; then
    echo "Not sending text, removing cronboot"
    rm /home/pi/garage/cronboot
else
    date
    echo "Sending text regarding reboot"
    wget --quiet --delete --no-check -t 1 "https://192.168.0.215:5000/send_message?msg=Starting garagePi"
fi
