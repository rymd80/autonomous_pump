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

have_sent_startup_notification = False
startup_notification_timer = None

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
    if not have_sent_startup_notification:
        # Only send startup notification once
        # This will keep attempting the notification every 30 seconds until successful
        if pumping.remote_notifier.http.last_http_status_success():
            if startup_notification_timer is None or startup_notification_timer.is_timed_out():
                display.display_remote("startup notification")
                response = pumping.remote_notifier.send_startup_notification(properties.defaults)
                if pumping.remote_notifier.http.success(response):
                    have_sent_startup_notification = True
                else:
                    # Only attempt to send startup notification every 30 seconds
                    startup_notification_timer = Timer()
                    startup_notification_timer.start_timer(30)
        else:
            debug.print_debug("code", "Didn't sent startup remote notification due to http error")

    this_address = pumping.remote_notifier.http.ip_address
    button_value = buttons.button_pushed()
    if button_value >= 0:
        if button_value == 0:
            debug.print_debug("code", "button 0 pressed -- set remote status")
            display.display_remote("status")
            pumping.remote_notifier.send_status_handshake(pumping.pump_state, pumping.create_status_object())
            # Reset idle timer to not send another status for seconds_between_pumping_status_to_remote seconds
            pumping.idle_timer.reset_timer(pumping.seconds_between_pumping_status_to_remote)
        elif button_value ==1:
            debug.print_debug("code", "button 1 pressed -- turn pump on for 10 seconds")
            display.display_messages(["pump on"])
            pump_timer = Timer()
            pump_timer.start_timer(30) # Will run pump max of 30 seconds (or when empty)
            pump.pump_on()
            while True:
                if not water_level_readers[0].water_present() and not water_level_readers[1].water_present():
                    break
                if pump_timer.is_timed_out():
                    break
                time.sleep(.1)
            pump.pump_off()
            display.display_messages(["pump off"])
            time.sleep(5)
        elif button_value ==2:
            debug.print_debug("code", "button 2 pressed - toggle debug stage")
            # Toggles debug flag (without reloading program)
            debug.toggle_local_debug()
            display.display_messages(["local-debug "+str(debug.local_set),"debug "+str(debug.debug)])
            time.sleep(5)
        display.display_status(this_address, pumping.pump_state, pumping.remote_notifier,
                               program_start_time, pump_start_time, water_level_readers)

    loop_count += 1
    debug.check_debug_enable()
    try:
        pumping.check_water_level_state()

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
            sleep_time = .2
        elif sleep_time > 5:
            sleep_time = 5
        time.sleep(sleep_time)

    except Exception as e:
        # error = pumping.remote_notifier.http.str(format_exception(e))
        error = str(format_exception(e))
        pumping.remote_notifier.http.do_error_post("MAIN LOOP", "Error: " + error)
        debug.print_debug("code","Exception in main: "+error)
        display.display_error(["Exception in main",str(e)])
        pumping_state = "error"
        time.sleep(10)
        # display.display_status(this_address, pumping_state, program_start_time, pump_start_time, water_level_readers,
        #                       "Err")
        continue

