#! /usr/bin/env python2.7
"""
* Script redeployer.py
* Written by Josh Sonstroem (jsonstro@ucsc.edu) 
* Move a host from one VLAN to another in vSphere...
* For the DCO.Unix team
* Version v0.1 on Monday, 12 Dec. 2017 
"""

from fabric.api import env, run, sudo, local, settings
from fabric import exceptions as fe
from fabric.operations import put
import getpass
from optparse import OptionParser
from paramiko import Transport
import platform
from pysphere import VIServer, MORTypes, VIProperty
from pysphere.vi_virtual_machine import VIVirtualMachine
from pysphere.resources import VimService_services as VI
from pysphere.vi_task import VITask
from socket import getdefaulttimeout, setdefaulttimeout
import ssl
from subprocess import call
from sys import exit, version_info


ver = "v0.1"
version = "%prog "+ver

global domain
domain = None

py3 = version_info[0] > 2 #creates boolean value for test that Python major version > 2


def usage_and_opts(vc1, vc2):
    print "_________DCO__BUILD__NET__REDEPLOYER__%s_________" % ver
    
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage, version=version)
    parser.add_option("-n", "--hostname", dest="hostname",
                      help="HOSTNAME: The target VM's name in vCenter")
    parser.add_option("-d", "--destvlan", dest="destvlan",
                      help="VLAN: Destination vlan tag in ESXi")
    parser.add_option("-u", "--username", dest="username",
                      help="USERNAME: CruzID to use when connecting to vCenter")
    parser.add_option("-c", "--vcenter", dest="vcenter",
                      help="vCENTER: Which vCenter to connect to:                     '%s'                       '%s'" % (vc1, vc2))
    parser.add_option("-o", "--host_os", dest="host_os",
                      help="HOST_OS: The OS of the VM")
    #parser.add_option("-v", "--verbose",
    #                  action="store_true", dest="verbose")
    parser.add_option("-q", "--quiet",
                      action="store_false", dest="verbose")
    (options, args) = parser.parse_args()
    
    if len(args) != 0:
        print "ERROR --> Incorrect number of arguments (%i)" % len(args)
        parser.print_help()
        exit(1)

    return options, args


def list_running_vms(vserver):

    if vserver.get_server_type():
        vmlist = vserver.get_registered_vms()
        for v in vmlist:
            w = v.split("/")
            print w[0]
    else:
        print "vserver EMPTY - Connection Failed"
        exit(1)


def select_host(vserver, options):
    if options.hostname:
        hostname = options.hostname
        print "--> Hostname: "+hostname
    else:
        print ""
        print "    [Datastore]        Hostname      "
        print "====================================="

        list_running_vms(vserver)
    
        print "====================================="
        print "SELECT --> An existing host to move from above..."
        if py3:
            hostname = input("--> Enter your hostname: ")
        else:
            hostname = raw_input("--> Enter your hostname: ")

    return hostname


def get_current_vlan(vserver, vm, hostname):
    m_c = 0
    vlan_list = []
    net = vm.get_property('net', from_cache=False)
    #print "Net(s): %s" % net

    if isinstance(net, list):
        print ""
        print "       Interface(s) on VM '%s'                " % hostname
        print "============================================================="
        cnt = 0
        for n_i in net:
            print "(%d) %s" % (cnt, n_i)
            cnt += 1

        if cnt >= 2:
            print "============================================================="
            print "SELECT --> Host has multiple interfaces, please choose one..."
            cnt -= 1
            if py3:
                m_c = input("--> Enter desired interface (0-%s): " % cnt)
            else:
                m_c = raw_input("--> Enter desired interface (0-%s): " % cnt)
            net = [net[int(m_c)]]

    if net:
        for interface in net:
            if interface.get('network', None): vlan_list.append(interface.get('network', None))

    for v in vm.get_property("devices").values():
        if v.get('network'): vlan_list.append(v.get('network'))

    if len(vlan_list) >= 1:
        return m_c, vlan_list[0]
    else:
        print "ERROR --> VM '%s' seems to be powered off!"
        vserver.disconnect()
        exit(1)


def change_dvs_net(s, vm_obj, hostname, dstlabel, curlabel):
    """Takes a VIServer and VIVirtualMachine object and reconfigures
    dVS portgroups according to the mappings in the pg_map dict. The
    pg_map dict must contain the source portgroup as key and the
    destination portgroup as value"""

    # Find virtual NIC devices
    pg_map = {}

    if vm_obj:
        net_device = []
        for dev in vm_obj.properties.config.hardware.device:
            if dev._type in ["VirtualE1000", "VirtualE1000e",
                            "VirtualPCNet32", "VirtualVmxnet",
                            "VirtualNmxnet2", "VirtualVmxnet3"]:
                net_device.append(dev)
    if len(net_device) == 0:
        raise Exception("The vm seems to lack a Virtual Nic")

    # Lets get the information for the port group
    network_name = dstlabel
    network_name2 = curlabel

    for ds_mor, name in s.get_datacenters().items():
        dcprops = VIProperty(s, ds_mor)
        break

    # networkFolder managed object reference
    nfmor = dcprops.networkFolder._obj
    dvpg_mors = s._retrieve_properties_traversal(property_names=['name','key'],
                                        from_node=nfmor, obj_type='DistributedVirtualPortgroup')

    # Get the portgroup managed object.
    dvpg_mor = None
    for dvpg in dvpg_mors:
        if dvpg_mor:
            break
        for p in dvpg.PropSet:
            if p.Name == "name" and p.Val == network_name:
                dvpg_mor = dvpg
            if dvpg_mor:
                break

    # Get the portgroup managed object.
    dvpg_mor2 = None
    for dvpg2 in dvpg_mors:
        if dvpg_mor2:
            break
        for p in dvpg2.PropSet:
            if p.Name == "name" and p.Val == network_name2:
                dvpg_mor2 = dvpg2
            if dvpg_mor2:
                break

    if dvpg_mor == None:
        print "Didnt find the dvpg %s, exiting now" % (network_name)
        exit()

    if dvpg_mor2 == None:
        print "Didnt find the dvpg %s, exiting now" % (network_name)
        exit()

    # Get the portgroup key
    portgroupKey = None
    for p in dvpg_mor.PropSet:
        if p.Name == "key":
            portgroupKey = p.Val
    portgroupKey2 = None
    for p in dvpg_mor2.PropSet:
        if p.Name == "key":
            portgroupKey2 = p.Val

    # Use pg_map to set the new Portgroups
    pg_map[portgroupKey2] = portgroupKey
    for dev in net_device:
        old_portgroup = dev.backing.port.portgroupKey
        if pg_map.has_key(old_portgroup):
            dev.backing.port._obj.set_element_portgroupKey(pg_map[old_portgroup])
            dev.backing.port._obj.set_element_portKey('')

    # Invoke ReconfigVM_Task
    request = VI.ReconfigVM_TaskRequestMsg()
    _this = request.new__this(vm_obj._mor)
    _this.set_attribute_type(vm_obj._mor.get_attribute_type())
    request.set_element__this(_this)

    # Build a list of device change spec objects
    devs_changed = []
    for dev in net_device:
        spec = request.new_spec()
        dev_change = spec.new_deviceChange()
        dev_change.set_element_device(dev._obj)
        dev_change.set_element_operation("edit")
        devs_changed.append(dev_change)

    # Submit the device change list
    spec.set_element_deviceChange(devs_changed)
    request.set_element_spec(spec)
    ret = s._proxy.ReconfigVM_Task(request)._returnval

    # Wait for the task to finish
    task = VITask(ret, s)

    status = task.wait_for_state([task.STATE_SUCCESS, task.STATE_ERROR])
    if status == task.STATE_SUCCESS:
        print "SUCCESS --> VM '%s' successfully reconfigured!" % hostname
    elif status == task.STATE_ERROR:
        print "ERROR --> Something went wrong reconfiguring vm '%s'!" % hostname, task.get_error_message()
    else:
        print "ERROR --> VM '%s' not found!" % hostname


def print_available_vlans(vserver, vhost, hostname, options):
    if options.destvlan:
        destvlan = options.destvlan
        print "--> Destination VLAN: "+destvlan
    else:
        for ds_mor, name in vserver.get_hosts().items():
            if name == vhost:
                props = VIProperty(vserver, ds_mor)
    
                print "     Available VLANs for vHost (%s)" % vhost
                print "=============================================================="
                for nw in props.network:
                    print nw.name
                print "=============================================================="
                print "SELECT --> VLAN to move VM '%s' onto..." % hostname
                if py3:
                    destvlan = input("--> Enter destination VLAN: ")
                else:
                    destvlan = raw_input("--> Enter destination VLAN: ")

    return destvlan


def restart_host_network(hostname, username, ldap_pw):
    global domain
    hs = "%s@%s.%s" % (username, hostname, domain)
    hn = "%s.%s" % (hostname, domain)
    resp = call(["ping", "-c 1", "-t 1", hn])
    print ""
    if resp == 0:
        if ldap_pw == "":
            ldap_pw = getpass.getpass("FABRIC --> Please input your Blue password: ")
        with settings(host_string=hs, password=ldap_pw):
            try:
                hd = "/home/%s" % username
                put("runit.sh", "%s/runit.sh" % hd, mode='750')
                sudo("/usr/bin/screen -d -m %s/runit.sh; sleep 1" % hd, shell=True, timeout=0.5)
            except fe.CommandTimeout or fe.NetworkError:
                pass
        print ""


def run_cfengine(hostname, username, ldap_pw):
    global domain
    hs = "%s@%s.%s" % (username, hostname, domain)
    hn = "%s.%s" % (hostname, domain)
    resp = call(["ping", "-c 1", "-t 1", hn])
    print ""
    if resp == 0:
        if ldap_pw == "":
            ldap_pw = getpass.getpass("FABRIC --> Please input your Blue password: ")
        with settings(host_string=hs, password=ldap_pw):
            try:
                hd = "/home/%s" % username
                put("cfengineit.sh", "%s/cfengineit.sh" % hd, mode='750')
                sudo("/usr/bin/screen -d -m %s/cfengineit.sh; sleep 1" % hd, shell=True, timeout=0.5)
            except fe.CommandTimeout or fe.NetworkError:
                pass
        print ""


def set_host_static_ip(vserver, cnt, hostname, username, options):
    scpath = "/etc/sysconfig/network-scripts"
    rcpath = "/etc"
    global domain
    err = ""

    def determine_host_os(vserver, options):
        if options.host_os:
            host_os = options.host_os
            if verbose:
                print "--> OS: "+host_os
        else:
            print "    OS    "
            print "=========="
            print "FreeBSD"
            print "RHEL6"
            print "Centos7"
            if py3:
                host_os = input("--> Please select your OS: ")
            else:
                host_os = raw_input("--> Please select your OS: ")
        
        if host_os != "FreeBSD" and host_os != "RHEL6" and host_os != "Centos7":
            print "ERROR --> Unknown OS selection!"
            vserver.disconnect()
            exit(1)
        else:
            return host_os

    def collect_details(vserver, ifcnt, host_os):
        print "INPUT --> Please enter network information for interface '%s'" % ifcnt

        if (host_os == "RHEL6" or host_os == "Centos7"):
            interface = "eth%s" % ifcnt
            print "SELECTED --> network interface is '%s' for Linux..." % interface
        else:
            interface = "em%s" % ifcnt
            print "SELECTED --> network interface is '%s' for FreeBSD..." % interface

        if py3:
            override = input("--> Override selected inferface? (Y/N): ")
            if override != "Y" and override != "y" and override != "N" and override != "n":
                print "ERROR --> your answer (%s) is not understood!" % answer
                vserver.disconnect()
                exit(1)
            elif override == "Y" or override == "y":
                inferface = input("--> Enter interface name: ")
            ipaddr = input("--> Enter static IP: ")
            netmask = input("--> Enter netmask: ")
            gateway = input("--> Enter default gateway: ")
        else:
            override = raw_input("--> Override default inferface? (Y/N): ")
            if override != "Y" and override != "y" and override != "N" and override != "n":
                print "ERROR --> your answer (%s) is not understood!" % answer
                vserver.disconnect()
                exit(1)
            elif override == "Y" or override == "y":
                inferface = raw_input("--> Enter interface name: ")
            ipaddr = raw_input("--> Enter static IP: ")
            netmask = raw_input("--> Enter netmask: ")
            gateway = raw_input("--> Enter default gateway: ")

        return ipaddr, netmask, gateway, interface

    def setup_sysconfig_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, scpath):

        global domain
        hs = "%s@%s.%s" % (username, hostname, domain)
        with settings(host_string=hs):
            sudo("cat %s/ifcfg-%s | grep -v BOOTPROTO | grep -v NM_CONTROLLED > /tmp/ifcfg-%s" % (scpath, interface, interface), shell=False)
            sudo("echo \"BOOTPROTO='static'\" >> /tmp/ifcfg-%s" % interface, shell=False)
            sudo("echo \"IPADDR='%s'\" >> /tmp/ifcfg-%s" % (ipaddr, interface), shell=False)
            sudo("echo \"NETMASK='%s'\" >> /tmp/ifcfg-%s" % (netmask, interface), shell=False)
            sudo("echo \"GATEWAY='%s'\" >> /tmp/ifcfg-%s" % (gateway, interface), shell=False)
            sudo("echo \"NM_CONTROLLED='no'\" >> /tmp/ifcfg-%s" % interface, shell=False)
            print ""
            sudo("cat /tmp/ifcfg-%s" % interface, shell=False)

        print "=============================================================="
        if py3:
            answer = input("VALIDATE --> Does the above look correct? (Y/N): ")
        else:
            answer = raw_input("VALIDATE --> Does the above look correct? (Y/N): ")
        if answer != "Y" and answer != "y" and answer != "N" and answer != "n":
            print "ERROR --> your answer (%s) is not understood!" % answer
            vserver.disconnect()
            exit(1)
        else:
            return answer


    def setup_rcconf_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, rcpath):

        global domain
        hs = "%s@%s.%s" % (username, hostname, domain)
        with settings(host_string=hs):
            sudo("echo \"ifconfig_%s='inet %s netmask %s'\" > /tmp/rc.conf" % (interface, ipaddr, netmask), shell=False)
            sudo("echo \"defaultrouter='%s'\" >> /tmp/rc.conf" % gateway, shell=False)
            sudo("cat %s/rc.conf | grep -v ifconfig_%s | grep -v defaultrouter >> /tmp/rc.conf" % (rcpath, interface), shell=False)
            print ""
            sudo("cat /tmp/rc.conf", shell=False)

        print "=============================================================="
        if py3:
            answer = input("VALIDATE --> Does the above look correct? (Y/N): ")
        else:
            answer = raw_input("VALIDATE --> Does the above look correct? (Y/N): ")
        if answer != "Y" and answer != "y" and answer != "N" and answer != "n":
            print "ERROR --> your answer (%s) is not understood!" % answer
            vserver.disconnect()
            exit(1)
        else:
            return answer


    host_os = determine_host_os(vserver, options)

    print ""
    print "     Configure network details for VM '%s'" % hostname
    print "=============================================================="
    ipaddr, netmask, gateway, interface = collect_details(vserver, cnt, host_os)

    if host_os == "RHEL6" or host_os == "Centos7":
        answer = setup_sysconfig_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, scpath)

        while answer == "N" or answer == "n":
            # Data collection was wrong, lets retry 'til we get it right...
            ipaddr, netmask, gateway, inferface = collect_details(vserver, cnt, host_os)
            answer = setup_sysconfig_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, scpath)
    
        if answer == "Y" or answer == "y":
            print "--> Rewriting network info for VM '%s' (interface %s)" % (hostname, interface)
            hs = "%s@%s.%s" % (username, hostname, domain)
            with settings(host_string=hs, password=""):
                sudo("mv /tmp/ifcfg-eth%s %s/ifcfg-eth%s" % (cnt, scpath, cnt), shell=False)
                try:
                    hd = "/home/%s" % username
                    if host_os == "RHEL6":
                        put("cfengineit.sh", "%s/cfengineit.sh" % hd, mode='750')
                        sudo("/usr/bin/screen -d -m %s/cfengineit.sh; sleep 1" % hd, shell=True, timeout=0.5)
                    ### TO DO ###
                    #else:
                        # Centos 7 so call chef, either from 'workstation/server' or client,
                        # this assumes we need to do some build net cleanup post-move...
                        #put("chefit.sh", "%s/chefit.sh" % hd, mode='750')
                        #sudo("/usr/bin/screen -d -m %s/chefit.sh; sleep 1" % hd, shell=True, timeout=0.5)
                    sudo("service network restart", shell=False, timeout=0.5)
                except fe.CommandTimeout:
                    pass
            print ""
        else:
            err = "ERROR --> Something went wrong with static IP setup (interface %s) on host '%s'!" % (interface, hostname)

    else:
        # FreeBSD
        answer = setup_rcconf_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, rcpath)

        while answer == "N" or answer == "n":
            # Data collection was wrong, lets retry 'til we get it right...
            ipaddr, netmask, gateway, inferface = collect_details(vserver, cnt, host_os)
            answer = setup_rcconf_file(vserver, ipaddr, netmask, gateway, interface, hostname, username, rcpath)
   
        if answer == "Y" or answer == "y":
            print "--> Rewriting network info for VM '%s' (inferface %s)" % (hostname, interface)
            hs = "%s@%s.%s" % (username, hostname, domain)
            with settings(host_string=hs, password=""):
                sudo("mv /tmp/rc.conf %s/rc.conf" % rcpath, shell=False)
                try:
                    hd = "/home/%s" % username
                    put("freebsdit.sh", "%s/freebsdit.sh" % hd, mode='750')
                    sudo("/usr/bin/screen -d -m %s/freebsdit.sh; sleep 1" % hd, shell=True, timeout=0.5)
                except fe.CommandTimeout:
                    pass
            print ""
        else:
            err = "ERROR --> Something went wrong with static IP setup (interface %s) on host '%s'!" % (interface, hostname)

    # Check for errors and bail!
    if err != "":
        print err
        vserver.disconnect()
        exit(1)


def main():
    vcenter = ""
    esx_username = ""
    esx_password = ""
    ldap_password = ""


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

    if domain == None:
        print "ERROR --> Domain is blank, add to settings in config..."
        print "--> echo 'domain = \"<DOMAIN>\"' >> %s" % vcf
        vserver.disconnect()
        exit(1)


    options, args = usage_and_opts(vc1, vc2)


    def connect_vsphere():
        default_context = ssl._create_default_https_context
        ssl._create_default_https_context = ssl._create_unverified_context
        vserver.connect(vcenter,esx_username,esx_password)


    if options.username:
        esx_username = options.username
        print "--> CruzID: "+esx_username
    else:
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


    if options.vcenter:
        vcenter = options.vcenter
        print "--> vCenter: "+vcenter
    else:
        print ""
        print "             vCenter            "
        print "================================"
        print "(1) %s" % vc1
        print "(2) %s" % vc2
        if vcenter == "":
            if py3:
                esx_c = input("--> Which vCenter: ")
            else:
                esx_c = raw_input("--> Which vCenter: ")
            if esx_c == "1" or esx_c == vc1:
                vcenter = vc1
            elif esx_c == "2" or esx_c == vc2:
                vcenter = vc2
            else:
                print "ERROR --> Please select a vCenter from list..."
                exit(1)
        else:
            print "--> vCenter: "+vcenter

    vserver = VIServer()
    connect_vsphere()

    hostname = select_host(vserver, options)
    vm = vserver.get_vm_by_name(hostname)

    ifc, curvlan = get_current_vlan(vserver, vm, hostname)
    curhost = vm.properties.runtime.host.name

    print ""
    print "    Settings of VM '%s'   " % hostname
    print "======================================="
    print "Current VLAN: %s" % curvlan
    print "Current HOST: %s" % curhost
    print ""

    destvlan = print_available_vlans(vserver, curhost, hostname, options)

    print ""
    print "NOTE --> Host will continue to use DHCP on new network if no static IP defined..."
    if py3:
        ans = input("--> Do you wish to set a static IP for VM '%s'? (Y/N): " % hostname)
    else:
        ans = raw_input("--> Do you wish to set a static IP for VM '%s'? (Y/N): " % hostname)
    print ""
    if ans == "Y" or ans == "y":
        set_host_static_ip(vserver, ifc, hostname, esx_username, options)
    else:
        restart_host_network(hostname, esx_username, ldap_password)

    change_dvs_net(vserver, vm, hostname, destvlan, curvlan)

    if platform.system() != "Darwin":
        call(["/local/adm/infoblox-scripts/remove_dcnet_dns_from_hostmaster.sh", hostname])

    vserver.disconnect()


if __name__ == '__main__':
    l = main()
