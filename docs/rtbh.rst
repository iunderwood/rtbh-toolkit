RTBH Requirements
=================

This section describes the necessary requirements that must be in place for the tool can be used.

|:factory:| Network Infrastructure
----------------------------------

A Remote Trigger Black Hole infrastructure, defined in `RFC 5365`_ leverages reverse-path forwarding validation in network equipment to block undesired source addresses by inserting routes to those networks via a Null interface.  Since traffic originating from a blocked address cannot actually come from a Null interface, the packets are blocked upon ingress to the network hardware.

Preparing the network for this toolkit is the job of the Network Engineer.  Suggestions and links will be appended to this document as this particular project matures.  However, achieving scale in an RTBH environment generally employs route reflectors, and a dedicated null route server or two.

As this toolkit goes, its job is to interact with a Null Route server.

|:computer:| Null Route Server
------------------------------

At this time, the only supported Null Route server is a Cisco IOS-XE device with RESTCONF enabled.

IOS-XE Requirements
^^^^^^^^^^^^^^^^^^^

Cisco IOS-XE devices are required to have the following in place:

* All static routes which must stay on the device must have a "name" parameter added to the route.

* Static routes intended to be announced via BGP must use a route-map and the "tag" parameter to match the routes.

|:notebook:| Notes

* At least one tag must be set up.  (e.g. 6660)  This will be applied to a route from any list that does not have its own tag, or a route that appears in more than one list.

* The use of a tag for each list may be used to announce an origin community, if desired.

IOS-XE Operation
^^^^^^^^^^^^^^^^

The Cisco IOS-XE routerunner performs a wholesale reset and replacement of all the routes on the system.  RESTCONF does not have a bulk delete capability that I am aware of, so the static route table is set to a bare minimum based upon routes which have the default "name" configured as described above.

This is a very simple RESTCONF PUT, but it can take several minutes for the internal confd process to handle the request.

Once the base route state has been achieved, all eligible routes are added to the static route table in batches of a size to be defined by the operator.  A batch size of 300 has been found to be pretty close to optimal.  The routerunner will wait one second between each successful batch update.

.. _RFC 5365: https://datatracker.ietf.org/doc/html/rfc5635