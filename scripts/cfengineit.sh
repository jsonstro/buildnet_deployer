#! /bin/sh
sleep 10 
/usr/local/sbin/cf-agent -f /var/cfengine/inputs/failsafe.cf && /usr/local/sbin/cf-agent -IK
logger "Yep -- ran cfengine 3!"
