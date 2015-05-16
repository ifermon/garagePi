#!/bin/bash
BASE_DIR='/home/pi/garagePi'
echo "BASE_DIR = $BASE_DIR"
cd ${BASE_DIR}
echo "PWD = $(pwd)"
. ${BASE_DIR}/venv/bin/activate
sudo ${BASE_DIR}/venv/bin/python ${BASE_DIR}/garage.py > ${BASE_DIR}/logs/go.out 2>&1
