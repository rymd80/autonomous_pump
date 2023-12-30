import board
import digitalio
from util.debug import Debug


class PumpMotorController:
    def __init__(self, pump_pin: board.pin, debug: Debug):
        self.debug = debug
        self.relay = digitalio.DigitalInOut(pump_pin)
        self.relay.direction = digitalio.Direction.OUTPUT
        self.running = False
        self.relay.value = False

    def pump_on(self):
        self.running = True
        self.debug.print_debug("pump", "Pump ON")
        self.relay.value = True

    def pump_off(self):
        self.running = False
        self.debug.print_debug("pump", "Pump OFF")
        self.relay.value = False
