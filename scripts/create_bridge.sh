#!/bin/bash
# creates a bridge that can be used to connect a virtual machine to.
set -e

# All functions support ifconfig and ip commands (iproute2).
# Mac still only supports ifconfig
if uname -s | grep Darwin > /dev/null 2>&1; then
  on_mac=true
fi

####################
# Configure settings
####################
BRIDGE=bridge43
NETMASK=24
GATEWAY=10.0.0.1
NETMASK6=64
GATEWAY6=fe80::e823:fcff:fef4:83e7
# Håreks cool hack:
# - First two bytes is fixed to "c001" because it's cool
# - Last four is the gateway IP, 10.0.0.1
HWADDR=c0:01:0a:00:00:01
NETWORK=10.0.0.0

####################
# Functions. All support ifconfig and iproute2
####################
function output() {
  printf ">>> %s\n" "$1"
}
function verify_command() {
  command -v $1 >/dev/null 2>&1 || { echo >&2 "I require $1 but it's not installed.  Aborting."; exit 1; }
}
function bridge_check_existing() {
  if [ $on_mac ]; then
    ifconfig $BRIDGE > /dev/null 2>&1
  else
    ip link show $BRIDGE > /dev/null 2>&1
  fi
}
function bridge_create() {
  if [ $on_mac ]; then
    sudo ifconfig $BRIDGE create > /dev/null
  else
    sudo ip link add $BRIDGE type bridge > /dev/null
  fi
}
function bridge_activate() {
  if [ $on_mac ]; then
    sudo ifconfig $BRIDGE up
  else
    sudo ip link set $BRIDGE up
  fi
}
function bridge_check_configured() {
  if [ $on_mac ]; then
    ifconfig $BRIDGE | grep -q $HWADDR
  else
    # TODO: finish
    ip link show $BRIDGE
  fi
}
function bridge_configure_ipv4() {
  if [ $on_mac ]; then
    sudo ifconfig $BRIDGE $GATEWAY/$NETMASK
    sudo ifconfig $BRIDGE ether $HWADDR
  else
    sudo ip address replace $GATEWAY/$NETMASK dev $BRIDGE
    sudo ip link set dev $BRIDGE address $HWADDR
  fi
}
function bridge_configure_ipv6() {
  if [ $on_mac ]; then
    if [[ ! $(ifconfig $BRIDGE | grep $GATEWAY6) ]]; then
      sudo ifconfig $BRIDGE inet6 add $GATEWAY6/$NETMASK6
      sudo ifconfig $BRIDGE ether $HWADDR
    fi
  else
    sudo ip address replace $GATEWAY6/$NETMASK6 dev $BRIDGE
    sudo ip link set dev $BRIDGE address $HWADDR
  fi
}
function routes_number() {
  if [ $on_mac ]; then
    echo netstat -rnv | grep -c $NETWORK
  else
    echo ip route | grep -c $NETWORK
  fi
}

####################
# Setup logic. Configures the bridge the same for both commands.
####################
output "Setting up bridge: $BRIDGE, ipv4: $GATEWAY/$NETMASK, ipv6: $GATEWAY6/$NETMASK6"
if [ $on_mac ]; then
  verify_command ifconfig
  output "Running on Mac using ifconfig"
else
  verify_command ip
  output "Running on Linux using iproute2"
fi
# Check for existing
if bridge_check_existing; then
  output "Bridge already exists"
else
  output "No existing bridge, creating"
  bridge_create
fi
# Activate bridge just in case
output "Activating bridge"
bridge_activate
output "Configuring with ipv4"
bridge_configure_ipv4
output "Configuring with ipv6"
bridge_configure_ipv6
if [[ "$(routes_number)" -gt 1 ]]; then
  output """
    Potential ERROR: More than 1 route to the 10.0.0.0 network detected
    echo Check the interfaces using ifconfig and turn off any potential
    echo conflicts. The bridge interface in use is: $BRIDGE
    echo to disable use the command: ifconfig <iface> down"""

fi
output "Done setting up bridge"
