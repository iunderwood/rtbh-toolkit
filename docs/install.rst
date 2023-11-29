RTBH Installation
=================

This is a set of suggested steps for installation of the RTBH toolkit.

Install Requirements
--------------------

The system requires the following minimum parameters:

* Python 3.11, w/ PIP to manage the requirements.

* PostgreSQL 13, w/ limited access to a superuser account for installation

All shell scripts currently provided assume a BASH-compatible shell.

Service Accounts
----------------

Use of dedicated service accounts to execute the RTBH process is highly recommended.  This account should be sudo accessible to the system adminsistration team as well as the local owner of this application.

Python VENV
-----------

Ideally, the RTBH Toolkit should be installed inside its own VENV.  At this stage of development,
the placement of the VENV is up to the whims of the system administrator.