#! /usr/bin/python
import ssl
import sys
import getpass
from pysphere import VIServer, MORTypes, VIProperty 
from pysphere.vi_virtual_machine import VIVirtualMachine
from sys import version_info

esx_host = ""
esx_username = ""
esx_password = ""

py3 = version_info[0] > 2 #creates boolean value for test that Python major version > 2

print ""
print "               Identity               "
print "======================================"
if esx_username == "":
    if py3:
        esx_username = input("--> Please input your CruzID: ")
    else:
        esx_username = raw_input("--> Please input your CruzID: ")
else:
    print "--> CruzID: "+esx_username

if esx_password == "":
    esx_password = getpass.getpass("--> Please input your AD password: ")


# Read config file in...
vcf = ".vcenters"
try:
    file = open(vcf, "r")
    read = file.read()
    file.close()
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


print ""
print "             vCenter            "
print "================================"
print "(1) %s" % vc1
print "(2) %s" % vc2
if esx_host == "":
    if py3:
        esx_c = input("--> Which vCenter: ")
    else:
        esx_c = raw_input("--> Which vCenter: ")
    if esx_c == "1" or esx_c == vc1:
        esx_host = vc1
    elif esx_c == "2" or esx_c == vc2:
        esx_host = vc2
    else:
        print "ERROR --> Please select a vCenter from list..."
        exit(1)
else:
    print "--> vCenter: "+esx_host

s = VIServer()
def connect_vsphere():
    default_context = ssl._create_default_https_context
    ssl._create_default_https_context = ssl._create_unverified_context
    s.connect(esx_host,esx_username,esx_password)

connect_vsphere()

def get_mac_address(vm):
    mac_list = []          
    net = vm.get_property('net', from_cache=False)
    print net
    
    if net:
        for interface in net:               
            if interface.get('mac_address', None): mac_list.append(interface.get('mac_address', None))

    for v in vm.get_property("devices").values():
        if v.get('macAddress'): mac_list.append(v.get('macAddress'))                                                                             

    return mac_list

def main(vserver, hostname): 

    for ds_mor, name in vserver.get_hosts().items(): 
        props = VIProperty(vserver, ds_mor) 
        for nw in props.network:
            print nw.name
        #for item in props.datastore :
        #    print item.info.name

    if hostname:
        vm = vserver.get_vm_by_name(hostname)
        addrs = get_mac_address(vm)
        if len(addrs) > 1:
            if len(addrs) == 2:
                if addrs[0] == addrs[1]:
                    return addrs[0]
                else:
                    return addrs
            else:
                return addrs
        else:
            return addrs[0]
    else:
        print "ERROR --> 2 argumenta required, vserver and hostname!"

if __name__ == '__main__':
  l = main(s, sys.argv[1])
  print "mac(s): %s" % l


