#! /usr/bin/python

import getpass
from pysphere import VIServer, MORTypes
from pysphere.vi_virtual_machine import VIVirtualMachine
import ssl
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
props = s._retrieve_properties_traversal(property_names=['name', 'config.template'], 
                                         from_node=None, obj_type=MORTypes.VirtualMachine)

for p in props:
    mor = p.Obj
    name = ""
    is_template = False
    for item in p.PropSet:
        if item.Name == "name": name = item.Val
        elif item.Name == "config.template": is_template = item.Val
    if is_template: print "MOR:", mor, " - Name:", name
