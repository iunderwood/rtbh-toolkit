# rtbh-toolkit

Remote Trigger Black Hole Toolkit

## Description

This toolkit is a loosely integrated set of Python scripts that are used to manage and maintain a Remote Trigger Black Hole infrastructure.

Detailed documentation can be found in the docs/ code directory, or in a more viaually pleasning format here:

https://rtbh-toolkit.readthedocs.io/en/latest/

### rtbh-database.py

This utility is used to create the database and perform certain maintenance operations.

### rtbh-listrunner.py

This utility process incoming address lists.  This performs adds, updates, and deletes against the database. 

### rtbh-routerunner-xe.py

This utility maintains the static routes on a Cisco IOS-XE device serving as the RTBH server. 

### rtbh-query.py

This utility allows for some simple queries to be made against the RTBH database from the command line.

## Donation

If you have found this software to be useful, please consider making a donation to the Boston Children's Hospital Trust: http://giving.childrenshospital.org/