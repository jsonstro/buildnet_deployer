#! /bin/sh
/usr/sbin/service netif restart && /usr/sbin/service routing restart
logger "Yep -- restarted networking and routing!"
/usr/local/sbin/cf-agent -f /var/cfengine/inputs/failsafe.cf && /usr/local/sbin/cf-agent -IK
logger "Yep -- ran cfengine 3!"
