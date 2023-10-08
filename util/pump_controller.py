import board
import digitalio


class PumpController:
    def __init__(self, pump_pin: board.pin):
        self.relay = digitalio.DigitalInOut(pump_pin)
        self.relay.direction = digitalio.Direction.OUTPUT
        self.running = False
        self.debug = False
        self.relay.value = False

    def pump_on(self):
        self.running = True
        if self.debug:
            print("Pump on")
        self.relay.value = True

    def pump_off(self):
        self.running = False
        if self.debug:
            print("Pump off")
        self.relay.value = False
