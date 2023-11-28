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
    _logger = logging.getLogger("rtbh-query/cli_args")

    cli_parser = argparse.ArgumentParser(description="RTBH Query Utility v{}".format(version),
                                         epilog="This program runs queries against the RTBH database.")

    cli_parser.add_argument('-d', '--debug',
                            action='store_true',
                            help="Enable script debugging.  This is a LOT of output.")

    sub_parser = cli_parser.add_subparsers(help='Primary Operations',
                                           required=True)

    # Summary Sub Parser
    op_summary = sub_parser.add_parser('summary',
                                       help='This operation will report a summary.')
    op_summary.set_defaults(operation='summary')
    op_summary.add_argument('--last',
                            action='store',
                            default=15,
                            help='Display the last x entries in the history file.  15 is default.')

    # Query Sub Parser
    op_query = sub_parser.add_parser('query',
                                     help='This operation performs a specific CIDR query.')
    op_query.set_defaults(operation='query')
    op_query.add_argument('--cidr',
                          action='store',
                          help='IPv4 address in CIDR notation.',
                          required=True)

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

    _logger = logging.getLogger("rtbh-query/load_config")

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


def op_query(db_link, cidr):

    search_result = False

    db = db_link.cursor()

    # Query for all addresses within a queried CIDR range.
    sql = "SELECT address, isactive, firstadd, lastadd FROM netlist where address && '{}'".format(cidr)

    db.execute(sql)

    # Print something for each record that matches.
    for record in db:
        search_result = True
        print("{}".format(record[0]))
        print('=' * len(record[0]))
        print("  CIDR Active.: {}\n  First Add...: {}\n  Last Update.: {}".format(record[1], record[2], record[3]))

        # Check the block lists
        db2 = db_link.cursor()
        sql = "SELECT * FROM blocklist WHERE address = '{}'".format(record[0])
        db2.execute(sql)
        for record2 in db2:
            # Print a score value only if we have one.
            if float(record2[2]) > 0:
                print("  List........: {} / {}".format(record2[1], record2[2]))
            else:
                print("  List........: {}".format(record2[1]))
        db2.close()

        # Check the history list
        firstLine = True
        db2 = db_link.cursor()

        # Set Default SQL
        sql = "SELECT entrytime, entry FROM history WHERE address == '{}' ORDER BY entrytime DESC".format(record[0])

        # Change SQL if all the conditions are met.
        if 'query' in config:
            if ('timeZone' in config['query']) and ('timeFormat' in config['query']):
                sql = "SELECT to_char(entrytime AT TIME ZONE '{}', '{}')," \
                      " entry FROM history WHERE address = '{}'" \
                      " ORDER BY entrytime DESC".format(config['query']['timeZone'],
                                                        config['query']['timeFormat'],
                                                        record[0])

        db2.execute(sql)
        for record2 in db2:
            if firstLine:
                print()
                print("  History Entries")
                print("  ---------------")
                firstLine = False
            print("  {}: {}".format(record2[0], record2[1]))
        print()

    db.close()

    if not search_result:
        print("No results for {}.".format(cidr))


def op_summary(db_link, last):
    """
    This procedure prints out a summary of what is in the database along with the last number of history entries.

    :param db_link:
    :param last:
    :return:
    """
    db = db_link.cursor()

    print()
    print("RTBH Query Summary")
    print("------------------")

    sql = 'SELECT COUNT(*) from netlist'
    db.execute(sql)

    print("Host List Count: {}".format(db.fetchone()[0]))

    sql = 'SELECT COUNT(*) from blocklist'
    db.execute(sql)

    print("Block List Count: {}".format(db.fetchone()[0]))

    sql = 'SELECT processname FROM processes ORDER BY processname'
    db.execute(sql)

    processlist = {}
    processcount = 0

    print("\nBreakdown by Source\n-------------------")

    for record in db:
        processlist[processcount] = {}
        processlist[processcount]['name'] = record[0]
        db2 = db_link.cursor()
        sql = "SELECT COUNT(*) FROM blocklist WHERE source = '{}'".format(record[0])
        db2.execute(sql)
        processlist[processcount]['total'] = db2.fetchone()[0]

        # List only processes which have sources.
        if processlist[processcount]['total'] > 0:
            print("{:.<20}: {}\r".format(processlist[processcount]['name'], processlist[processcount]['total']))
        db2.close()

    print()

    if int(last):
        print("Last {} History Entries".format(last))
        print("-----------------------")

        # Set generic SQL
        sql = "SELECT entrytime, entry FROM history ORDER BY entrytime DESC LIMIT {}".format(last)

        # Change SQL if all the conditions are met.
        if 'query' in config:
            if ('timeZone' in config['query']) and ('timeFormat' in config['query']):
                sql = "SELECT to_char(entrytime AT TIME ZONE '{}', '{}')," \
                      " entry FROM history ORDER BY entrytime DESC LIMIT {}".format(config['query']['timeZone'],
                                                                                    config['query']['timeFormat'],
                                                                                    last)

        db.execute(sql)

        for record in db:
            print("  {}: {}".format(record[0], record[1]))

        print("-----------------------")

    db.close()

    return


if __name__ == "__main__":

    logger = logging.getLogger("rtbh-query")

    # Process CLI Arguments
    args = cli_args()

    # Load module configuration.  Exit if we can't find one.
    if not load_config("rtbh-config.yaml"):
        exit(1)

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

    # Open database as DB User
    try:
        db_link = psycopg2.connect(host=dbHost, port=dbPort, database=dbName, user=dbUserName, password=dbUserPass)
        db_link.autocommit = True
    except Exception as error:
        logger.error("Could not open database as user {}: {}".format(dbUserName, error))
        exit(2)

    # Perform our operations
    if vars(args)['operation'] == 'summary':
        op_summary(db_link, vars(args)['last'])
    elif vars(args)['operation'] == 'query':
        op_query(db_link, vars(args)['cidr'])

    # Close the database
    db_link.close()
