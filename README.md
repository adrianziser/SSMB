##SSMB (SIMPLE SONOS MARANTZ BRIDGE)

A simple python script which turns your avr on and off when a given sonos connect is playing, sets source and volume according to the settings


Automatically turns on a Marantz Receiver (and switches it to the appropriate input) when a Sonos Connect starts playing and turns of your Receiver if the Sonos Connects pauses.

What this does:

Start this as a daemon (sample init.d-script included). It connects to your Sonos Connect and your Marantz Receiver. Whenever the Sonos Connect starts playing music, radio or whatever, it turns on the Receiver, switches to the appropriate input and sets the volume.

If the Receiver is already turned on, it just switches the input and leaves the rest alone.


Optimized for minimum use of resources. I leave this running on a Raspberry Pi at my place. An A model should suffice. And it would still be bored 99% of the time.

Before installing it as a daemon, try it out first: Adapt the settings in the script below. Then just run the script. It'll auto-discover your Sonos Connect. If that fails (e.g. because you have more than one Connect in your home or for other reasons), you can use the UID of your Sonos Connect as the first and only parameter of the script. The script will output all UIDs neatly for your comfort.

Prerequisites:
- Your Marantz Receiver has to be connected to the LAN.
- Both your Marantz Receiver and your Sonos Connect have to use fixed IP
  addresses. You probably have to set this in your router (or whichever
  device is your DHCP).
- Your Marantz Receiver's setting of "Network Standby" has to be "On".
  Otherwise the Receiver cannot be turned on from standby mode.

Software prerequisites:
- sudo pip install soco

##Credits
[MarantzIP](https://github.com/iamcanadian2222/MarantzIP/)

[Sonos-Monitor](https://github.com/michaelotto/sonos-monitor/)
