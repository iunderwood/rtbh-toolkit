The Story
=========

This is how we got here.

|:books:| The Project
---------------------

This project was first conceived during the pandemic lockdown period.  During that time, the information security team was observing a fair amount of network surveillance traffic that was becoming a cause of concern.  In those conversations, which are something of a memory now, a question was asked.

How can we block all the TOR exit nodes?

The question itself was interesting.  The TOR project publishes a list of all the known exit nodes on their network and updates it every couple of hours.  While blocking on TOR is not an uncommon feature in most modern firewalls (as of 2023), there were still parts of the network that were in front of the firewall.

I was aware of the Remote Trigger Black Hole solution, in part due to my days of working in the service provider space.  First documented in `RFC 5365`_, a Remote Trigger Black Hole leverages network hardware to block traffic that the operator desires to block.

With this in mind and a router available for use, implementing an RTBH setup at the enterprise was demonstrated to be effective.

The dynamic nature of the TOR exit node list necessitated developing a set of scripts to automate the process and ensure it continued to run.  The first version of these tools was used in a production environment for years, and interest in adding new lists is what prompted the tool's rewriting and open-source publication.

|:warning:| Disclaimer
----------------------

This work is an open-source release under the `MIT license`_.

While my employer has allowed me to work on this project, they will remain nameless as they assume no liability or responsibility for it.

.. _RFC 5365: https://datatracker.ietf.org/doc/html/rfc5635
.. _MIT License: https://opensource.org/license/mit/