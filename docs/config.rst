Configuration
=============

This sections describes the sections that make up the YAML file which contains the parameters of the toolkit: rtbh-config.yaml

This system assumes there will be two different versions of the configuration.  The service-account version will exist in the home directory of the service account.  The read-only version will exist in ``/usr/local/etc``

Database Section
----------------

The first section of the YAML contains the important database information that is required to access the database which stores the RTBH information.  This file should be read/write by the owner only.

.. code-block:: yaml

    # Common Database Information
    database:
      dbHost: postgres.example.com
      dbPort: 5432
      dbName: rtbhdb
      dbUserName: rtbh_rw
      dbUserPass: rtbh_writepass

If there is a read-only version used system-wide, it should have a configuration with the database read-only account.

.. code-block:: yaml

    # Common Database Information
    database:
      dbHost: postgres.example.com
      dbPort: 5432
      dbName: rtbhdb
      dbUserName: rtbh_ro
      dbUserPass: timeToReadMe123!


Listrunner Section
------------------

This section is required in the configuration used by the read-write account.  This section contains the information about the lists that are used to populate the RTBH system.

.. code-block:: yaml

    listrunner:
      cache:
        location: /tmp
        age: 7000
      lists:
        - ident: STATIC
          descr: Static Network Block List
          file: /usr/local/etc/static.txt
          type: v4_host_mask
          tag: 6661
          auto:

cache
^^^^^

As the listrunner is often charged with pulling updates from an online source, there is a section which defines where and for how long a cache file may be maintained before being considered too old.

The name of the cache file will be based on the identifier used.

lists
^^^^^

The following list types are supported:

The **v4_host** list type is a list of host IPs without a subnet mask defined.  These are assumed to be /32 entries.  The TOR Exit Node list the 3CoreSec Blacklist use a v4_host list.

The **v4_host_mask** list type is a list of subnets with the mask in bits.  These are exact entries and are the format of the Team Cymru IPv4 BOGON list, and the recommended format for a locally-maintained block list.

Valid lines include an IPv4 host/mask combination.  Notes may be provided on commented lines if necessary.

The **csv** or comma-separated value type is the most common simple table format.  The first row is generally a header with a number of fields defined.  These kinds of files are often found with threat intelligence feeds (e.g. ProofPoint Emerging Threats, REN-ISAC).  In addition to the IP address identified, there is often a section for a category and a threat score.

Routerunner Section
-------------------

This section is in the read-write section only, and contains the router list and required parameters to support router changes:

.. code-block:: yaml

    routerunner:
      routers:
        - ident: TESTCSR01
          descr: Lab CSR-1000v
          auto:
      limits:
        runsec: 3200
        patchcount: 300
      method: restconf
      tags:
        basename: DEFAULT
        default: 6660

For the routerunner to work properly, there must be a routercreds.yaml file in the executing user's home directory.  This file must be only accessible by the owner, as it contains the credential required to configure the destination runner.

.. code-block:: yaml
   :caption: routecreds.yaml - in user home directory, permissions 600.

    ---
    routercred:
      un: svc-rtbh
      pw: rtbhServicePW918!
    ...

This approach was taken for this module because it is the most accessible.

Query Section (Optional)
------------------------

This section handles parameters used by the rtbh-query tool and is used to adjust the absolute timestamp stored in the database to one which is locally friendly.

.. code-block:: yaml

    # Query Output Formatting
    query:
      timeZone: America/New_York
      timeFormat: YYYY-MM-DD HH12:MI:SS AM

The time zone may be set to the time-zone of the system.