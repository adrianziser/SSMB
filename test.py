from queue import Empty

import logging
logging.basicConfig()
import soco
from pprint import pprint
from soco.events import event_listener
# pick a device at random and use it to get
# the group coordinator
device = soco.SoCo("192.168.11.32")
print (device.player_name)
#sub = device.renderingControl.subscribe()
sub2 = device.avTransport.subscribe()

while True:
    # try:
    #     event = sub.events.get(timeout=0.5)
    #     pprint (event.variables)
    # except Empty:
    #     pass
    try:
        event = sub2.events.get(timeout=0.5)
        pprint (event.variables)
    except Empty:
        pass

    except KeyboardInterrupt:
        print("STOP")
        #sub.unsubscribe()
        sub2.unsubscribe()
        event_listener.stop()
        break