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

The fields in this section are all required, and should not need further definition.

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

* *location* - This is the full path where external downloads are kept.  A temporary directory is recommended, though this can be placed anywhere appropriate.  If you use sensitive lists, it may be preferable to specify this directory under the RTBH service account's home space.

* *age* - This is the amount of time in seconds that a cache file should be considered valid.  Any files exceeding the cache time will be redownloaded.

The name of the cache file will be based on the identifier used.

lists
^^^^^

Each list has several key value pairs that must be defined.

* *ident* - As lists go, the *ident* key-value pair must be unique for each list.

* *descr* - This is the plaintext description of the list.

* *file* - This is the full path and filename where the list content can be found.  In the above example, the identifier is "STATIC", but that should not be taken to mean you cannot have more than one file for static entries.

* *type* - The following list types are supported:

  The **v4_host** list type is a list of host IPs without a subnet mask defined.  These are assumed to be /32 entries.  The TOR Exit Node list the 3CoreSec Blacklist use a v4_host list.

  The **v4_host_mask** list type is a list of subnets with the mask in bits.  These are exact entries and are the format of the Team Cymru IPv4 BOGON list, and the recommended format for a locally-maintained block list.

  Valid lines include an IPv4 host/mask combination.  Notes may be provided on commented lines if necessary.

  The **csv** or comma-separated value type is the most common simple table format.  The first row is generally a header with a number of fields defined.  These kinds of files are often found with threat intelligence feeds (e.g. ProofPoint Emerging Threats, REN-ISAC).  In addition to the IP address identified, there is often a section for a category and a threat score.

* *tag* - This is a numeric tag that is used to identify the origin of the route.  On route runners that support tags (e.g. Cisco), the number will be applied to the route itself.  The tag is used to determine any particular rules for redistribution and/or to act as an origin community within BGP.

* *auto* - This is a boolean flag.  When it is set, the list will be processed without having to be explicitly called out from the command line.

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

This approach was taken for this module because it is the most accessible to the widest audience.

For this, I recommend creating a dedicated account for running RTBH updates that only allow access to any routers that are intended for use in the RTBH system.

Query Section (Optional)
------------------------

This section handles parameters used by the rtbh-query tool and is used to adjust the absolute timestamp stored in the database to one which is locally friendly.

.. code-block:: yaml

    # Query Output Formatting
    query:
      timeZone: America/New_York
      timeFormat: YYYY-MM-DD HH12:MI:SS AM

The time zone may be set to the time-zone of the system.