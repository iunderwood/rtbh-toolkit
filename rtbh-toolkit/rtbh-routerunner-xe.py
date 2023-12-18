#!/usr/bin/env python3

import requests.exceptions

from globals import *

# Internal Imports
import argparse
import datetime
import json
import logging
import time

# External Imports
import iupy
import pprint
import psycopg2
import restconf
import tqdm
import yaml
import yaml.scanner


def cli_args():
    """
    Process CLI Arguments and return the namespace.

    :return:
    """

    _logger = logging.getLogger("rtbh-routerunner-xe/cli_args")

    cli_parser = argparse.ArgumentParser(description="RTBH Route Runner XE v{}".format(version),
                                         epilog="Update IOS-XE RTBH Servers with the current database information.")
    cli_parser.add_argument('-d', '--debug',
                            action='store_true',
                            help="Enable script debugging.  This is a LOT of output.")
    cli_parser.add_argument('--router',
                            action='store',
                            default='ALL',
                            help="Update a single router as specified, otherwise process all of them.")
    cli_parser.add_argument('--unlock',
                            action='store',
                            default='ALL',
                            help="Unlock a crashed runner process by its ID, or all of them.")
    arguments = cli_parser.parse_args()

    if vars(arguments)['debug']:
        logging.basicConfig(level=logging.DEBUG)
        _logger.debug("Debug Logging Enabled")

    return arguments


def load_config(config_file):
    """
    Loads configuration and performs YAML processing on it.

    This will either populate, or add to the global configuration dictionary.

    :return:
    """

    global config

    _logger = logging.getLogger("rtbh-routerunner-xe/load_config")

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


def db_proc_check(db_link, ident):
    """
    This function checks the current status of a process and returns it.

    :param db_link:
    :param ident:
    :return:
    """

    log = logging.getLogger("rtbh-routerunner-xe/db_proc_check")
    db = db_link.cursor()

    log.debug("Checking for {} process.".format(ident))
    sql = "SELECT * from processes WHERE processname = 'RR-{}' LIMIT 1".format(ident)

    db.execute(sql)

    status = "UNLOCKED"

    try:
        row = db.fetchone()
    except Exception as error:
        log.error("Unable to query process: {}".format(error))
        db.close
        return "ERROR"

    if row is None:
        sql = "INSERT INTO processes (processname, status, runlast, runsuccess, runfailure) VALUES" \
              "('RR-{}', '{}', current_timestamp, 0, 0)".format(ident, status)
        db.execute(sql)
        log.debug("Added RR-{} to process list.".format(ident))
    else:
        status = row[1]
        log.debug("Process {} status: {}".format(row[0], row[1]))

    db.close()
    return status


def db_proc_lock(db_link, ident):
    """
    This function sets a lock on the routerunner process for a given identity.

    :param db_link:
    :param ident:
    :return:
    """
    log = logging.getLogger("rtbh-routerunner-xe/db_proc_lock")

    db = db_link.cursor()

    sql = "UPDATE processes SET runlast = current_timestamp, status = 'LOCKED' WHERE processname = 'RR-{}'".format(ident)
    db.execute(sql)
    db.close()

    log.debug("Locked RR-{} in database.".format(ident))


def db_proc_unlock(db_link, ident, success=True):
    """
    This function removes a lot on the routerunner process for a given identity.

    :param db_link:
    :param ident:
    :param success:
    :return:
    """
    log = logging.getLogger("rtbh-routerunner-xe/db_proc_unlock")

    db = db_link.cursor()

    sql = "UPDATE processes SET runlast = current_timestamp, status = 'UNLOCKED' WHERE processname = 'RR-{}'".format(ident)
    db.execute(sql)
    log.debug("Unlocked RR-{} in database.".format(ident))

    if success:
        sql = "UPDATE processes set runsuccess = runsuccess + 1 WHERE processname = 'RR-{}'".format(ident)
        log.debug("Incremented success counter.")
    else:
        sql = "UPDATE processes set runfailure = runfailure + 1 WHERE processname = 'RR-{}'".format(ident)
        log.debug("Incremented failure counter.")

    db.execute(sql)
    db.close()


def db_blocklist_get(db_link):
    log = logging.getLogger("rtbh-routerunner-xe/db_blocklist_get")

    db = db_link.cursor()
    block_list = {}

    sql = "SELECT address, STRING_AGG(source, '|') AS sources FROM blocklist GROUP BY address"
    db.execute(sql)

    log.debug("Loading full blocklist.")

    for row in db:
        block_list.update({row[0]: row[1]})

    db.close()

    log.debug("Blocklist length: {}".format(len(block_list)))

    return block_list


def restconf_fib_size(router, instance_name):
    """
    Get and return the general FIB size for a given instance.

    :param router:
    :param instance_name:
    :return:
    """
    log = logging.getLogger("rtbh-routerunner-xe/route_processor")

    response = router.get('data/Cisco-IOS-XE-fib-oper:fib-oper-data/fib-ni-entry/?fields=num-pfx;num-pfx-fwd;instance-name')
    if response.status_code == 200:
        fib_dict = json.loads(response.content)
    else:
        return None

    for instance in fib_dict['Cisco-IOS-XE-fib-oper:fib-ni-entry']:
        if instance['instance-name'] == instance_name:
            return instance['num-pfx']


def route_processor(db_link, entry, blocklist):
    """
    Process a given black hole router.

    :param db_link: Database Object
    :param entry: Router being worked on
    :param blocklist: Blocks
    :return:
    """
    log = logging.getLogger("rtbh-routerunner-xe/route_processor")

    # Check the process lock.  This make sure someone else isn't running a current update against this particular router.
    status = db_proc_check(db_link, entry['ident'])

    if status == "LOCKED":
        log.error("Database is locked for router {}.  Skipping this run.".format(entry['ident']))
        return
    else:
        db_proc_lock(db_link, entry['ident'])

    # Test Access
    router = restconf.RestConf()

    router_state = router.connect(transport='https',
                                  host=entry['ident'],
                                  un=config['routercred']['un'],
                                  pw=config['routercred']['pw'])

    if router_state is True:
        log.debug("RESTCONF connection established.")
    else:
        log.error("RESTCONF state returned: {}".format(router_state))
        db_proc_unlock(db_link, entry['ident'], False)
        return

    # Get the routes.
    print("* Acquiring static route list.")

    # Prepare for the next loop.
    get_attempts = 0
    get_success = False

    # Sometimes, getting a very large routing table reports errors.
    while not get_success:
        try:
            response = router.get("data/native/ip/route")
            get_success = True
        except requests.exceptions.ChunkedEncodingError as error:
            log.debug("Unable to get the resource: {}".format(error))
            print("ChunkedEncdingError during retrieval.")
            db_proc_unlock(db_link, entry['ident'], False)
            get_success = False
            get_attempts += 1

        if get_attempts > 4 and get_success is False:
            log.error("Giving up on this run.  Try again later.")
            return
        elif get_success is False:
            print("Retrying ...")
            time.sleep(1)

    # Work with what we have managed to retrieve.
    if response.status_code == 204:
        log.debug("The routing table is empty.")
        route_dict = {}
    elif response.status_code == 200:
        log.debug("The routing table is found.")
        if response.content is not None:
            route_dict = json.loads(response.content)
        else:
            route_dict = {}

    print("* Preparing base route list.")
    # Clear all routes except for the named base.
    route_list_len = len(route_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'])
    i = 0
    while i < route_list_len:
        route_entry = route_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'][i]

        # Leave any kind of base route alone.
        if config['routerunner']['tags']['basename'] in route_entry['fwd-list'][0]['name']:
            log.debug("Default Entry: {}".format(route_entry['prefix']))
            i += 1

        # Pop the non-base route from the list.
        else:
            # log.debug("Non-Default Entry: {}".format(route_entry['prefix']))
            route_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'].pop(i)
            # Decrement total counter after pop
            route_list_len -= 1

    # Replace the exisiting static route list with the default list.
    print("* Setting base routes.")

    # One does not simply replace the routing table on a large blocklist collection.
    patched = False
    while not patched:
        try:
            response = router.put("data/native/ip/route", route_dict)
        except requests.exceptions.ChunkedEncodingError as error:
            print("  ChunkedEncodingError.")
            time.sleep(5)
            continue

        if response.status_code == 204:
            log.debug("Default placement successful!")
            patched = True

        # The rest deals with fussy routers which have a tendency to time out.
        elif response.status_code == 504:
            print("  Base route state still running.  Please wait.")
            log.debug("Gateway timeout.  This could take awhile.")
            fib_init = restconf_fib_size(router, "IPv4:Default")
            fib_last = fib_init
            log.debug("Initial FIB Size: {}".format(fib_init))
            time.sleep(15)

            fib_done = False
            while not fib_done:
                fib_current = restconf_fib_size(router, "IPv4:Default")

                if fib_current is not None:
                    if fib_current == fib_init:
                        log.debug("Cleanup hasn't started yet.  Waiting 30s,")
                        time.sleep(30)
                    elif fib_current < fib_last:
                        log.debug("Prefix decremented: {} < {}".format(fib_current, fib_last))
                        time.sleep(5)
                    elif fib_current == fib_last:
                        log.debug("Final Count: {}".format(fib_current))
                        fib_done = True
                    fib_last = fib_current

                else:
                    log.debug("Unable to get a FIB count.  Retry in 5.")
                    time.sleep(5)

        # Give up on all other 500-series errors.
        else:
            log.error("Received an unexpected response code from the router: {}".format(response.status_code))
            log.error(response.text)
            db_proc_unlock(db_link, entry['ident'], False)
            return

    # Patch in the block list.

    routes_dict = {}
    routes_dict['Cisco-IOS-XE-native:route'] = {}
    routes_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'] = []
    record_counter = 0

    # Populate a tag list.
    tag_list = {}
    for item in config['listrunner']['lists']:
        if 'tag' in item:
            source = 'LR-{}'.format(item['ident'])
            tag_list[source] = item['tag']
            log.debug("Tag List: {} / {}".format(source, item['tag']))

    # Cycle the block list
    batch_counter = 1
    route_counter = 0

    if logging.root.level != logging.DEBUG:
        print("{} Deployment - Batch Size: {}".format(entry['ident'], config['routerunner']['limits']['patchcount']))
        progress_bar = tqdm.tqdm(total=len(blocklist.items()), desc=' Routes')

    for block_addr, block_src in blocklist.items():

        # Reset the route dictionary if the tally is zero.
        if record_counter == 0:
            routes_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'].clear()

        entry_dict = {}
        entry_dict['fwd-list'] = []
        entry_dict['fwd-list'].append(0)
        entry_dict['fwd-list'][0] = {}
        entry_dict['fwd-list'][0]['fwd'] = "Null0"
        entry_dict['fwd-list'][0]['name'] = "{}".format(block_src)

        # Add the tag from the given source.
        if block_src in tag_list:
            entry_dict['fwd-list'][0]['tag'] = tag_list[block_src]

        # Apply the default tag if unspecified, or an IP has multiple sources.
        else:
            if 'default' in config['routerunner']['tags']:
                entry_dict['fwd-list'][0]['tag'] = config['routerunner']['tags']['default']

        ip_record = block_addr.split('/')
        entry_dict['prefix'] = ip_record[0]
        entry_dict['mask'] = iupy.v4_bits_to_mask(ip_record[1])

        log.debug("Adding {} / {} / {}".format(ip_record[0], ip_record[1], block_src))

        routes_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'].append(record_counter)
        routes_dict['Cisco-IOS-XE-native:route']['ip-route-interface-forwarding-list'][record_counter] = entry_dict

        route_counter += 1
        record_counter += 1

        if record_counter % config['routerunner']['limits']['patchcount'] == 0:
            log.debug("Applying batch {}".format(batch_counter))

            patched = False
            while not patched:
                response = router.patch("data/native/ip/route", routes_dict)
                if response.status_code == 204:
                    log.debug("Batch Update Successful")
                    patched = True
                    record_counter = 0
                    batch_counter += 1
                else:
                    # Retry.
                    log.debug("Retrying batch ...")

                log.debug("Wait a second.")
                time.sleep(1)

        if logging.root.level != logging.DEBUG:
            progress_bar.update(1)

    # Apply the final patch round.
    if record_counter % config['routerunner']['limits']['patchcount'] != 0:
        log.debug("Applying Final batch {}".format(batch_counter))
        response = router.patch("data/native/ip/route", routes_dict)
        if response.status_code == 204:
            log.debug("Final Batch Update Successful")

    log.debug("Final Route Count: {}".format(route_counter))

    # Close the progress bar.
    if logging.root.level != logging.DEBUG:
        progress_bar.close()

    # pprint.pprint(routes_dict)

    # Save the configuration
    response = router.post("operations/cisco-ia:save-config", None)

    if response.status_code == 200:
        print("* Configuration saved successfully!")

    # Unlock the database and increment the success counter.
    db_proc_unlock(db_link, entry['ident'], True)

    return


if __name__ == "__main__":
    logger = logging.getLogger("rtbh-routerunner")

    # Process CLI arguments
    args = cli_args()
    router = vars(args)['router']

    # Load module configuration.
    if not load_config("rtbh-config.yaml"):
        print("FATAL: Required configration file rtbh-config.yaml not found.")
        exit(1)

    # Load router credentials.
    if not load_config("routercreds.yaml"):
        logger.error("FATAL: Required configuration file routercreds.yaml not found.")
        exit(2)

    # Assign variables from configuration
    try:
        dbHost = config['database']['dbHost']
        dbPort = config['database']['dbPort']
        dbName = config['database']['dbName']
        dbUserName = config['database']['dbUserName']
        dbUserPass = config['database']['dbUserPass']
    except KeyError as error:
        logger.error("FATAL: Required configuration element {} missing.".format(error))
        exit(1)

    print("RTBH Route Runner")
    print("=================")

    # Section Check
    if 'routerunner' not in config:
        print("FATAL: No routerunner section configured.")
        exit(1)

    if 'routers' in config['routerunner']:
        if router == "ALL":
            print("{} routers configured.".format(len(config['routerunner']['routers'])))
        else:
            router_found = False
            for entry in config['routerunner']['routers']:
                if entry['ident'] == router:
                    print("Router ID {} Found: {}".format(entry['ident'], entry['descr']))
                    router_found = True
                    break
            if not router_found:
                print("FATAL: Router ID {} Not Found".format(router))
                exit(1)
    else:
        print("FATAL: No routers configured.")
        exit(1)

    if 'routercred' not in config:
        print("FATAL: No routercred section configured.")
        exit(1)

    if 'un' not in config['routercred'] or 'pw' not in config['routercred']:
        print("FATAL: Both un / pw need are required under routercred configuration.")

    # Note our starting time.
    startTime = datetime.datetime.now()

    # Open up the database for business.
    try:
        db_link = psycopg2.connect(host=dbHost, port=dbPort, database=dbName, user=dbUserName, password=dbUserPass)
        db_link.autocommit = True
        logger.debug("Database {} open".format(dbName))
    except Exception as error:
        logger.error("Could not open database: {}".format(error))
        exit(2)

    # Acquire the block list
    blocklist = db_blocklist_get(db_link)

    # Router Loop
    for entry in config['routerunner']['routers']:
        if router == "ALL" and 'auto' in entry:
            print("Processing {}".format(entry['ident']))
            route_processor(db_link, entry, blocklist)
        elif entry['ident'] == router:
            print("Processing {}".format(entry['ident']))
            route_processor(db_link, entry, blocklist)
        else:
            print("Not processing {}".format(entry['ident']))

    # Note our ending time.
    endTime = datetime.datetime.now()

    # Print out the timer information for the summary.
    print()
    print("Route Runner Summary")
    print("------------")
    print("Start time.: {}".format(startTime))
    print("End time...: {}".format(endTime))
    print("------------")