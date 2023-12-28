#!/usr/bin/env python3

from globals import *

# Internal Imports
import argparse
import csv
import datetime
import io
import ipaddress
import logging
import os
import re
import ssl
import time

# External Imports
import certifi
import iupy
import psycopg2
import tqdm
import urllib.error
import urllib.request
import yaml
import yaml.scanner


def cli_args():
    """
    Process CLI Arguments and return the namespace.

    :return:
    """

    _logger = logging.getLogger("rtbh-listrunner/cli_args")

    cli_parser = argparse.ArgumentParser(description="RTBH List Runner v{}".format(version),
                                         epilog="Retrieve blacklists and update the backend database.")
    cli_parser.add_argument('-d', '--debug',
                            action='store_true',
                            help="Enable script debugging.  This is a LOT of output.")
    cli_parser.add_argument('--skip-write',
                            action='store_true',
                            help="Look through the lists and changes, but do not commit to the database.")
    cli_parser.add_argument('--list',
                            action='store',
                            default='ALL',
                            help="Processes a list by its ID, otherwise, process everything.")
    cli_parser.add_argument('--unlock',
                            action='store',
                            default='ALL',
                            help="Unlock a crashed process by its ID, or all of them.")
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

    _logger = logging.getLogger("rtbh-listrunner/load_config")

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

    log = logging.getLogger("rtbh-listrunner/db_proc_check")
    db = db_link.cursor()

    log.debug("Checking for {} process.".format(ident))
    sql = "SELECT * from processes WHERE processname = 'LR-{}' LIMIT 1".format(ident)

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
              "('LR-{}', '{}', current_timestamp, 0, 0)".format(ident, status)
        db.execute(sql)
        log.debug("Added LR-{} to process list.".format(ident))
    else:
        status = row[1]
        log.debug("Process {} status: {}".format(row[0], row[1]))

    db.close()
    return status


def db_proc_lock(db_link, ident):
    """
    This function sets a lock on the listrunner process for a given identity.

    :param db_link:
    :param ident:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_proc_lock")

    db = db_link.cursor()

    sql = "UPDATE processes SET runlast = current_timestamp, status = 'LOCKED' WHERE processname = 'LR-{}'".format(ident)
    db.execute(sql)
    db.close()

    log.debug("Locked LR-{} in database.".format(ident))


def db_proc_unlock(db_link, ident, success=True):
    """
    This function removes a lot on the listrunner process for a given identity.

    :param db_link:
    :param ident:
    :param success:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_proc_unlock")

    db = db_link.cursor()

    sql = "UPDATE processes SET runlast = current_timestamp, status = 'UNLOCKED' WHERE processname = 'LR-{}'".format(ident)
    db.execute(sql)
    log.debug("Unlocked LR-{} in database.".format(ident))

    if success:
        sql = "UPDATE processes set runsuccess = runsuccess + 1 WHERE processname = 'LR-{}'".format(ident)
        log.debug("Incremented success counter.")
    else:
        sql = "UPDATE processes set runfailure = runfailure + 1 WHERE processname = 'LR-{}'".format(ident)
        log.debug("Incremented failure counter.")

    db.execute(sql)
    db.close()


def db_netlist(db_link, addr_mask, status):
    """
    This procedure adds or modifies a record in the netlist table and setting the Active boolean value as required.

    :param db_link:
    :param addr_mask:
    :param status:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_netlist")

    db = db_link.cursor()

    if status == "ACTIVE":
        sql = "INSERT INTO netlist (address, isactive) VALUES ('{}', TRUE) " \
              "ON CONFLICT (address) DO UPDATE SET lastadd = current_timestamp, isactive = TRUE".format(addr_mask)
    else:
        sql = "INSERT INTO netlist (address, isactive) VALUES ('{}', FALSE) " \
              "ON CONFLICT (address) DO UPDATE SET lastadd = current_timestamp, isactive = FALSE".format(addr_mask)

    try:
        db.execute(sql)
        log.debug("Hostlist Entry: {} / {}".format(addr_mask, status))
    except Exception as error:
        log.error("Hostlist Entry Failed: {}".format(error))

    db.close()


def db_blocklist_add(db_link, ident, addr_mask, score):
    """
    This function adds a address record to a the block list for a given identifier along with its score.

    :param db_link:
    :param ident:
    :param addr_mask:
    :param score:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_blocklist_add")

    db = db_link.cursor()

    sql = "INSERT INTO blocklist (address, source, score) VALUES ('{}', 'LR-{}', '{}')" \
          "ON CONFLICT (address, source) DO UPDATE SET lastadd = current_timestamp, " \
          "score = '{}'".format(addr_mask, ident, float(score), float(score))

    try:
        db.execute(sql)
        log.debug("Blocklist Add: {}-{} ({})".format(ident, addr_mask, score))
    except Exception as error:
        log.error("Blocklist Add Failed: {}".format(error))

    db.close()


def db_blocklist_delete(db_link, ident, addr_mask):
    """
    This function removes a particular address record from a blocklist of a given identity.

    :param db_link:
    :param ident:
    :param addr_mask:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_blocklist_delete")

    db = db_link.cursor()

    sql = "DELETE FROM blocklist WHERE address = '{}' AND source = 'LR-{}'".format(addr_mask, ident)

    try:
        db.execute(sql)
        log.debug("Blocklist Remove: {}-{}".format(ident, addr_mask))
    except Exception as error:
        log.error("Blocklist Remove Failed: {}".format(error))

    db.close()


def db_blocklist_select(db_link, ident):
    """
    This function select and returns the value of a block list based on the source where the IP address is the key and
    the score is the value.

    :param db_link:
    :param ident:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_blocklist_select")

    db = db_link.cursor()
    block_list = {}

    sql = "SELECT address, score FROM blocklist WHERE source = 'LR-{}'".format(ident)
    db.execute(sql)

    log.debug("Loading blocklist attributed to {}".format(ident))

    for row in db:
        block_list.update({row[0]: row[1]})

    db.close()

    log.debug("Blocklist length for {}: {}".format(ident, len(block_list)))

    return block_list


def db_blocklist_count(db_link, addr_mask):
    """
    This function returns the number of block lists a given address record is a part of, since an address can appear in
    more than one list.

    :param db_link:
    :param addr_mask:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_blocklist_count")

    db = db_link.cursor()

    sql = "SELECT COUNT (*) FROM blocklist WHERE address = '{}';".format(addr_mask)
    db.execute(sql)

    count = db.fetchone()[0]

    log.debug("Entry count: {}".format(count))

    return count


def db_history_add(db_link, ident, addr_mask, operation, notes):
    """
    This function adds an entry to the history table.  Ideally, this should be used for any adds or deletes to a
    block list, or to note any changes to a score used in a record.

    :param db_link:
    :param ident:
    :param addr_mask:
    :param operation:
    :param notes:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/db_history_add")

    db = db_link.cursor()

    sql = "INSERT INTO history (address, source, action, entry) VALUES ('{}', 'LR-{}', '{}', '{}')". \
        format(addr_mask, ident, operation, notes)

    try:
        db.execute(sql)
        log.debug("Added History Log: {}".format(notes))
    except Exception as error:
        log.error("Unable to add history: {}".format(error))

    db.close()


def process_content_v4hostmask(content):
    """
    Process raw text contatining v4 hosts w/ bitmasks.  Return a host list.

    :param content:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/process_content_v4hostmask")

    # Set up initial variables
    v4_regex = re.compile('^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\/(3[0-2]|[1-2][0-9]|[0-9])$')
    line_counter = 0
    hostmask_dict = dict()

    # Split the data into lines
    content_data = content.splitlines()

    # Let's loop!
    for line in content_data:
        if v4_regex.match(line):
            hostmask_dict.update({line: 0})
        else:
            log.debug("Invalid line data: {}: {}".format(line_counter, line))
        line_counter += 1

    log.debug("Total lines in file: {}".format(line_counter))

    return hostmask_dict


def process_content_v4host(content):
    """
    Process raw text containing v4 hosts only.  Return a list of hosts.

    :param content:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/process_content_v4host")

    # Set up initial variables
    v4_regex = re.compile('^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
    line_counter = 0
    hostmask_dict = dict()

    # Split the data into lines
    content_data = content.splitlines()

    # Let's loop!
    for line in content_data:
        host_mask = "{}/32".format(line)
        if v4_regex.match(line):
            hostmask_dict.update({host_mask: 0})
        else:
            log.debug("Invalid line data: {}: {}".format(line_counter, line))
        line_counter += 1

    log.debug("Total lines in file: {}".format(line_counter))

    return hostmask_dict


def process_content_csv(content, entry):
    """
    This list processes content that's in a CSV format.

    :param content:
    :param entry:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/process_content_csv")

    hostmask_dict = {}

    # Default Booleans
    return_empty = True

    cat_op = "CONTAINS"
    cat_criteria = ""
    cat_check = False
    score_check = False
    score_threshold = 0

    # Check configured parameters for the CSV
    if 'csv' in entry:
        if 'field_addr' in entry['csv']:
            csv_addr = entry['csv']['field_addr']
            log.debug("CSV Column for IP: {}".format(csv_addr))
            return_empty = False

        if 'field_category' in entry['csv']:
            csv_cat = entry['csv']['field_category']
            log.debug("CSV Column for Category: {}".format(csv_cat))
            if 'category' in entry:
                if 'operator' in entry['category'] and 'criteria' in entry['category']:
                    cat_op = entry['category']['operator']
                    cat_criteria = entry['category']['criteria']
                    log.debug("Categry Check Enabled!")
                    cat_check = True

        if 'field_score' in entry['csv']:
            csv_score = entry['csv']['field_score']
            log.debug("CSV Column for Score: {}".format(csv_score))
            if 'score' in entry:
                if 'lwm' in entry['score']:
                    score_check = True
                    log.debug("Score Check Enabled")
                    score_threshold = entry['score']['lwm']

    if return_empty:
        log.debug("No address field identified.  Returning empty dictionary.")
        return hostmask_dict

    # Content is already loaded, but we'll be working the CSV like a file.
    csv_file = io.StringIO(content)

    row_counter = 0

    with csv_file as csv_read:

        # If we have headers defined for a given CSV, we'll load them.
        if 'headers' in entry['csv']:
            csv_data = csv.DictReader(csv_read, fieldnames=entry['csv']['headers'])
        else:
            csv_data = csv.DictReader(csv_read, skipinitialspace=True)

        # Process each CSV line.
        for row in csv_data:

            # Make sure the csv_addr field is in place, and add a host netmask if there is no mask specified.
            try:
                if "/" not in row[csv_addr]:
                    host_addr = "{}/32".format(row[csv_addr])
                else:
                    host_addr = row[csv_addr]
            except KeyError as error:
                log.error("Invalid field specified: {}".format(error))
                return

            host_score = 0

            # Category checks will skip to the next item in the loop if the match is proper.

            if cat_check:
                # Category from the row is equal to the specified criteria.
                if cat_op == "equals":
                    if not str(cat_criteria) == str(row[csv_cat]):
                        continue

                # Configured criteria is the haystack, which the row category must be found in.
                elif cat_op == "haystack":
                    if not str(row[csv_cat]) in str(cat_criteria):
                        continue

                # Configured criteria is the needle, found as part of the row category.
                elif cat_op == "needle":
                    if not str(cat_criteria) in str(row[csv_cat]):
                        continue

                #
                else:
                    log.debug("Unknown category operation: {}".format(cat_op))

            if score_check:
                try:
                    host_score = row[csv_score]
                except KeyError as error:
                    log.error("Invalid score field specified: {}".format(error))

                if not float(row[csv_score]) > float(score_threshold):
                    continue

            # log.debug("CSV Row: {} / {} / {}".format(host_addr, host_score, row[csv_cat]))
            hostmask_dict.update({host_addr: host_score})
            row_counter +=1;

    log.debug("CSV Rows Adopted: {}".format(row_counter))

    return hostmask_dict


def get_by_file(file_name):
    """
    This function just opens and reads the data from a file.

    :param file_name:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/get_by_file")

    try:
        file = open(file_name, "r")
        file_content = file.read()
        file.close()
        log.debug("Successfully loaded {}.".format(file_name))
    except Exception as error:
        log.error("Unable to read {}: {}".format(file_name, error))
        file_content = ""

    return(file_content)


def get_by_url(entry):
    """
    This function returns raw data from a URL, or its cached file if the file is within expiry.

    :param entry:
    :return:
    """
    global config

    log = logging.getLogger("rtbh-listrunner/get_by_url")

    # Set caching parameters
    if 'cache' in config['listrunner']:

        # Set a file directory for the cache.
        if 'location' in config['listrunner']['cache']:
            file_directory = config['listrunner']['cache']['location']
        else:
            file_directory = None
        log.debug("Cache directory set to {}".format(file_directory))

        # Set an aging time for the cache.
        if 'age' in config['listrunner']['cache']:
            file_max_age = config['listrunner']['cache']['age']
        else:
            file_max_age = 300
        log.debug("Cache timer set to {} seconds.".format(file_max_age))

    else:
        log.debug("Caching configuration not found.  Applying default")
        file_directory = None
        file_max_age = 300

    # Set the cache filename.
    cache_file = "cache-{}.txt".format(entry['ident'])

    if file_directory is not None:
        cache_file = "{}/{}".format(file_directory, cache_file)

    log.debug("Cache file is {}".format(cache_file))

    # Assume we need to get the file.
    get_file = True

    # Check for the file, and set get_file to false only if there is an unexpired cache.
    if os.path.isfile(cache_file):
        log.debug("Cache file found.")
        file_delta = time.time() - os.path.getmtime(cache_file)
        if file_delta > file_max_age:
            log.debug("Cache file is old.  {} seconds.".format(file_delta))
        else:
            log.debug("Cache file has not expired.  {} < {}".format(file_delta, file_max_age))
            get_file = False
    else:
        log.debug("Cache file not found.")

    # Get the text data from the URL and save it locally.
    if get_file is True:
        log.debug("Acquiring file for {}.".format(entry['ident']))

        raw_data = ""

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        # A URL grab might not be successful.
        try:
            url_response = urllib.request.urlopen(entry['url'], context=ssl_context)
        except urllib.error.HTTPError as error:
            print("Unable to acquire list: {}".format(error))
            return

        with url_response as r:
            raw_data += r.read().decode()

        try:
            cache_write = open(cache_file, "w")
            cache_write.write(raw_data)
            cache_write.close()
        except FileNotFoundError as error:
            log.error("Unable to write cache: {}".format(error))
        except PermissionError as error:
            log.error("No permission to write cache: {}".format(error))

    # Load in the content by the file.
    content = get_by_file(cache_file)
    log.debug("Content length: {} bytes.".format(len(content)))

    return content


def list_processor(db_link, entry):
    """
    This function processes a block list for a given entry.

    :param db_link:
    :param entry:
    :return:
    """
    log = logging.getLogger("rtbh-listrunner/list_processor")

    list_notes = ''

    #
    # List Readiness
    #

    # Check the process lock.  This make sure someone else isn't running a current update against this particular list.
    status = db_proc_check(db_link, entry['ident'])

    if status == "LOCKED":
        log.error("Database is locked for list {}.  Skipping this run.".format(entry['ident']))
        return
    else:
        db_proc_lock(db_link, entry['ident'])

    # Acquire the raw data.
    if 'url' in entry:
        log.debug("List {} by URL: {}".format(entry['ident'], entry['url']))
        raw_content = get_by_url(entry)
    elif 'file' in entry:
        log.debug("List {} by File: {}".format(entry['ident'], entry['file']))
        raw_content = get_by_file(entry['file'])
    else:
        log.error("Entry {} must contain a url or file identifier.")
        return

    if raw_content is None:
        log.error("Content block is empty for this list.")
        db_proc_unlock(db_link, entry['ident'], False)
        return

    # Acquire the host list based upon its configured type.
    if 'type' in entry:
        if entry['type'] == 'v4_host':
            list_dict = process_content_v4host(raw_content)
        elif entry['type'] == 'v4_host_mask':
            list_dict = process_content_v4hostmask(raw_content)
        elif entry['type'] == 'csv':
            list_dict = process_content_csv(raw_content, entry)
        else:
            log.error("Entry type {} unrecognized.".format(entry['type']))
            db_proc_unlock(db_link, entry['ident'], False)
            return
    else:
        log.error("Entry {} must contain a compatible list type.")
        db_proc_unlock(db_link, entry['ident'], False)
        return

    if len(list_dict) == 0:
        log.error("List dictionary is blank.  This could be a problem.")

    # Get the current block list
    block_dict = db_blocklist_select(db_link, entry['ident'])

    # Are we doing any score evaluation with the given list entry?
    score_eval = False
    if 'score' in entry:
        if "lwm" in entry['score'] and "hwm" in entry['score']:
            score_eval = True
            score_lwm = entry['score']['lwm']
            score_hwm = entry['score']['hwm']

    log.debug("Running {} List Loop".format(entry['ident']))

    #
    # Block Loop Begins
    #

    # Block/Add Progress Bar
    if logging.root.level != logging.DEBUG:
        print("List: {} ({})".format(entry['ident'], len(list_dict)))
        progress_bar = tqdm.tqdm(total=len(list_dict), desc=' Block/Add')

    counter_add = 0
    counter_update = 0
    counter_delete = 0

    # Loop through the active block dictionary.
    for list_item in list_dict:

        # Prep for exclusion checks.
        exclusion_continue = False

        # Check exclusions: Exact List
        try:
            if list_item in config['listrunner']['exclude']['exact']:
                exclusion_continue = True
        except Exception as error:
            log.debug("Exception check failed: {}".format(error))

        # Check exclusions: Subnet List
        try:
            for within_item in config['listrunner']['exclude']['within']:
                if ipaddress.ip_network(list_item).subnet_of(ipaddress.ip_network(within_item)):
                    exclusion_continue = True
        except Exception as error:
            log.debug("Exception check failed: {}".format(error))

        # If we have an exclusion, skip to the next entry in the loop
        if exclusion_continue is True:
            log.debug("Address {} found in exclusion subnets.")
            if logging.root.level != logging.DEBUG:
                progress_bar.update(1)
            continue

        # If an entry is in the block list, evaluate and update.
        if list_item in block_dict:

            # Evaluate scores against a configured low watermark (lwn) and high watermark (hwm).
            if score_eval:

                # Evaluate if the item is greater than the low water mark / minimum score.
                if float(list_dict[list_item]) > float(score_lwm):
                    log.debug("Address {} already in {} w/ score: {}".format(list_item, entry['ident'],
                                                                             list_dict[list_item]))
                    # db_hostlist(db_link, list_item, "ACTIVE")
                    # db_blocklist_add(db_link, entry['ident'], list_item, list_dict[list_item])

                    # Log if the score has changed.
                    if not float(list_dict[list_item]) == float(block_dict[list_item]):
                        log.debug("Score change: {} from {}".format(list_dict[list_item], block_dict[list_item]))

                        # Update blocklist with new score.
                        db_blocklist_add(db_link, entry['ident'], list_item, list_dict[list_item])

                        # Update the history log entry for the score.
                        history_string = "source={}, action=UPDATE, host={}, score={}".format(entry['ident'],
                                                                                              list_item,
                                                                                              list_dict[list_item])
                        db_history_add(db_link, entry['ident'], list_item, "UPDATE", history_string)

                        counter_update += 1

                # Remove from the list if the item is now under the low water mark / minimum score.
                elif float(list_dict[list_item]) < float(score_lwm):
                    log.debug("Address {} score {} is scored below {}.".format(list_item,
                                                                               list_dict[list_item],
                                                                               score_lwm))

                    # Pop from the list and it will be dropped on the cleanup loop.
                    list_dict.pop(list_item)

            # Make a debug note if we're already blocked.
            else:
                log.debug("Address {} already in {}".format(list_item, entry['ident']))

        # if an entry is not in the block list, add to it.
        else:
            log.debug("Address {} not in {}".format(list_item, entry['ident']))

            if score_eval:
                # Don't add a address if the score is too low.
                if float(list_dict[list_item]) < float(score_hwm):
                    log.debug("Address {} score {} is scored below {}.".format(list_item,
                                                                               list_dict[list_item],
                                                                               score_hwm))
                    if logging.root.level != logging.DEBUG:
                        progress_bar.update(1)
                    continue

            # Update the Host List
            db_netlist(db_link, list_item, "ACTIVE")

            # Update the block list
            db_blocklist_add(db_link, entry['ident'], list_item, list_dict[list_item])

            # Update our history logs.
            history_string = "source={}, action=ADD, host={}".format(entry['ident'], list_item)

            # Append the score if we have one.
            if float(list_dict[list_item]) > 0:
                history_string += ", score={}".format(list_dict[list_item])

            db_history_add(db_link, entry['ident'], list_item, "ADD", history_string)

            # Add to the blocklist dictionary, so it doesn't get deleted in the next check.
            block_dict.update({list_item: 0})

            counter_add += 1

        # Update the progress bar before finishing out the loop.
        if logging.root.level != logging.DEBUG:
            progress_bar.update(1)

    # Close the progress bar.
    if logging.root.level != logging.DEBUG:
        progress_bar.close()

    #
    # Cleanup Loop Begins
    #

    log.debug("Running {} Block Loop".format(entry['ident']))

    # Cleanup Progress Bar
    if logging.root.level != logging.DEBUG and len(block_dict) > 0:
        progress_bar = tqdm.tqdm(total=len(block_dict), desc=' Cleanup  ')

    # Loop block list against current entries.
    for block_item in block_dict:

        # If the block item is in the current list, there's nothing more to do in this loop.
        if block_item in list_dict:
            pass

        # If the block item is *not* in the current list, remove from the block list, and update the hostlist if applicable.
        else:
            log.debug("Address {} is not on the {} block list.".format(block_item, entry['ident']))

            # Remove from the block list.
            db_blocklist_delete(db_link, entry['ident'], block_item)

            counter_delete += 1

            # Change the hostlist only if there are no entries in the block list.
            bl_counter = db_blocklist_count(db_link, block_item)

            if bl_counter == 0:
                log.debug("Entry is in no other lists.")
                db_netlist(db_link, block_item, "INACTIVE")
            else:
                if bl_counter == 1:
                    log.debug("Entry is in {} other list.".format(bl_counter))
                else:
                    log.debug("Entry is in {} other lists.".format(bl_counter))

            # Update our history logs.
            history_string = "source={}, action=DELETE, host={}".format(entry['ident'], block_item)
            db_history_add(db_link, entry['ident'], block_item, "ADD", history_string)

        # Update the progress bar before finishing out the loop.
        if logging.root.level != logging.DEBUG:
            progress_bar.update(1)

    # Close out the progress bar.
    if logging.root.level != logging.DEBUG:
        progress_bar.close()

    # Unlock the database and increment the success counter.
    db_proc_unlock(db_link, entry['ident'], True)

    print(" Add/Del..: {} / {}".format(counter_add, counter_delete))
    if counter_update > 0:
        print(" Updates..: {}".format(counter_update))

    return


if __name__ == "__main__":
    logger = logging.getLogger("rtbh-listrunner")

    # Process CLI arguments
    args = cli_args()
    list = vars(args)['list']

    # Load module configuration.
    if not load_config("rtbh-config.yaml"):
        print("FATAL: Required configration file rtbh-config.yaml not found.")
        exit(1)

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

    print("RTBH List Runner")
    print("================")

    # Section Check
    if 'listrunner' not in config:
        print("FATAL: No listrunner section configured.")
        exit(1)

    # Check for the lists.  Exit if necessary.
    if 'lists' in config['listrunner']:
        if list == "ALL":
            print("{} Lists Configured.  Processing 'auto' lists only.".format(len(config['listrunner']['lists'])))
        else:
            list_found = False
            for entry in config['listrunner']['lists']:
                if entry['ident'] == list:
                    print("List ID {} Found: {}".format(entry['ident'], entry['descr']))
                    list_found = True
                    break
            if not list_found:
                print("FATAL: List ID {} Not Found".format(list))
                exit(1)
    else:
        logger.error("FATAL: No lists configured for processing.")
        exit(1)

    print()

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

    # List Loop!
    logger.debug("Starting List Loop")
    for entry in config['listrunner']['lists']:
        if list == "ALL" and 'auto' in entry:
            logger.debug("Processing {}".format(entry['ident']))
            list_processor(db_link, entry)
        elif entry['ident'] == list:
            logger.debug("Processing {}".format(entry['ident']))
            list_processor(db_link, entry)
        else:
            logger.debug("Not processing {}".format(entry['ident']))

    # Close the database
    db_link.close()
    logger.debug("Database closed.")

    # Note our ending time.
    endTime = datetime.datetime.now()

    # Print out the timer information for the summary.
    print()
    print("List Runner Summary")
    print("------------")
    print("Start time.: {}".format(startTime))
    print("End time...: {}".format(endTime))
    print("------------")
