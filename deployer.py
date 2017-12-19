#! /usr/bin/env python2.7
"""
* Script deployer.py
* Written by Josh Sonstroem (jsonstro@ucsc.edu) 
* For the DCO.Unix team
* Version v0.2 on Monday, 6 Nov. 2017 
"""


import getpass
from optparse import OptionParser
import os
import platform
from pysphere import VIServer
import re
import ssl
from subprocess import call, check_output
import sys
from sys import version_info
from time import sleep


vcenter = ""
esx_password = ""
username = ""
hostname = ""
host_os = ""
profile = ""
template = ""
ver = "v0.2"
version = "%prog "+ver
py3 = version_info[0] > 2 #creates boolean value for test that Python major version > 2
verbose = "true"


print "_________DCO__BUILD__NET__DEPLOYER__%s_________" % ver

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage, version=version)
parser.add_option("-n", "--hostname", dest="hostname",
                  help="HOSTNAME: The target VM's name in vCenter")
parser.add_option("-o", "--os", dest="host_os",
                  help="OS: One of 'FreeBSD', 'RHEL6', or 'Centos7', or 'DBAN'")
parser.add_option("-p", "--profile", dest="profile",
                  help="PROFILE: Only Linux, *must* match name under /tftpboot/{rhel6,centos7}/pxelinux.cfg on dhcp server")
parser.add_option("-t", "--template", dest="template",
                  help="TEMPLATE: Template name, *must* match vCenter, expects 3 words, e.g. 'no-app template (rhel6)'", nargs=3)
parser.add_option("-u", "--username", dest="username",
                  help="USERNAME: CruzID to use when connecting to vCenter")
parser.add_option("-c", "--vcenter", dest="vcenter",
                  help="vCENTER: Which vCenter to connect to")
#parser.add_option("-v", "--verbose",
#                  action="store_true", dest="verbose")
parser.add_option("-q", "--quiet",
                  action="store_false", dest="verbose")
(options, args) = parser.parse_args()

if len(args) != 0:
    print "ERROR --> Incorrect number of arguments (%i)" % len(args)
    parser.print_help()
    exit(1)


if options.username:
    username = options.username
    if verbose:
        print "--> CruzID: "+username
else:
    print ""
    print "               Identity               "
    print "======================================"
    if py3:
        username = input("--> Please input your CruzID: ")
    else:
        username = raw_input("--> Please input your CruzID: ")

if esx_password == "":
    esx_password = getpass.getpass("--> Please input your AD password: ")

# Read config file in...
vcf = ".vcenters"
try:
    file = open(vcf, "r")
    read = file.read()
except IOError:
    print "ERROR --> Config file '%s' does not exist! Please create it as described below." % vcf
    print "--> echo 'vc1 = \"<VCENTER1>\"' > %s" % vcf
    print "--> echo 'vc2 = \"<VCENTER2>\"' >> %s" % vcf
    print ""
    vserver.disconnect()
    exit(1)

i = 1
vc = {}
for line in read.splitlines():
    if "vc%s = " % i in line:
        vc["vc"+str(i)] = line.split('=',1)[1]
        i += 1
    if "domain = " in line:
        domain = line.split('=',1)[1].lstrip().translate(None, '"')

vc1 = vc.get("vc1").lstrip().translate(None, '"')
vc2 = vc.get("vc2").lstrip().translate(None, '"')


if options.vcenter:
    vcenter = options.vcenter
    if verbose:
        print "--> vCenter: "+vcenter
else:
    print ""
    print "             vCenter            "
    print "================================"
    print "(1) %s" % vc1
    print "(2) %s" % vc2
    if py3:
        esx_c = input("--> Which vCenter (1/2): ")
    else:
        esx_c = raw_input("--> Which vCenter (1/2): ")

    if esx_c == "1" or esx_c == vc1:
        vcenter = vc1
    elif esx_c == "2" or esx_c == vc2:
        vcenter = vc2
    else:
        print "ERROR --> Please select a vCenter from the list..."
        exit(1)

if vcenter != vc1 and vcenter != vc2:
    print "ERROR --> Please select a valid vCenter..."
    exit(1)


def connect_vsphere():
    default_context = ssl._create_default_https_context
    ssl._create_default_https_context = ssl._create_unverified_context
    vserver.connect(vcenter,username,esx_password)

vserver = VIServer()
connect_vsphere()


def powerOnGuest(vserver,hostname):
    vm=vserver.get_vm_by_name(hostname)
    vm.power_on()


def restartGuest(vserver,hostname):
    vm=vserver.get_vm_by_name(hostname)
    vm.power_off()
    vm.power_on()


def close_vsphere():
    vserver.disconnect()


def get_resource_pools(vserver):
    resource_pools = vserver.get_resource_pools()
    first_resource_pool = resource_pools.keys()[0]
    return first_resource_pool


def write_dhcp(l, n, hn, m):
    l.insert(n+4, '    host ' + hn + ' {\n')
    l.insert(n+5, '        hardware ethernet ' + m + ';\n')
    l.insert(n+6, '    }\n')


def correct_dhcp(l, n, m):
    l.pop(n)
    l.insert(n, '        hardware ethernet ' + m + ';\n')


def get_mac_address(vm):
    mac_list = []
    nic_list = []
    net = vm.get_property('net', from_cache=False)

    if net:
        for interface in net:
            nic_list.append(interface)
            if interface.get('mac_address', None): mac_list.append(interface.get('mac_address', None))

    for v in vm.get_property("devices").values():
        if v.get('macAddress'): mac_list.append(v.get('macAddress'))

    return nic_list, mac_list


def get_mac(vserver, hostname):
    if hostname:
        vm = vserver.get_vm_by_name(hostname)
        nics, addrs = get_mac_address(vm)
        if len(addrs) > 1:
            if len(addrs) == 2:
                if addrs[0] == addrs[1]:
                    return "", addrs[0]
                else:
                    return nics, addrs
            else:
                return nics, addrs
        else:
            return "", addrs[0]
    else:
        print "ERROR --> 2 arguments required, vserver and hostname!"


if options.hostname:
    hostname = options.hostname
    if verbose:
        print "--> Hostname: "+hostname
else:
    print ""
    print "    [Datastore]        Hostname      "
    print "====================================="
    
    if vserver.get_server_type():
        vmlist = vserver.get_registered_vms()
        for v in vmlist:
            w = v.split("/")
            print w[0] 
    else:
        print "vserver EMPTY - Connection Failed"
        exit(1)

    print "====================================="
    print "SELECT --> An existing host from above or enter a new hostname to clone..."
    if py3:
        hostname = input("--> Enter your hostname: ")
    else:
        hostname = raw_input("--> Enter your hostname: ")


template = ""
template_vm = ""
if options.template:
    template = options.template
    if verbose:
        print "--> Template: "+template
else:
    if py3:
        answer = input("--> Would you like to clone at template (Y/N): ")
    else:
        answer = raw_input("--> Would you like to clone a template (Y/N): ")
    if answer == "Y" or answer == "y":
        if py3:
            template = input("--> Please select template to clone from: ")
        else:
            template = raw_input("--> Please select template to clone from: ")
        print "--> Template: "+template
    elif answer == "N" or answer == "n":
        template = ""
    else:
        print "ERROR --> Unknown answer '%s', please try again..." % answer
        exit(2)


if template != "":
    if verbose:
        print ""
        print "    Clone    "
        print "============="

    def get_status(clonedVM):
        st = clonedVM.get_status()
        print "----> VM: '%s', Status: %s" % (clonedVM.get_property("name"), st)
        return st
 
    first_resource_pool = get_resource_pools(vserver)
    print "--> Cloning template '%s' as VM '%s' in vCenter (%s)" % (template, hostname, vcenter)
    template_vm = vserver.get_vm_by_name(template)
    clonedVM = template_vm.clone(hostname, resourcepool=first_resource_pool, power_on='False')
    sleep(5)
    st = get_status(clonedVM)
    while st == "Running":
        st = get_status(clonedVM)
        if st == "Success":
            break
        elif st != "Running":
            print "ERROR --> Something went amiss with clone... status '%s'!" % st
            exit(1)
        sleep(5)


if verbose:
    print ""
    print "       Mac(s)"
    print "=================="

nics, mac = get_mac(vserver, hostname)
if isinstance(mac, list):
    cnt = 0
    for n_i in nics:
        print "(%d) %s: %s" % (cnt, str(mac[cnt]), n_i)  
        cnt += 1
    if py3:
        m_c = input("--> Please select desired mac: ")
    else:
        m_c = raw_input("--> Please select desired mac: ")
    mac = mac[int(m_c)]

if verbose:
    print "--> Mac: "+mac


if options.host_os:
    host_os = options.host_os
    if verbose:
        print "--> OS: "+host_os
else:
    print ""
    print "    OS    "
    print "=========="
    print "DBAN"
    print "FreeBSD"
    print "RHEL6"
    print "Centos7"
    if py3:
        host_os = input("--> Please select your OS: ")
    else:
        host_os = raw_input("--> Please select your OS: ")

if host_os != "DBAN" and host_os != "FreeBSD" and host_os != "RHEL6" and host_os != "Centos7":
    print "ERROR --> Unknown OS selection!"
    close_vsphere()
    exit(1)

error = 0
if platform.system() == "Darwin":
    pth = os.path.dirname(__file__)
else:
    pth = "/etc/dhcp"
dhcpconf = os.path.join(pth, 'dhcpd.conf')
f = open(dhcpconf, "r")
lines = f.readlines()
f.close()


hnreg = ".*"+hostname+"\s+.*"
for num, line in enumerate(lines, 1):
    if re.search('.*Centos 7 PXEClients.*', line):
        centos7line = num
    elif re.search('.*RHEL 6 PXEClients.*', line):
        rhel6line = num
    elif re.search('.*FreeBSD.*10.*11.*PXEClients.*', line):
        freebsdline = num
    elif re.search(hnreg, line):
        wline = str(num + 1)
        cur_mac = os.popen("sed '%sq;d' %s | awk '{print $3}' | tr -d ';'" % (wline, dhcpconf)).read()
        eline = num
        error += 1


if verbose:
    print ""
    print "   DHCP   "
    print "=========="

if re.search('FreeBSD', host_os) or re.search('DBAN', host_os):
    for num, line in enumerate(lines, 1):
        if error >= 1:
            if eline > freebsdline and cur_mac.rstrip() == mac and error == 1:
                print "WARNING --> Host ("+hostname+") is already correctly configured at line", eline 
                break
            elif eline > freebsdline and cur_mac.rstrip() != mac and error == 1:
                print "WARNING --> Mac address for host ("+hostname+") does not match ("+cur_mac.rstrip()+" != "+mac+")..."
                correct_dhcp(lines, eline, mac)
                break
            else:
                print "ERROR --> Host ("+hostname+") is improperly configured at line", eline
                print "TO FIX --> Please remove entry from file '%s' and re-run script" % dhcpconf
                close_vsphere()
                exit(error)
        elif re.search('.*FreeBSD.*10.*11.*PXEClients.*', line):
            write_dhcp(lines, num, hostname, mac)
elif re.search('RHEL6', host_os):
    for num, line in enumerate(lines, 1):
        if error >= 1:
            if eline < freebsdline and eline > rhel6line and cur_mac.rstrip() == mac and error == 1:
                print "WARNING --> Host ("+hostname+") is already correctly configured at line", eline 
                break
            elif eline < freebsdline and eline > rhel6line and cur_mac.rstrip() != mac and error == 1:
                print "WARNING --> Mac address for host ("+hostname+") does not match ("+cur_mac.rstrip()+" != "+mac+")..."
                correct_dhcp(lines, eline, mac)
                break
            else:
                print "ERROR --> Host ("+hostname+") is improperly configured at line", eline
                print "TO FIX --> Please remove entry from file '%s' and re-run script" % dhcpconf
                close_vsphere()
                exit(error)
        elif re.search('.*RHEL 6 PXEClients.*', line):
            write_dhcp(lines, num, hostname, mac)
elif re.search('Centos7', host_os):
    for num, line in enumerate(lines, 1):
        if error >= 1:
            if eline > centos7line and eline < rhel6line and cur_mac.rstrip() == mac and error == 1:
                print "WARNING --> Host ("+hostname+") is already correctly configured at line", eline 
                break
            elif eline > centos7line and eline < rhel6line and cur_mac.rstrip() != mac and error == 1:
                print "WARNING --> Mac address for host ("+hostname+") does not match ("+cur_mac.rstrip()+" != "+mac+")..."
                correct_dhcp(lines, eline, mac)
                break
            else:
                print "ERROR["+error+"] --> Host ("+hostname+") is improperly configured at line", eline
                print "TO FIX --> Please remove entry from file '%s' and re-run script" % dhcpconf
                close_vsphere()
                exit(error)
        elif re.search('.*Centos 7 PXEClients.*', line):
            write_dhcp(lines, num, hostname, mac)


tmp = '/tmp'
dhcpnew = os.path.join(tmp, 'dhcpd.new')
g = open(dhcpnew, "w")
for lx in lines:
    g.write(lx)
g.close()


if os.path.getsize(dhcpnew) < os.path.getsize(dhcpconf):
    print "WARNING --> New dhcpd.conf is smaller than previous!"
    print "TO FIX --> Please review the diff below:"
    os.system("diff %s %s" % (dhcpnew, dhcpconf))
    if py3:
        cont = input("--> Overwrite %s existing config? (Y/N): " % dhcpconf)
    else:
        cont = raw_input("--> Overwrite %s existing config? (Y/N): " % dhcpconf)
    if cont == "Y" or cont == "y":
        os.system("cp %s %s" % (dhcpnew, dhcpconf))
    else:
        print "EXITING --> Please edit %s and try again!" % dhcpconf
        close_vsphere()
        exit(1)
else:
    if verbose:
        print "RELOAD --> Copying tmp file %s to %s and restarting dhcpd service..." % (dhcpnew, dhcpconf)
    os.system("cp %s %s" % (dhcpnew, dhcpconf))
    if os.path.exists('/etc/init.d/dhcpd'):
        rt1 = call(["/sbin/service", "dhcpd", "restart"])
        if rt1 != 0:
            print "ERROR --> Something went wrong with the 'dhcpd' restart..."
            close_vsphere()
            exit(1)


rt2 = 1
if re.search('FreeBSD', host_os):
    print "--> Select FreeBSD Version and ZFS/UFS on PXE Boot Screen..."
    rt2 = 0
elif re.search('DBAN', host_os):
    print "--> Select DBAN on PXE Boot Screen..."
    rt2 = 0
else:
    # Set the path to the profiles per OS
    if re.search('Centos7', host_os):
        profpath = "/tftpboot/centos7/pxelinux.cfg"
    elif re.search('RHEL6', host_os):
        profpath = "/tftpboot/rhel6/pxelinux.cfg"

    if options.profile:
        profile = options.profile
        if verbose:
            print "--> Profile: "+profile
    else:
        if verbose: 
            print ""
            print "       Profile        "
            print "======================"
    
        if re.search('Centos7', host_os):
            if platform.system() == "Darwin" and verbose:
                 os.system("cat profiles/profs7.txt")
        elif re.search('RHEL6', host_os):
            if platform.system() == "Darwin" and verbose:
                os.system("cat profiles/profs.txt")
    
        if platform.system() != "Darwin" and verbose:
            os.system("cd %s && find . -maxdepth 1 -type f | grep app | sort --version-sort | cut -d'/' -f2" % profpath)

        if py3:
            profile = input("--> Please choose desired profile: ")
        else:
            profile = raw_input("--> Please choose desired profile: ")
    
    if os.path.exists(profpath):
        if verbose:
            print ""
            print "--> Creating symlink from profile ("+profile+") to mac address for anaconda..."
        rt2 = call([os.path.join(profpath, 'link_host.sh'), profile, hostname])

if rt2 == 0:
    running_vms = vserver.get_registered_vms(advanced_filters={'runtime.powerState':'poweredOn'})
    for index, item in enumerate(running_vms):
        rf = ".*%s.*" % hostname 
        if re.search(rf, item):
            vm_state = "poweredOn"
            break
        else:
            vm_state = "poweredOff"

    if verbose:
        print "--> Booting [%s] VM '%s' in vCenter (%s)" % (vm_state, hostname, vcenter)

    if vm_state == "poweredOn":
        restartGuest(vserver,hostname)
    else:
        powerOnGuest(vserver,hostname)

    h_ip = ""
    if platform.system() != "Darwin":
        sleep(5)
        h_ip = check_output("egrep -B6 '%s' /etc/dhcp/dhcpd.leases | tail -8 | head -1 | awk '{print $2}'" % mac, shell=True)
        while h_ip == "":
            sleep(3)
            h_ip = check_output("egrep -B6 '%s' /etc/dhcp/dhcpd.leases | tail -8 | head -1 | awk '{print $2}'" % mac, shell=True)
        else:
            h_ip = h_ip.rstrip()
            print "--> Adding '%s' DNS entry for IP (%s) on buildnet..." % (hostname, h_ip)
            call(["/local/adm/infoblox-scripts/add_buildnet_dns_to_hostmaster.sh", h_ip, hostname])

else:
    print "ERROR --> Something happened with linking the profile..."

close_vsphere()
exit(rt2)
