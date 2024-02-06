RTBH Installation
=================

This is a set of suggested steps for installation of the RTBH toolkit.

The recommendations here are based upon what was used for environments in the development and QA systems.

Install Requirements
--------------------

The system requires the following minimum parameters:

* Python 3.10+, w/ PIP to manage the requirements.

* PostgreSQL 13+, w/ limited access to a superuser account for installation

All shell scripts currently provided assume a BASH-compatible shell.

Service Accounts
----------------

Use of dedicated service accounts to execute the RTBH process is highly recommended.  This account should be sudo accessible to the system adminsistration team as well as the local owner of this application.

A service account is can be created in Linux by specifying the -r flag on the useradd command:

``sudo useradd -r --create-home rtbhmgr``

Python VENV
-----------

The RTBH tooklit should be placed inside its own virtual environment.  If this is being placed on a multiuser system.  For the purposes of the documentation, the VENV is going to be housed at the following location:

``/usr/local/python/venv/rtbh``

Ownership of this directory should be assigned to the user who will be responsible for the upkeep of the system.

The directory for the VENV is also referenced in the provided examples of shell scripts via the **$RTBH_VENV** variable.  Make note of what this value should be an apply it to the system-wide profile.

``export RTBH_VENV=/usr/local/python/venv/rtbh``

Pull from GitHub
----------------

From within the VENV directory, make a new directory which contain the GitHub repository:

.. code-block::

    ./bin/activate
    mkdir src
    cd src
    git clone https://github.com/iunderwood/rtbh-toolkit
    cd rtbh-toolkit
    pip3 install -r requirements.txt

Database Initializaiton
-----------------------

In order to initialize the database, a minimal configuration must be built and placed in rtbh-config.yaml.

.. code-block:: yaml

    # Common Database Information
    database:
      dbHost: postgres.example.com
      dbPort: 5432
      dbName: rtbhdb
      dbUserName: rtbh_ro
      dbUserPass: timeToReadMe123!

To install this using the service account, the config file would be placed in /home/rtbhmgr/rtbh-config.yaml.

Initializing the database requires the Postgres superuser credentials which are specified on the command line:

``rtbh-database.py init --db-superuser PGSUPER --db-superpass PGSECRET``
