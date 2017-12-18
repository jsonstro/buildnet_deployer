#!/usr/bin/python
import vm_include
 
def main():
    #change these to match your installation
    host = ""
    user = ""
    pw = ""
 
    #connect to the host
    hostcon=vm_include.connectToHost(host,user,pw)
 
    #list server type
    print "Type:",hostcon.get_server_type()
 
    #disconnect from the host
    hostcon.disconnect()
 
if __name__ == '__main__':
        main()
