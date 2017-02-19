#!/usr/bin/python
# -*- coding: utf-8 -*-

# What this does:
#
# Start this as a daemon. It connects to your Sonos Connect and your MARANTZ
# Receiver. Whenever the Sonos Connect starts playing music, radio or whatever,
# it turns on the Receiver, switches to the appropriate input, sets the volume
# and changes to the Sound Program you want to (e.g. "5ch Stereo").
#
# If the Receiver is already turned on, it just switches the input and the
# Sound Program, not the Volume.
#
# If you set the standby time of the Receiver to 20 minutes, you'll have a
# decent instant-on solution for your Sonos Connect - it behaves just like
# one of Sonos' other players.
#
# Optimized for minimum use of resources. I leave this running on a Raspberry
# Pi at my place.
#
# Before installing it as a daemon, try it out first: Adapt the settings in the
# script below. Then just run the script. It'll auto-discover your Sonos
# Connect. If that fails (e.g. because you have more than one Connect in your
# home or for other reasons), you can use the UID of your Sonos Connect as the
# first and only parameter of the script. The script will output all UIDs
# neatly for your comfort.
#
# Prerequisites:
# - Your MARANTZ Receiver has to be connected to the LAN.
# - Both your MARANTZ Receiver and your Sonos Connect have to use fixed IP
#   addresses. You probably have to set this in your router (or whichever
#   device is your DHCP).
# - Your MARANTZ Receiver's setting of "Network Standby" has to be "On".
#   Otherwise the Receiver cannot be turned on from standby mode.
#
# Software prerequisites:
# - sudo pip install soco



import os
import sys
import time
import re
import urllib, urllib2
import soco
import Queue
import signal
import Marantz

from datetime import datetime

__version__     = '0.3'



# --- Please adapt these settings ---------------------------------------------

SONOS_UUID       = 'RINCON_B8E937953D7201400'	# IP address of your MARANTZ Receiver. Look it up in your router or set it in the Receiver menu.
MARANTZ_IP       = '192.168.11.4'            	# IP address of your MARANTZ Receiver. Look it up in your router or set it in the Receiver menu.
MARANTZ_INPUT    = 'CD'                     	# Name of your Receiver's input the Sonos Connect is connected to. Should be one
												# of AV1, AV2, ..., HDMI1, HDMI2, ..., AUDIO1, AUDIO2, ..., TUNER, PHONO, V-AUX, DOCK,
												# iPod, Bluetooth, UAW, NET, Napster, PC, NET RADIO, USB, iPod (USB) or the like.
												# Don't use an input name you set yourself in the Receiver's setup menu.
MARANTZ_VOLUME   = '60'                     	# Volume the Receiver is set to when started. Set to None if you don't want to change it.
MARANTZ_SOUNDPRG = '5ch Stereo'              	# DSP Sound Program to set the Receiver to when started. Set to None if you don't want to change it.


def auto_flush_stdout():
    unbuffered = os.fdopen(sys.stdout.fileno(), 'w', 0)
    sys.stdout.close()
    sys.stdout = unbuffered

def handle_sigterm(*args):
    global break_loop
    print u"SIGTERM caught. Exiting gracefully.".encode('utf-8')
    break_loop = True

# --- Connect to Marantz AVR --------------------------------------------------

avr = Marantz.IP("192.168.11.4") # replace with your AVR IP
# test connectivity
#avr.connect() # if you get an error, double check the IP

# --- Discover SONOS zones ----------------------------------------------------

if len(sys.argv) == 2:
    connect_uid = sys.argv[1]
else:
    connect_uid = SONOS_UUID

print u"Discovering Sonos zones".encode('utf-8')

match_ips   = []
for zone in soco.discover():
    print u"   {} (UID: {})".format(zone.player_name, zone.uid).encode('utf-8')

    if connect_uid:
        if zone.uid.lower() == connect_uid.lower():
            match_ips.append(zone.ip_address)
    else:
        # we recognize Sonos Connect and ZP90 by their hardware revision number
        if zone.get_speaker_info().get('hardware_version')[:4] == '1.1.':
            match_ips.append(zone.ip_address)
            print u"   => possible match".encode('utf-8')
print

if len(match_ips) != 1:
    print u"The number of Sonos Connect devices found was not exactly 1.".encode('utf-8')
    print u"Please specify which Sonos Connect device should be used by".encode('utf-8')
    print u"using its UID as the first parameter.".encode('utf-8')
    sys.exit(1)

sonos_device    = soco.SoCo(match_ips[0])
subscription    = None
renewal_time    = 120

# --- Initial MARANTZ status ---------------------------------------------------

print u"MARANTZ Power status:  {}".format(avr.get_power())
print u"MARANTZ Input select:  {}".format(avr.get_source())
print u"MARANTZ Volume:        {}".format(avr.get_volume())
print

# --- Main loop ---------------------------------------------------------------

break_loop      = False
last_status     = None

# catch SIGTERM gracefully
signal.signal(signal.SIGTERM, handle_sigterm)
# non-buffered STDOUT so we can use it for logging
auto_flush_stdout()

while True:
    # if not subscribed to SONOS connect for any reason (first start or disconnect while monitoring), (re-)subscribe
    if not subscription or not subscription.is_subscribed or subscription.time_left <= 5:
        # The time_left should normally not fall below 0.85*renewal_time - or something is wrong (connection lost).
        # Unfortunately, the soco module handles the renewal in a separate thread that just barfs  on renewal
        # failure and doesn't set is_subscribed to False. So we check ourselves.
        # After testing, this is so robust, it survives a reboot of the SONOS. At maximum, it needs 2 minutes
        # (renewal_time) for recovery.

        if subscription:
            print u"{} *** Unsubscribing from SONOS device events".format(datetime.now()).encode('utf-8')
            try:
                subscription.unsubscribe()
                soco.events.event_listener.stop()
            except Exception as e:
                print u"{} *** Unsubscribe failed: {}".format(datetime.now(), e).encode('utf-8')

        print u"{} *** Subscribing to SONOS device events".format(datetime.now()).encode('utf-8')
        try:
            subscription = sonos_device.avTransport.subscribe(requested_timeout=renewal_time, auto_renew=True)
        except Exception as e:
            print u"{} *** Subscribe failed: {}".format(datetime.now(), e).encode('utf-8')
            # subscription failed (e.g. sonos is disconnected for a longer period of time): wait 10 seconds
            # and retry
            time.sleep(10)
            continue

    try:
        event   = subscription.events.get(timeout=10)
        status  = event.variables.get('transport_state')

        if not status:
            print u"{} Invalid SONOS status: {}".format(datetime.now(), event.variables).encode('utf-8')

        if last_status != status:
            print u"{} SONOS play status: {}".format(datetime.now(), status).encode('utf-8')

        if last_status != 'PLAYING' and status == 'PLAYING':
            if not avr.get_power()['PW'] == 'ON':
                avr.set_power('ON')
            avr.set_source(MARANTZ_INPUT)
            if MARANTZ_VOLUME is not None:
                if not avr.get_volume()['MV'] == MARANTZ_VOLUME:
                    print 'im here'
                    time.sleep(2)
                    avr.set_volume(MARANTZ_VOLUME)
            #if MARANTZ_SOUNDPRG is not None:
            #    MARANTZ_set_value('MAIN:SOUNDPRG', MARANTZ_SOUNDPRG)
        if last_status == 'PLAYING' and status == 'PAUSED_PLAYBACK':
            if avr.get_source('SI') == MARANTZ_INPUT:
                if not avr.get_power()['PW'] == 'OFF':
                    avr.set_power('OFF')
        last_status = status
    except Queue.Empty:
        pass
    except KeyboardInterrupt:
        handle_sigterm()

    if break_loop:
        subscription.unsubscribe()
        soco.events.event_listener.stop()
        break
