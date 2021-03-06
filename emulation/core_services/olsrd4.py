# vim:ts=2:expandtab:shiftwidth=2
#
#  Copyright 2013 Claudio Pisa, Andrea Detti
#
#  This file is part of wmSDN
#
#  wmSDN is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  wmSDN is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with wmSDN.  If not, see <http://www.gnu.org/licenses/>.
#

''' OLSRd IPv4 user-defined service.
'''

import os
import random

from core.service import CoreService, addservice
from core.misc.ipaddr import IPv4Prefix

class Olsrd4Service(CoreService):
    ''' This is an user-defined service. 
    '''
    # a unique name is required, without spaces
    _name = "Olsrd4Service"
    # you can create your own group here
    _group = "Utility"
    # list of other services this service depends on
    _depends = ()
    # per-node directories
    #_dirs = ("/tmp/")
    _dirs = ()
    # generated files (without a full path this file goes in the node's dir,
    #  e.g. /tmp/pycore.12345/n1.conf/)
    _configs = ('olsrdservice_start.sh', 'olsrdservice_stop.sh', '.bashrc')
    # this controls the starting order vs other enabled services
    _startindex = 51
    # list of startup commands, also may be generated during startup
    _startup = ('/bin/bash olsrdservice_start.sh',)
    # list of shutdown commands
    _shutdown = ('/bin/bash olsrdservice_stop.sh',)

    _ipv4_routing = True
    _ipv6_routing = False

    @classmethod
    def generateconfig(cls, node, filename, services):
        ''' Return a string that will be written to filename, or sent to the
            GUI for user customization.
        '''
        try:
            olsrd_dir = node.session.cfg['olsrd_dir']
        except KeyError:
            # PLEASE SET THIS VALUE in your /etc/core/core.conf
            olsrd_dir = "/home/user/wmSDN/olsrd-git" 

        cfg =  "#!/bin/bash\n"
        cfg += "# auto-generated by OlsrdService \n"
        cfg += "# source /etc/profile \n"

        if filename == cls._configs[0]: # start
                return cfg + cls.generateOlsrdConf(node, services, olsrd_dir, start=True)
        elif filename == cls._configs[1]: # stop
                return cfg + cls.generateOlsrdConf(node, services, olsrd_dir, start=False)
        elif filename == cls._configs[2]: # env
                return cls.generateOlsrdEnv(node, services, olsrd_dir)
        else:
                raise ValueError
    
    @classmethod
    def generateOlsrdEnv(cls, node, services, olsrd_dir):
            cfg = """
export OLSR_DIR=%s
export SHELL=/bin/bash
export HOME=$PWD
export PATH=$OLSR_DIR:$OLSR_DIR/olsrd:$PATH
export TERM=vt100
alias ls='ls --color'

4olsr () {
    wget -q http://127.0.0.1:2006/$1 -O -
}

""" % (olsrd_dir,)
            return cfg

    @classmethod
    def generateOlsrdConf(cls, node, services, olsrd_dir, start):
            return """

export OLSR_DIR=%s
export OLSR_TABLE="198"
export OLSR_DEFAULT_TABLE="199"
export OLSR_INTERFACE="eth0"

printandexec() {
    echo "$@"
    eval "$@"
}

is_hna_node() {
    if ip address show | grep "10\.100\."; then
        return 0   #true
    else
        return 1   #false
    fi
}

is_gateway () {
    if [ ${HOSTNAME:0:1} == "g" ]; then
        return 0   #true
    else
        return 1   #false
    fi
}

start() {
    # we don't need no IPv6
    echo 1 > /proc/sys/net/ipv6/conf/all/disable_ipv6

    # take eth0's IP address and compute broadcast address
    ETH0_IP=$(ip -4 addr show dev eth0 | grep "inet " | awk '{print $2}' | cut -d "/" -f 1)
    ETH_MASK=$(ip -4 addr show dev eth0 | grep "inet " | awk '{print $2}' | cut -d "/" -f 2)
    # broadcast IP address (assuming /16 !!! FIXME!!!)
    BRD_IP=$(echo $ETH0_IP | awk 'BEGIN {FS="."} {print $1 "." $2 ".255.255"}')

    # take IP addresses and delete them from the interface
    printandexec ip addr del ${ETH0_IP}/${ETH_MASK} dev eth0

    # add the broadcast address to eth0 (assuming /16 !!! FIXME !!!)
    printandexec ip addr add ${ETH0_IP}/16 brd ${BRD_IP} dev eth0

    #generate an olsrd.conf on the fly
    cat - > olsrd.conf << EOF
LinkQualityFishEye  0

LoadPlugin "olsrd_txtinfo.so.0.1"
{
    PlParam      "accept" "0.0.0.0"
}

LoadPlugin "olsrd_jsoninfo.so.0.0"
{
    PlParam      "port" "9090"
    PlParam      "accept" "0.0.0.0"
}

Interface "$OLSR_INTERFACE"
{
}

EOF

    if is_gateway; then
        # add a default Hna4 to olsrd.conf
        cat - >> olsrd.conf << EOF
Hna4
{
    0.0.0.0 0.0.0.0
}
EOF

        # and NAT
        # assume that the "internet interface" is eth1
        #iptables -A POSTROUTING -t nat -o eth1 -j MASQUERADE
        printandexec tc qdisc add dev eth1 parent root handle 1: htb default 1 
        printandexec tc class add dev eth1 parent 1: classid 1:1 htb rate 1Mbit
    fi

    if is_hna_node ; then
        # announce the HNA
        HNA_NET=$( ip address show | grep "10\.100\." | cut -d "/" -f 1 | awk '{print $2}' | awk -F '.' '{print $1 "." $2 "." $3 "." 0}' )
        cat - >> olsrd.conf << EOF
Hna4
{
    ${HNA_NET} 255.255.255.0
}
EOF
    fi

    # start olsrd
    printandexec ${OLSR_DIR}/olsrd -f olsrd.conf -d 0

}

stop() {
    killall olsrd
}

$1

""" % (olsrd_dir,)



# this line is required to add the above class to the list of available services
addservice(Olsrd4Service)

