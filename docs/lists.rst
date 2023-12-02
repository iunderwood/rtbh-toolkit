List References
===============

This section contains a set of list references for use in the "listrunner" configuration.

These may be modified to suit the needs of the system, but the are provided as examples.

Static Lists
------------

This list uses a specific file which contains a list of networks and bitmasks.  The file has a local storage reference, but this can be updated by any automated means available.

.. code-block:: yaml
   :caption: listrunner structure

    listrunner:
      lists:
        - ident: STATIC
          descr: Static Network List
          file: /etc/static.txt
          type: v4_host_mask
          tag: 6661
          auto:

.. code-block::
   :caption: static list text file

    # 2020-12-09 - Ticket 12313
    52.188.145.215/32
    # 2021-02-06 - Ticket 31245
    94.147.140.0/23

Free Address Lists
------------------

This section highlights some free address lists that may be suitable for blocking.

3Corsec Blacklist
^^^^^^^^^^^^^^^^^

3Coresec publishes a subset of the Emerging Threats list called the `Blacklist`_.  This is a very dynamic list and often has large changes while the list updates.

.. code-block:: yaml
   :caption: listrunner structure

    listrunner:
      lists:
       - ident: 3CORESEC
         descr: 3CoreSec Open Blacklist
         url: https://blacklist.3coresec.net/lists/et-open.txt
         type: v4_host
         tag: 6664
         auto:

.. code-block::
   :caption: 3CoreSec ET-Open Text

   1.117.87.94
   1.12.247.13
   1.14.20.119
   ...

Team Cymru IPv4 Bogon List
^^^^^^^^^^^^^^^^^^^^^^^^^^

Team Cymru provides a full reference to the `Bogons with HTTP`_ service.  The last updated time is provided in a comment at the top of the remote file, but this is not used.

The full bogon list is free and is updated every four hours.

.. code-block:: yaml
   :caption: listrunner structure

    listrunner:
      lists:
       - ident: V4BOGON
         descr: Team Cymru IPv4 Bogon List
         url: https://team-cymru.org/Services/Bogons/fullbogons-ipv4.txt
         type: v4_host_mask
         tag: 6663
         auto:

.. code-block::
   :caption: Team Cymru IPv4 Full BOGONs

   # last updated 1701536101 (Sat Dec  2 16:55:01 2023 GMT)
   # Know your network!  Please rigorously test all filters!
   0.0.0.0/8
   10.0.0.0/8
   23.135.225.0/24
   23.151.160.0/24
   23.154.233.0/24
   ...

|:onion:| TOR Exit Node List
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The TOR Project publicises its Exit Node list every few hours.  It is freely available for anyone to use.  The `Abuse FAQ`_ advises against blocking the exit nodes, but high-value institutions may find benefit from blocking anonymous access to their networks.

.. code-block:: yaml
   :caption: listrunner structure

    listrunner:
      lists:
        - ident: TORXN
          descr: TOR Exit Node List
          url: https://check.torproject.org/torbulkexitlist
          type: v4_host
          tag: 6662
          auto:

.. code-block::
   :caption: TOR Exit Node text file

    185.241.208.232
    194.26.192.64
    171.25.193.25
    80.67.167.81
    192.42.116.187
    ...

.. _Abuse FAQ: https://support.torproject.org/abuse/
.. _Blacklist: https://blacklist.3coresec.net/
.. _Bogons with HTTP: https://www.team-cymru.com/bogon-reference-http

Paid Lists
----------

This is the configuration for lists which are available for a fee from the subscription provider.

Proofpoint Emerging Threats
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ProofPoint Emerging Threats Repultation List is a subscription service which provides a detailed list of relevant IP reputation data for the end user.  This does need a key to access the list which is updated roughly hourly.

This is in a CSV format with multiple columns that identify the address, what the reputation category is, and a confidence score within that category.

In the configuration below, we are filtering out category 1 for Malware C&C.  Additionally we leverage the score provided in the list, where we will add hosts with a score of 112 or higher, and then remove the offending address only after the score drops below 96.

The tech brief for the `Rep List Overview`_ provides a detailed explanation of what is available.

.. code-block:: python
   :caption: listrunner structure

    listrunner:
      lists:
       - ident: PPOINT1
         descr: ProofPoint Malware C&C
         url: https://rules.emergingthreatspro.com/_KEY_/reputation/detailed-iprepdata.txt
         type: csv
         tag: 6666
         csv:
           field_addr: ip
           field_score: score
           field_category: category
         category:
           operator: equals
           criteria: 1
         score:
           lwm: 96
           hwm: 112
         auto:

.. code-block::
   :caption: CSV headers

   ip, category, score, first_seen, last_seen, ports (|)

.. _`Rep List Overview`: https://tools.emergingthreats.net/docs/ET%20Intelligence%20Rep%20List%20Tech%20Description.pdf