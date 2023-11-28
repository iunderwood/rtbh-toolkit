#!/usr/bin/env bash

# Activate Python VENV

source /usr/local/python/venv/rtbh_toolkit/bin/activate

# Change to the code directory

cd /usr/local/python/venv/rtbh_toolkit/src/rtbh-toolkit/rtbh-toolkit/

# Cron Header
echo "RTBH Scheduled Update Process"
echo "============================="
echo -n "Cron Start: "; TZ='America/New_York' date
echo

# Update all automatic lists.
./rtbh-listrunner.py

# Push the config
./rtbh-routerupdate-xe.py

# Show Summary
echo
./rtbh-summary.py summary --last 25

echo
echo -n "Cron End: "; TZ='America/New_York' date