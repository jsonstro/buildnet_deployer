#! /bin/sh

DIR1="/tftpboot/rhel6/pxelinux.cfg"
DIR2="/var/lib/tftpboot/rhel6/pxelinux.cfg"
DIR3="/tftpboot/centos7/pxelinux.cfg"
DIR4="/var/lib/tftpboot/centos7/pxelinux.cfg"
FILE="/etc/dhcp/dhcpd.conf"

APP_ROOT="$(dirname "$(readlink -fm "$0")")"
cd $APP_ROOT
PWD=$(pwd)
TYPES=$(ls $PWD | grep app)

USAGE="      ./link_host.sh CONF HOST [HOST2 ...]"
NOTES="        where HOST is a valid entry in ${FILE} and ${CONF} an existing conf in ${PWD}"
if [ "${1}" == "-h" ] || [ $# -eq "0" ]; then
    echo "USAGE: ${USAGE}"
    echo "       ${NOTES}"
    exit 0
fi

if [ "$#" -lt "2" ]; then
    echo "--> Error: Needs 2+ args, conf and host(s)"
    echo "USAGE: ${USAGE}"
    echo "       ${NOTES}"
    exit 1
fi

if [ "${PWD}" != "${DIR1}" ] && [ "${PWD}" != "${DIR2}" ] && [ "${PWD}" != "${DIR3}" ] && [ "${PWD}" != "${DIR4}" ]; then
    echo "--> Error: Can't run this script from ${PWD}!"
    exit 1
fi

CONF=${1}

if [ "$#" -gt "2" ]; then
    shift
    # We got multiple hosts to link
    i=1
    for h in ${@}; do
        if [ ${i} -gt 0 ]; then
            HOST=${1}
            grep -q ${HOST} ${FILE}
            if [ $? -ne 0 ]; then
                echo "--> Error: ${HOST} not found in ${FILE}"
                exit 1
            fi

            DST=$(grep -A1 ${HOST} ${FILE} | tail -1 | awk '{print $3}' | tr -d ';' | tr ':' '-' | awk '{print "01-" $1 }')
            if [ ! -z ${DST} ]; then
                echo ${TYPES} | grep -q ${CONF}
                if [ $? -eq 0 ]; then
                    echo "--> Linking from '${CONF}' to '${DST}' (${HOST})"
                    ln -s ${CONF} ${DST}
                else
                    echo "--> Error: No app config called '${CONF}' exists, valid types:" 
                    echo "${TYPES}"
                    exit 1
                fi
            else
                echo "--> Error: no link dest specified..."
                exit 1
            fi
        fi
        shift
        i=$(expr ${i} + 1)
    done
else
    HOST=${2}
    grep -q ${HOST} ${FILE}
    if [ $? -ne 0 ]; then
        echo "--> Error: ${HOST} not found in ${FILE}"
        exit 1
    fi

    DST=$(grep -A1 ${HOST} ${FILE} | tail -1 | awk '{print $3}' | tr -d ';' | tr ':' '-' | awk '{print "01-" $1 }')
    if [ ! -z ${DST} ]; then
        echo ${TYPES} | grep -q ${CONF}
        if [ $? -eq 0 ]; then
            echo "--> Linking from '${CONF}' to '${DST}' (${HOST})"
            ln -s ${CONF} ${DST}
        else
            echo "--> Error: No app config called '${CONF}' exists, valid types:" 
            echo "${TYPES}"
            exit 1
        fi
    else
        echo "--> Error: no link dest specified..."
        exit 1
    fi
fi

echo
exit 0
