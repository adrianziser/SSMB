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
# - sudo pip install denonavr
# - sudo pip install aiohttp

import os
from soco import events_asyncio
from pprint import pprint
from datetime import datetime
import logging
import denonavr
import asyncio
import signal
import soco
import time
import sys


class Unbuffered(object):
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def writelines(self, datas):
        self.stream.writelines(datas)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


soco.config.EVENTS_MODULE = events_asyncio

__version__ = '0.4'


# --- Please adapt these settings ---------------------------------------------
# logging.basicConfig(level=logging.NOTSET)
# The UUID of your device, if you dont have it, we will try to search for it later
SONOS_UUID = 'RINCON_949F3EB99CCA01400'
# IP address of your MARANTZ Receiver. Look it up in your router or set it in the Receiver menu.
MARANTZ_IP = '192.168.11.4'
# The ip address of your device, if you dont have it, we will try to search for it later
SONOS_IP = '192.168.11.27'
# Name of your Receiver's input the Sonos Connect is connected to. Should be one
MARANTZ_INPUT = 'CD'
# of AV1, AV2, ..., HDMI1, HDMI2, ..., AUDIO1, AUDIO2, ..., TUNER, PHONO, V-AUX, DOCK,
# iPod, Bluetooth, UAW, NET, Napster, PC, NET RADIO, USB, iPod (USB) or the like.
# Don't use an input name you set yourself in the Receiver's setup menu.
# Volume the Receiver is set to when started. -20.0 equals 60 on Marantz devices. Set to None if you don't want to change it.
MARANTZ_VOLUME = -15.0
# DSP Sound Program to set the Receiver to when started. Set to None if you don't want to change it.
MARANTZ_SOUNDPRG = '5ch Stereo'
avr = None
break_loop = False
global last_status
last_status = None
sonos_device = None
renewal_time = 120
subscription = None


async def main():
    print("SSMB launched")
    # --- Connect to Marantz AVR --------------------------------------------------
    await setup_avr()
    avr.register_callback("ALL", update_avr_callback)

    # --- Discover SONOS zones ----------------------------------------------------

    if len(sys.argv) == 2:
        connect_uid = sys.argv[1]
    else:
        connect_uid = SONOS_UUID

    global sonos_device
    sonos_device = soco.SoCo(SONOS_IP)

    # --- Initial MARANTZ status ---------------------------------------------------

    print("MARANTZ Power status:  " + avr.power)
    print("MARANTZ Input select:  " + avr.input_func)
    print("MARANTZ Volume:        " + str(avr.volume))
    print()

    # --- Main loop ---------------------------------------------------------------
    # catch SIGTERM gracefully
    signal.signal(signal.SIGTERM, handle_sigterm)
    # non-buffered STDOUT so we can use it for logging
    sys.stdout = Unbuffered(sys.stdout)

    while True:
        # if not subscribed to SONOS connect for any reason (first start or disconnect while monitoring), (re-)subscribe
        if not subscription or not subscription.is_subscribed or subscription.time_left <= 5:
            # The time_left should normally not fall below 0.85*renewal_time - or something is wrong (connection lost).
            # Unfortunately, the soco module handles the renewal in a separate thread that just barfs  on renewal
            # failure and doesn't set is_subscribed to False. So we check ourselves.
            # After testing, this is so robust, it survives a reboot of the SONOS. At maximum, it needs 2 minutes
            # (renewal_time) for recovery.
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(check_subscription())
                threshold = renewal_time - 5
                while threshold != 0 and not break_loop:
                    await asyncio.sleep(1)
                    threshold-=1
            except KeyboardInterrupt:
                handle_sigterm()
        if break_loop:
            print("{} *** Unsubscribing from SONOS device {} events".format(datetime.now(),sonos_device.player_name))
            await subscription.unsubscribe()
            await events_asyncio.event_listener.async_stop()
            break


async def check_subscription():
    global subscription
    if subscription:
        print("{} *** Unsubscribing from SONOS device {} events".format(datetime.now(),sonos_device.player_name))
        try:
            subscription.unsubscribe()
            await events_asyncio.event_listener.async_stop()

        except Exception as e:
            print('{} *** Unsubscribe for renewal failed: {}'.format(datetime.now(), e))

    print("{} *** Subscribing to SONOS device {} events".format(datetime.now(),sonos_device.player_name))
    try:
        subscription = await sonos_device.avTransport.subscribe(requested_timeout=renewal_time, auto_renew=True)
        subscription.callback = update_sonos_callback
    except Exception as e:
        print("{} *** Subscribe failed: {}".format(datetime.now(), e))
        # subscription failed (e.g. sonos is disconnected for a longer period of time): wait 10 seconds
        # and retry
        time.sleep(10)


def handle_sigterm(*args):
    global break_loop
    print(("SIGTERM caught. Exiting gracefully."))
    break_loop = True
    return


async def update_avr_callback(zone, event, parameter):
    print("{} Marantz callback #zone: {} #event: {} #parameter: {}".format(datetime.now(), zone, event, parameter))
    return


def update_sonos_callback(event):
    status = event.variables.get('transport_state')
    global last_status
    print(str(datetime.now()) + " Callback fired, last status is " + str(last_status) + " status is: "+str(status))

    loop = asyncio.get_event_loop()
    if not status:
        print("{} Invalid SONOS status: {}".format(datetime.now(), event.variables))

    if last_status != status:
        print("{} SONOS play status: {}".format(datetime.now(), status))

    if (last_status != 'PLAYING' and status == 'PLAYING'):
        if not avr.power == 'ON':
            print("{} Set AVR to status ON".format(datetime.now()))
            loop.create_task(avr.async_power_on())
        loop.create_task(avr.async_set_input_func(MARANTZ_INPUT))

        if MARANTZ_VOLUME is not None:
            if not avr.volume == MARANTZ_VOLUME:
                time.sleep(5)
                print("{} Set AVR volume to 65".format(datetime.now()))
                loop.create_task(avr.async_set_volume(MARANTZ_VOLUME))
        # if MARANTZ_SOUNDPRG is not None:
        #    MARANTZ_set_value('MAIN:SOUNDPRG', MARANTZ_SOUNDPRG)
    if last_status == 'PLAYING' and status == 'PAUSED_PLAYBACK':
        if avr.input_func == MARANTZ_INPUT:
            if not avr.power == 'OFF':
                print("{} Set AVR to status ON".format(datetime.now()))
                loop.create_task(avr.async_power_off())
    last_status = status
    return


async def setup_avr():
    global avr
    avr = denonavr.DenonAVR(MARANTZ_IP)
    # test connectivity
    await avr.async_setup()
    await avr.async_telnet_connect()
    await avr.async_update()
    return

try:
    loop = asyncio.get_running_loop()
except RuntimeError:  # 'RuntimeError: There is no current event loop...'
    loop = None

if loop and loop.is_running():
    print('Async event loop already running. Adding coroutine to the event loop.')
    tsk = loop.create_task(main())
    # ^-- https://docs.python.org/3/library/asyncio-task.html#task-object
    # Optionally, a callback function can be executed when the coroutine completes
    tsk.add_done_callback(
        lambda t: print(f'Task done with result={t.result()}  << return val of main()'))
else:
    print()
    print("------------------------------------")
    print('Fresh start, starting new event loop')
    result = asyncio.run(main())
