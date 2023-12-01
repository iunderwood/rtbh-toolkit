#!/usr/bin/env python3

from globals import *

# Internal Imports
import argparse
import logging

# External Imports
import iupy
import psycopg2
import yaml
import yaml.scanner


def cli_args():
    """
    Process CLI Arguments and return the namespace.

    :return:
    """
    _logger = logging.getLogger("rtbh-database/cli_args")

    cli_parser = argparse.ArgumentParser(description="RTBH Database Utility v{}".format(version),
                                         epilog="This program can initialize or flush the RTBH back end database.")

    cli_parser.add_argument('-d', '--debug',
                            action='store_true',
                            help="Enable script debugging.  This is a LOT of output.")

    sub_parser = cli_parser.add_subparsers(help='Primary Operations',
                                           required=True)

    # Initialization Sub Parser
    op_init = sub_parser.add_parser('init',
                                    help='This option will initialize the database.')
    op_init.set_defaults(operation='init')
    op_init.add_argument('--db-superuser',
                         required=True,
                         action='store',
                         help='This is the database account name with CREATE USER and CREATE DATABASE permission.')
    op_init.add_argument('--db-superpass',
                         required=True,
                         action='store',
                         help='This is the password for the superuser account.')

    op_init.add_argument('--db-rouser',
                         required=False,
                         action='store',
                         help='This is the database account with read-only permissions.')
    op_init.add_argument('--db-ropass',
                         required=False,
                         action='store',
                         help='This is the password for the read-only account.')

    # Database Flush Sub Parser
    op_flush = sub_parser.add_parser('flush',
                                     help='This option will flush the database tables.')
    op_flush.set_defaults(operation='flush')

    # Database Lock Status
    op_status = sub_parser.add_parser('locks',
                                      help='Show the locks associated with each process.')
    op_status.set_defaults(operation='status')

    # Database Unlock Process
    op_unlock = sub_parser.add_parser('unlock',
                                      help='This option will unlock and stuck processes.')
    op_unlock.set_defaults(operation='unlock')

    # Assign the arguments to a variable
    arguments = cli_parser.parse_args()

    if vars(arguments)['debug']:
        logging.basicConfig(level=logging.DEBUG)
        logger.debug("Debug Logging Enabled")

    return arguments


def load_config(config_file):
    """
    Loads configuration and performs YAML processing on it.

    This will either populate, or add to the global configuration dictionary.

    :return:
    """

    global config

    _logger = logging.getLogger("rtbh-database/load_config")

    # Load the configuration file into a dictionary.
    config_dict = iupy.get_my_config(config_file, subdir="rtbh_toolkit")

    # Error and return false if we can't find the given file.
    if not config_dict:
        _logger.error("Unable to find configuration {} in any of the expected locations.".format(config_file))
        return False

    # Attempt to load the YAML config into a dictionary.
    try:
        config_yaml = yaml.load(config_dict['data'], Loader=yaml.SafeLoader)
    except yaml.scanner.ScannerError as error:
        _logger.error("File {} is not a valid YAML file.\n----\n{}\n----\n".format(config_file, error))
        return False

    # Create the config, if we can't append to it first.
    try:
        config = {**config, **config_yaml}
    except TypeError:
        config = {**config_yaml}

    return True


def unlock_process(db_link):
    _logger = logging.getLogger("rtbh-database/unlock_process")

    db = db_link.cursor()

    try:
        db.execute("UPDATE processes SET runlast = current_timestamp, status = 'UNLOCKED' WHERE status = 'LOCKED'")
        print()
    except Exception as error:
        _logger.error("Could not unlock processes: {}\r".format(error))

    db.close()


def lock_status(db_link):
    _logger = logging.getLogger("rtbh-database/lock_status")

    db = db_link.cursor()

    try:
        db.execute("SELECT processname, status FROM processes ORDER BY status, processname")
    except Exception as error:
        _logger.error("Count not get a process list.")

    for row in db:
        print("{:.<20}: {:10}".format(row[0], row[1]))


def create_tables(db_link):
    """
    This function creates the tables required.

    :param db_link:
    :return:
    """

    _logger = logging.getLogger("rtbh-database/create_tables")

    # Open up a query cursor.
    db = db_link.cursor()

    # Create Process Table
    sql = '''CREATE TABLE IF NOT EXISTS processes (
            processname     varchar(16),
            status          varchar(8),
            runlast         timestamptz,
            runsuccess      int,
            runfailure      int,
            PRIMARY KEY (processname)
        )'''
    try:
        db.execute(sql)
        print("Created table: processes\r")
    except Exception as error:
        _logger.error("Could not create table: {}\n".format(error))

    # Create Master IP Table
    sql = '''CREATE TABLE IF NOT EXISTS netlist (
            address         cidr,
            isactive        boolean,
            firstadd        timestamptz     default current_timestamp,
            lastadd         timestamptz     default current_timestamp,
            PRIMARY KEY (address)
        )'''
    try:
        db.execute(sql)
        print("Created table: netlist")
    except Exception as error:
        _logger.error("Could not create table: {}\n".format(error))

    # Create History Table
    sql = '''CREATE TABLE IF NOT EXISTS history (
            entrytime       timestamptz     default current_timestamp,
            address         cidr,
            source          varchar(16),
            action          varchar(8),
            entry           varchar(96),
            CONSTRAINT fk_address
                FOREIGN KEY (address)
                    REFERENCES netlist(address),
            CONSTRAINT fk_source
                FOREIGN KEY (source)
                    REFERENCES processes(processname)
        )'''
    try:
        db.execute(sql)
        print("Created table: history")
    except Exception as error:
        _logger.error("Could not create table: {}\n".format(error))

    # Create active block table.
    sql = '''CREATE TABLE IF NOT EXISTS blocklist (
            address         cidr,
            source          varchar(16),
            score           real            default 0,
            firstadd        timestamptz     default current_timestamp,
            lastadd         timestamptz     default current_timestamp,
            PRIMARY KEY (address, source),
            CONSTRAINT fk_address
                FOREIGN KEY (address)
                    REFERENCES netlist(address),
            CONSTRAINT fk_source
                FOREIGN KEY (source)
                    REFERENCES processes(processname)
        )'''
    try:
        db.execute(sql)
        print("Created table: blocklist")
    except Exception as error:
        _logger.error("Could not create table: {}\r".format(error))

    # Close query cursor
    db.close()


def flush_tables(db_link):
    """
    This function flushes tables.
    :param db_link:
    :return:
    """

    _logger = logging.getLogger("rtbh-database/flush_tables")

    # Open up a query cursor.
    db = db_link.cursor()

    # Flush Blocklist
    try:
        db.execute("DELETE FROM blocklist")
        print("Purged table: blocklist")
    except Exception as error:
        _logger.error("Could not purge table: {}\r".format(error))

    # Flush History
    try:
        db.execute("DELETE FROM history")
        print("Purged table: history")
    except Exception as error:
        _logger.error("Could not purge table: {}\r".format(error))

    # Flush Hostlist
    try:
        db.execute("DELETE FROM netlist")
        print("Purged table: netlist")
    except Exception as error:
        _logger.error("Could not purge table: {}\r".format(error))

    # Flush Processes
    try:
        db.execute("DELETE FROM processes")
        print("Purged table: processes")
    except Exception as error:
        _logger.error("Could not purge table: {}\r".format(error))

    # Close down a query cursor.
    db.close()


if __name__ == "__main__":

    logger = logging.getLogger("rtbh-database")

    # Process CLI Arguments
    args = cli_args()

    # Load module configuration.  Exit if we can't find one.
    if not load_config("rtbh-config.yaml"):
        exit(1)

    if vars(args)['operation'] == 'init':

        # Assign variables from arguments
        dbSuperUserName = vars(args)['db_superuser']
        dbSuperUserPass = vars(args)['db_superpass']

    # Assign variables from configuration
    try:
        dbHost = config['database']['dbHost']
        dbPort = config['database']['dbPort']
        dbName = config['database']['dbName']
        dbUserName = config['database']['dbUserName']
        dbUserPass = config['database']['dbUserPass']
    except KeyError as error:
        logger.error("FATAL: Configuration element {} missing.".format(error))
        exit(1)

    print("RTBH Database Init")
    print("==================")

    if vars(args)['operation'] == 'init':
        # Connect to DB, and enable auto-commit:
        try:
            db_link = psycopg2.connect(host=dbHost, port=dbPort, database="postgres",
                                       user=dbSuperUserName, password=dbSuperUserPass)
            db_link.autocommit = True
        except Exception as error:
            logger.error("Could not open database as superuser: {}".format(error))
            exit(2)

        db_cursor = db_link.cursor()

        # Create the r/w database user.
        try:
            db_cursor.execute("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{}'".
                              format(dbUserName, dbUserPass))
            db_cursor.execute("COMMENT ON ROLE {} IS 'RTBH Read-Write Account'".format(dbUserName))
            print("Created user: {}".format(dbUserName))
        except Exception as error:
            logger.error("Could not create user: {}".format(error))
            exit(3)

        # Create the database itself and assign to read-write account.
        try:
            db_cursor.execute("CREATE DATABASE {} WITH OWNER = {}".format(dbName, dbUserName))
            print("Created database {}, owned by {}.\r".format(dbName, dbUserName))
        except Exception as error:
            logger.error("Could not create database: {}".format(error))
            exit(4)

        # Close database
        db_cursor.close()
        db_link.close()

    # Create the read-only user under the proper database.

    if vars(args)['operation'] == 'init':
        try:
            db_link = psycopg2.connect(host=dbHost, port=dbPort, database=dbName,
                                       user=dbSuperUserName, password=dbSuperUserPass)
            db_link.autocommit = True
        except Exception as error:
            logger.error("Could not open database as superuser: {}".format(error))
            exit(2)

        # Create the read-only user if we both options.
        try:
            dbReadUser = vars(args)['db_rouser']
            dbReadPass = vars(args)['db_ropass']
            stepReadUser = True
        except Exception as error:
            logger.debug("DB read-only account not created.")
            stepReadUser = False

        if stepReadUser:
            db_cursor = db_link.cursor()

            # Create, comment, and grant
            try:
                db_cursor.execute("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{}'".
                                  format(dbReadUser, dbReadPass))
                db_cursor.execute("COMMENT ON ROLE {} IS 'RTBH Read-Only Account'".format(dbReadUser))
                db_cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}".format(dbReadUser))
                print("Created read-only user: {}".format(dbReadUser))
            except Exception as error:
                logger.error("Non-Fatal: Unable to create read-only user: {}".format(error))

            db_cursor.close()

        # Close database
        db_link.close()

    # Open database as DB User
    try:
        db_link = psycopg2.connect(host=dbHost, port=dbPort, database=dbName, user=dbUserName, password=dbUserPass)
        db_link.autocommit = True
    except Exception as error:
        logger.error("Could not open database as user {}: {}".format(dbUserName, error))
        exit(5)

    # Check other conditions
    if vars(args)['operation'] == 'flush':
        print("Flushing all tables...")
        flush_tables(db_link)
    elif vars(args)['operation'] == 'init':
        print("Creating all tables...")
        create_tables(db_link)
    elif vars(args)['operation'] == 'status':
        print("Current Lock Status...")
        lock_status(db_link)
    elif vars(args)['operation'] == 'unlock':
        print("Unlocking processes...")
        unlock_process(db_link)
    else:
        logger.error("Unknown operation.")

    # Close database
    db_link.close()
