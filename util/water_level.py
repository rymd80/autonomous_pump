import board
import digitalio
import analogio

from util.debug import Debug
from util.properties import Properties

LOW_VALUE = 36000
EMPTY_VALUE = 11000


class WaterLevelReader:
    DRY = "dry"
    WET = "+WET+"

    def __init__(self, name, properties: Properties, enable_pin: board.pin,water_level_pin: board.pin, debug: Debug):
        self.name = name
        self.properties = properties

        # self.water_level_sensor = analogio.AnalogIn(water_level_pin)
        self.water_level_sensor = digitalio.DigitalInOut(water_level_pin)
        self.water_level_sensor.switch_to_input(pull=digitalio.Pull.UP)
        self.debug = debug

    def get_water_state(self):
        # If the float is not floating, there will be a value, which means it's dry.
        # If the float is floating, there will not be a value which means it's wet.
        # self.debug.print_debug(self.name + " value "+str(self.water_level_sensor.value)
        return self.DRY if self.water_level_sensor.value else self.WET

    def water_present(self):
        water_present = self.get_water_state() != self.DRY
        return water_present

    def print_water_state(self):
        current_state = str(self.get_water_state())
        # self.debug.print_debug(self.name+" "+str(current_state))
        return self.name[0:1] + " " + str(current_state)

# *************************************************************************************************
# *****ANALOG (other sensor) **********************************************************************
# *************************************************************************************************


class WaterLevelReaderAnalog:
    DRY = "dry"
    WET = "wet"

    def __init__(self, name, properties: Properties, enable_pin: board.pin, water_level_pin: board.pin,
                 debug: Debug):
        self.name = name
        self.water_level = None
        self.properties = properties

        # "Other" water level sensors
        self.water_enable = digitalio.DigitalInOut(enable_pin)
        self.water_enable.switch_to_output()
        self.water_level_sensor = analogio.AnalogIn(water_level_pin)

        self.empty_value = properties.defaults["water_levels"][name]
        self.debug = debug
        # self.dry_level = EMPTY_VALUE
        self.dry_level = self.empty_value
        self.wet_level = None
        # self.wet_level = LOW_VALUE

    # Allows the outside to easily tweak the on/off level triggers if/when defaults don't work for a give sensor
    def set_dry_wet(self, dry: int, wet: int):
        self.dry_level = dry
        self.wet_level = wet

    def get_water_level(self):
        self.water_enable.value = True
        millivolts = int(self.water_level_sensor.value * (self.water_level_sensor.reference_voltage * 1000 / 65535))
        self.water_level = self.water_level_sensor.value
        self.debug.print_debug("water_level","milli volts "+str(millivolts))
        self.debug.print_debug("water_level","water_level "+str(self.water_level))
        self.water_enable.value = False
        return self.water_level

    def get_water_state(self):
        water_state = self.WET
        level = self.get_water_level()
        # self.debug.print_debug("water_level","Before getting water state "+str(level))
        if level >= self.dry_level:
            water_state = self.DRY
        self.debug.print_debug("water_level","get_water_state: "+
            self.name + " level value [" + str(self.empty_value) + "/" + str(self.water_level) + "] state " + str(
                water_state))
        # self.debug.print_debug("water_level","After getting water state "+water_state)
        return water_state

    def water_present(self):
        water_present = self.get_water_state() != self.DRY
        return water_present

    def print_water_state(self):
        current_state = str(self.get_water_state())
        self.debug.print_debug(
            self.name + " level value [" + str(self.empty_value) + "/" + str(self.water_level) + "] state " + str(
                current_state))
        return self.name[0:1] + " [" + str(self.empty_value) + "/" + str(self.water_level) + "] " + current_state
