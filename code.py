import os
import time
from traceback import format_exception

import board

from pumping_controller import PumpingController
from util.button import Button
from util.debug import Debug
from util.properties import Properties
from util.pump_motor_controller import PumpMotorController
from util.simple_timer import Timer
from util.water_level import WaterLevelReader

debug = Debug()
debug.print_debug("code","CircuitPython version " + str(os.uname().version))
debug.check_debug_enable()

properties = Properties(debug)

if properties.defaults["display_type"].lower() in ["i2c"]:
    from util.pumping_display import PumpingDisplay_i2c
    display = PumpingDisplay_i2c(debug, properties)
else:
    from util.pumping_display import PumpingDisplay
    display = PumpingDisplay(debug, properties)

buttons = Button([board.D0, board.D1, board.D2])
# buttons = Button([board.D10, board.D6, board.D9])

# Create the pump control object (turns pump on/off)
# Can be any GPIO pin, match accordingly
pump = PumpMotorController(board.D12, debug)

# Create the two water sensor controllers, (bottom, and top)
# Needs all the A pins, match bottom, middle, top sensors accord
if properties.defaults["wiring_option"] is None or properties.defaults["wiring_option"].lower() in ['2','t','test']:
    water_level_readers = [WaterLevelReader("Bottom", properties, board.D9, board.D9, debug),  # Bottom sensor
                           WaterLevelReader("Top", properties, board.D10, board.D10, debug)]  # Top sensor
else:
    water_level_readers = [WaterLevelReader("Bottom", properties, board.D5, board.D5, debug),  # Bottom sensor
                           WaterLevelReader("Top", properties, board.D6, board.D6, debug)]  # Top sensor

# Create the pumping controller
pumping = PumpingController(display, properties, board.LED, pump, water_level_readers, debug)

pump_start_time = None
pumping_state = "Not Started"
loop_count = 0

program_start_time = time.monotonic()

hello_response = pumping.remote_notifier.http.do_hello()
if not pumping.remote_notifier.http.success(hello_response):
    if isinstance(hello_response, dict):
        debug.print_debug("code","hello error  " + hello_response["text"])

display_timer = Timer()

while True:
    this_address = pumping.remote_notifier.http.ip_address
    button_value = buttons.button_pushed()
    if button_value >= 0:
        if button_value == 0:
            display.display_remote("status")
            pumping.remote_notifier.send_status_handshake(pumping.pump_state, pumping.create_status_object())
            display.display_status(this_address, pumping.pump_state, pumping.remote_notifier,
                                   program_start_time, pump_start_time, water_level_readers)
        if button_value > 0:
            pump.pump_on()
            time.sleep(10)
            pump.pump_on()

    loop_count += 1
    debug.check_debug_enable()
    try:
        pumping.check_water_level_state()

        debug.print_debug("code", "pump_state "+pumping.pump_state)
        debug.print_debug("code", "last_pump_state "+str(pumping.last_pump_state))

        if pumping.pump_state is pumping.ENGAGE_PUMP and  pumping.last_pump_state is pumping.PUMPING_VERIFIED:
            debug.print_debug("code", "Setting : pump_start_time")
            pump_start_time = time.monotonic()

        if pumping.last_pump_state != pumping.pump_state or display_timer.start_time is None or display_timer.is_timed_out():
            display.display_status(this_address, pumping.pump_state, pumping.remote_notifier,
                                   program_start_time, pump_start_time, water_level_readers)
            display_timer.start_timer(properties.defaults["display_interval"])

        if pumping.notify_remote():
            display.display_status(this_address, pumping.pump_state, pumping.remote_notifier,
                                   program_start_time, pump_start_time, water_level_readers)

        # If http failed, then ping again to attempt to reset http error
        if not pumping.remote_notifier.http.last_http_status_success():
            pumping.remote_notifier.http.ping_default()

        sleep_time = properties.defaults["sleep_time"]
        if sleep_time <1:
            sleep_time = .5
        elif sleep_time > 10:
            sleep_time = 10
        time.sleep(sleep_time)

    except Exception as e:
        # error = pumping.remote_notifier.http.str(format_exception(e))
        error = str(format_exception(e))
        print(error)
        pumping.remote_notifier.http.do_error_post("MAIN LOOP", "Error: " + error)
        debug.print_debug("code","Exception in main: "+error)
        display.display_error(error)
        pumping_state = "error"
        time.sleep(10)
        # display.display_status(this_address, pumping_state, program_start_time, pump_start_time, water_level_readers,
        #                       "Err")
        continue

