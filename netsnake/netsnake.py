#!/usr/bin/python3
import ipaddress
import argparse
import getpass
import yaml
import pathlib
import re
import pprint

# Colors of course
from colorama import Fore
green = Fore.GREEN
yellow = Fore.YELLOW
red = Fore.RED
color_reset = Fore.RESET

# Junos libs
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.utils.start_shell import StartShell


# Functions
def valid_ip(ipaddr):
    try:
        ipaddress.ip_address(ipaddr)
    except ValueError:
        if ipaddr == None:
            print(red + "No ip addres or device list given." + color_reset)
        print(red + f"Ip validation failed for {ipaddr}" + color_reset)
        exit(code=1)

def valid_j2(templ):
    if pathlib.Path(templ).suffix == '.j2':
       return True
    else:
        print(red + "Bad template file type. Example: template.j2" + color_reset)
        exit(code=1)

def valid_conf(conffile):
    if pathlib.Path(conffile).suffix == '.yml' or pathlib.Path(conffile).suffix == '.yaml':
        return True
    else:
        print(red + "Bad config file type. Example: config/switch_addr.yml" + color_reset)
        exit(code=1)

def valid_mac(macaddr):    
    str(macaddr)
    macaddr = macaddr.replace('-', ':')

    regexp = r'^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$'

    pregexp = re.compile(regexp)
    
    if re.search(pregexp,macaddr):
        return macaddr
    else:
        print(red + "Mac address verification failed. Desired address format: xx:xx:xx:xx:xx:xx" + color_reset)
        exit(code=1)

parser = argparse.ArgumentParser(usage="netsnake.py [-a ADDRESS | -l DEVICE-LIST] COMMAND")
subcommand = parser.add_subparsers(dest="command")

parser_group = parser.add_mutually_exclusive_group()
parser_group.add_argument("-a", "--address", help="Taget IP address")
parser_group.add_argument("-l", "--device-list", help="File with list of target devices. For this option")

# config subcommand
config_parser = subcommand.add_parser("config", help="Load specified config file. Example: config/switch_addr.yml or config/switch_addr.yaml", 
                                      usage="netsnake.py [-a ADDRESS | -l DEVICE-LIST] config {options} TEMPLATE ")
config_parser.add_argument("template", help="Configuration template file. Example: template.j2")
config_parser.add_argument("--no-confirm", action="store_true", help="Commit without confirmation. Use only after double check of configuration")

# confirm subcommand
commit_parser = subcommand.add_parser("confirm", help="Commit confirmation after loading new configuration", 
                                      usage="netsnake.py [-a ADDRESS | -l DEVICE-LIST] commit")

# mac-find subcommand
mac_find_parser = subcommand.add_parser("mac-find", help="Find mac address in switching table of one or multiple devices", 
                                        usage="netsnake.py [-a ADDRESS | -l DEVICE-LIST] mac-find MACADDR")
mac_find_parser.add_argument("macaddr", help="Mac address of device you want to locate")

# get-info
get_info_parser = subcommand.add_parser("get-info", help="Get information about device")
get_info_parser.add_argument("-v", "--verbose",action="store_true", help="Get full unformatted full output from device")

#debug
debug_parser = subcommand.add_parser("debug")

arg = parser.parse_args()

if arg.address:
    switches = [ arg.address ]
    ssh_user = input("User: ")
    ssh_key = input("Path to ssh key file. Leave blank to use password instead: ")
    if ssh_key == "":
        password = getpass.getpass("Password: ")
    devlist_used = False
        
elif arg.device_list:
    #Read inventory file
    with open(arg.device_list, 'r') as inv:
        devlist = yaml.safe_load(inv)
        switches = devlist['switches']
        password = None
        devlist_used = True

match arg.command:
    case 'debug':
        for switch in switches:
            print(switch['address'])

    case 'config':
        valid_j2(f"{arg.template}")

        for switch in switches:
            
            if devlist_used == True:
                ssh_user = switch['ssh_user']
                ssh_key = switch['ssh_key']
                switch = switch['address']

            print(switch)
            print(yellow + "To config devices, you must create device config file 'config/switches/*device_hostname*.yml'" + color_reset)
            print("Loading switch variables file")

            valid_ip(switch)
            
                
            with Device(host = switch, user = ssh_user, ssh_private_key_file = ssh_key,password = password) as dev:
                hostname = dev.facts['hostname'] 

                filename = './config/switches/'+ hostname + '.yml'

                valid_conf(filename)

                with open(filename, 'r') as file:
                    data = yaml.safe_load(file)

                dev.timeout = 120
                print("Device model: " + dev.facts['model'])
                print("Device software version: " + dev.facts['version'])
                with Config(dev) as conf:
                    if arg.no_confirm == True:
                        commit = conf.commit(timeout=120)
                        print(yellow + "Warning: --no-confirm option detected.")
                        print("Mistakes in configuration can break connection to switch" + color_reset)
                    else:
                        commit = conf.commit(timeout=120, confirm=10)
                        print(yellow + "Warning: Configuration will rollback to previous in 10 minutes.")
                        print("To confirm new configuration run netsnake confirm script"+ color_reset)

                    print("Loading configuration template file")
                    conf.load(template_path=arg.template, template_vars=data, format="text")
                    conf.pdiff()

                    if conf.diff() == None:
                        print(red + "No changes to commit." + color_reset)
                        continue
                    print("Starting commit check. Please wait")
                    
                    if conf.commit_check() == True:
                        print("Commit check passed.")
                    verify = input("Commit? yes/no: ")
                    
                    if verify == "yes":
                        if commit == True:
                            print(green + "Commit successfull" + color_reset)
                        else: 
                            print(red + "commit failed" + color_reset)
                    elif verify == "no":
                        print(red + "Operation canceled" + color_reset)
                        conf.rollback()
                        exit(code=0)
                    else:
                        print(red + "Please use yes or no. Operation canceled" + color_reset)
                        conf.rollback()
    
    case 'confirm':
        for switch in switches:

            if devlist_used == True:
                ssh_user = switch['ssh_user']
                ssh_key = switch['ssh_key']
                switch = switch['address']

            with Device(host = switch, user = ssh_user, ssh_private_key_file = ssh_key,password = password) as dev:
                dev.timeout = 120
                print(switch)
    
                with Config(dev) as conf:
                    print("changes to confirm")
                    conf.pdiff(rb_id=1)
                    print("Commit confirmation")
                    verify = input("Confirm? yes/no: ")
    
                    if verify == "yes":
                        if conf.commit() == True:
                            print(green + "Commit confirmed" + color_reset)
                        else:
                            print(red + "Commit confirmation failed" + color_reset)
                            conf.rollback(rb_id=1)
                    elif verify == "no":
                            print("Operation canceled")
                            conf.rollback(rb_id=1)
    
    case 'mac-find':
        macaddr = arg.macaddr
        macaddr = valid_mac(macaddr)

        print("mac-find")

        for switch in switches:

            if devlist_used == True:
                ssh_user = switch['ssh_user']
                ssh_key = switch['ssh_key']
                switch = switch['address']

            with Device(host = switch, user = ssh_user, ssh_private_key_file = ssh_key,password = password) as dev:
                print(switch)
                shell = StartShell(dev)

                command = "cli -c 'show ethernet-switching table {} brief'".format(macaddr)
                
                shell.open()
                output = shell.run(command)
                shell.close()

                pprint.pp(output, width=150)
    
    case 'get-info':
        print("get-info")

        for switch in switches:
            
            if devlist_used == True:
                ssh_user = switch['ssh_user']
                ssh_key = switch['ssh_key']
                switch = switch['address']

            print(switch)
            with Device(host = switch, user = ssh_user, ssh_private_key_file = ssh_key,password = password) as dev:

                if arg.verbose == True:
                    pprint.pp(dev.facts, width=150)
                else:
                    print("Device hostname: " + dev.facts['hostname'])
                    print("Device model: " + dev.facts['model'])
                    print("OS version: " + dev.facts['version'])
                    print("Serial number: " + dev.facts['serialnumber'])
                    print("VC State: " + dev.facts['vc_mode'])
                    print("VC Master: " + dev.facts['vc_master'])
                
                print("\b")

