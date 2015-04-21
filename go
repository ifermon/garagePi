#!/bin/bash
BASE_DIR='/home/pi/garagePi'
cd ${BASE_DIR}
. ${BASE_DIR}/venv/bin/activate
sudo ${BASE_DIR}/venv/bin/python ${BASE_DIR}/garage.py
