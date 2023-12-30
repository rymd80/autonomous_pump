import time
from traceback import format_exception

import board
import digitalio

from util.debug import Debug
from util.properties import Properties
from util.pump_motor_controller import PumpMotorController
from util.remote_event_notifier import RemoteEventNotifier
from util.simple_timer import Timer
from util.water_level import WaterLevelReader
from util.pumping_display import PumpingDisplay

bottom = 0
top = 1


def get_pumping_id():
    return str(int(time.time() * 1000))


class PumpingController:
    IDLE = "idle"
    READY_TO_PUMP = "ready"
    PUMPING_CANCELED = "canceled"
    PUMPING_STOPPED = "stopped"
    PUMPING_STARTED = "started"
    START_PUMPING = "start"
    STOP_PUMPING = "stop"
    ENGAGE_PUMP = "pumping"
    PUMPING_VERIFY = "verify"
    PUMPING_VERIFIED = "verified"
    PUMPING_TIMED_OUT = "timed_out"
    REMOTE_NOTIFIER_ERROR = "remote_error"
    UNKNOWN = "unknown"



    def __init__(self,display:PumpingDisplay, properties: Properties, led: board.pin, pump: PumpMotorController,
                 water_level_readers: list[WaterLevelReader], debug: Debug):
        self.display = display
        self.properties = properties
        self.led = digitalio.DigitalInOut(led)
        self.led.direction = digitalio.Direction.OUTPUT
        self.water_level_readers = water_level_readers
        self.debug = debug
        self.error_string = "No Error"
        self.unknown_count = 0
        self.pump = pump
        self.pumping_started_flag = False
        self.pumping_verified_flag = False
        self.pump_state = None
        self.last_pump_state = None
        self.last_remote_cmd = None
        self.need_to_send_remote_pumping_started = False
        self.remote_notifier = RemoteEventNotifier(properties, debug)
        self.timer = Timer()
        self.idle_timer = Timer()
        self.seconds_to_wait_for_pumping_verification = self.properties.defaults["seconds_to_wait_for_pumping_verification"]
        self.seconds_between_pumping_status_to_remote = self.properties.defaults["seconds_between_pumping_status_to_remote"]

    def set_and_return_state(self, state):
        self.last_pump_state = self.pump_state
        self.pump_state = state
        return state

    def handle_remote_response(self, success_state, remote_response):
        if self.remote_notifier.http.success(remote_response):
            return success_state
        else:
            # If we get a remote error, always stop pumping.
            # If water level is high enough, it will again try to pump.
            self.stop_pumping(self.REMOTE_NOTIFIER_ERROR)
            try:
                self.error_string = self.remote_notifier.http.get_response_text(remote_response)
            except Exception as e:
                None
            return self.REMOTE_NOTIFIER_ERROR

    def stop_pumping(self,pumping_state):
        self.debug.print_debug("controller","**** stop_pumping **** ("+pumping_state+")")
        self.pump.pump_off()
        self.timer.cancel_timer()
        self.pumping_started_flag = False
        self.pumping_verified_flag = False
        self.remote_notifier.http.reset_id()

    def blink(self):
        for times in range(0, 2):
            # three quick blinks
            for blink in range(0, 4):
                self.led.value = True
                time.sleep(0.05)
                self.led.value = False
                time.sleep(0.05)

            # one longer blink
            self.led.value = True
            time.sleep(0.5)
            self.led.value = False
            time.sleep(0.1)

    def create_status_object(self):
        water_level_state = self.get_water_state(self.pumping_started_flag, self.pumping_verified_flag)
        return {
            "water_level_state": water_level_state,
            "pump_running": str(self.pump.running),
            "pumping_started_flag": str(self.pumping_started_flag),
            "pumping_verified": str(self.pumping_verified_flag),
            "top_sensor_level": self.water_level_readers[top].print_water_state(),
            "bottom_sensor_level": self.water_level_readers[bottom].print_water_state()
        }

    # Uses water level in the three water measurement sensors to return a water state
    def get_water_state(self, pumping_started, pumping_verified):
        bottom_has_water = self.water_level_readers[bottom].water_present()
        top_has_water = self.water_level_readers[top].water_present()

        if not bottom_has_water and not top_has_water:
            return self.IDLE

        elif not pumping_started and bottom_has_water and not top_has_water:
            return self.READY_TO_PUMP

        # Once the pumping_started flag look for the bottom to have water, but the top doesn't have water.
        # This state verifies the pump is working.
        # NOTE: We use the flag pumping_verified to allow the next elif to get executed after the verification
        elif not pumping_verified and pumping_started and bottom_has_water and not top_has_water:
            return self.PUMPING_VERIFIED

        # Once the pumping_started flag set, we stay pumping until the bottom water_level has no water
        elif not pumping_started and bottom_has_water and top_has_water:
            return self.ENGAGE_PUMP

        elif pumping_started and bottom_has_water:
            return self.ENGAGE_PUMP

        else:
            self.debug.print_debug("controller","UNKNOWN STATE: bottom has water %s, top has water %s, pumping_started %s"
                                   % (str(bottom_has_water), str(top_has_water), str(pumping_started)))
            return self.UNKNOWN

    # This is the main pumping logic method
    def check_water_level_state(self):
        self.error_string = "No Error"  # If an error is generated, the error string only lasts for one call
        self.debug.print_debug("controller","check_state: pump_state[%s], pumping_started_flag[%s], pumping_verified[%s]" %
                               (self.pump_state, self.pumping_started_flag, self.pumping_verified_flag))

        if self.pump_state is None:
            self.pump.pump_off()
            self.pumping_started_flag = False
            self.pumping_verified_flag = False
            self.idle_timer.start_timer(self.seconds_between_pumping_status_to_remote)
            self.need_to_send_remote_pumping_started = False
            return self.set_and_return_state(self.IDLE)
        # elif self.pump_state  == self.IDLE:
        #     self.pump.pump_off()
        #     self.pumping_started_flag = False
        #     self.pumping_verified_flag = False

        # Timer starts when pumping starts.
        # Timer canceled as soon as the pumping verification happens
        if self.timer.is_timed_out():
            self.debug.print_debug("controller","TIMED OUT. Elapsed: " + self.timer.get_elapsed())
            self.stop_pumping(self.PUMPING_TIMED_OUT)
            self.remote_notifier.http.do_error_post("TIMED OUT", "Elapsed: " + self.timer.get_elapsed())
            self.timer.cancel_timer()
            self.display.display_remote("timeout")
            self.remote_notifier.missed_pumping_verification(self.pump_state)
            # TEMP code, not sure what to do after a timeout
            # For now reset, set last_state to idle and return
            # The calling loop will re-evaluate automatically
            self.pump.pump_off()
            self.pumping_started_flag = False
            self.pumping_verified_flag = False
            self.need_to_send_remote_pumping_started = False
            return self.set_and_return_state(self.IDLE)
            # return self.handle_remote_response(self.PUMPING_TIMED_OUT,
            #                                    self.remote_notifier.missed_pumping_verification(self.pump_state))

        # After remote status and timer check, it's time to read the water levels
        # and see if we need to change state, i.e. start or stop pump
        water_level_state = self.get_water_state(self.pumping_started_flag, self.pumping_verified_flag)
        # self.debug.print_debug("controller","water_level_state "+water_level_state)

        # If we get weird, bogus reading and water level state can't be computed, then return to try again

        if water_level_state == self.UNKNOWN:
            self.pump.pump_off()
            self.need_to_send_remote_pumping_started = False
            self.pumping_started_flag = False
            self.pumping_verified_flag = False
            self.unknown_count += 1
            time.sleep(2)
            if self.unknown_count > 10:
                self.unknown_count = 0
                self.display.display_remote("unknown state")
                return self.handle_remote_response(self.UNKNOWN,
                                                   self.remote_notifier.send_unknown_status(self.pump_state))
            else:
                return self.set_and_return_state(self.UNKNOWN)

        try:
            # If we've been pumping and the bottom water measurement has no water, stop pumping
            if water_level_state == self.IDLE:
                self.stop_pumping(self.STOP_PUMPING)
                return self.set_and_return_state(self.IDLE)

            # If the last state was idle and now the bottom water level sensor has water, then set READY_TO_PUMP
            elif self.pump_state == self.IDLE and water_level_state == self.READY_TO_PUMP:
                # Setup for pump start and verification
                self.pumping_started_flag = False
                self.pumping_verified_flag = False
                self.need_to_send_remote_pumping_started = False
                return self.set_and_return_state(self.READY_TO_PUMP)

            # If the last state was READY_TO_PUMP and the top water level still has no water, then keep READY_TO_PUMP
            # Note: This elif gets executed many times until the top water measurement has water, and we start pumping.
            elif self.pump_state == self.READY_TO_PUMP and water_level_state == self.READY_TO_PUMP:
                return self.set_and_return_state(self.READY_TO_PUMP)

            # After pumping has started, wait for the pumping verification.
            # The middle water measurement sensor should be fairly physically close to the top water measurement sensor,
            #      the water doesn't have to go down much to validate the pump is moving water out.
            # There is a flag to avoid doing this a second time.
            # NOTE: You should probably time how long it takes the pump to lower the water below the top water
            #            measurement and set seconds_to_wait_for_pumping_verification accordingly.
            #            The timeout default is 5 minutes.
            elif not self.pumping_verified_flag and \
                    self.pump_state == self.ENGAGE_PUMP and water_level_state == self.PUMPING_VERIFIED:
                # When we get the pumping verification, turn off timer (we don't need it anymore)
                self.timer.cancel_timer()
                self.pumping_verified_flag = True
                # Only send a pump event notification to remote only if pumping_verified
                self.need_to_send_remote_pumping_started = True
                # We didn't stop pump, we are still pumping, return that the verification state has been reached
                # self.blink()
                return self.set_and_return_state(self.PUMPING_VERIFIED)

            # If we haven't started pumping and the last pump state is READY_TO_PUMP and
            # the top water measurement sensor has water, start pumping
            # It's possible to turn on and start pumping.
            # If last pump state is IDLE, and we have water, then also start pumping
            elif ((self.pump_state == self.IDLE or self.pump_state == self.READY_TO_PUMP)
                  and water_level_state == self.ENGAGE_PUMP):
                # When we start pumping, then start pumping verification timer
                self.timer.start_timer(self.seconds_to_wait_for_pumping_verification)

                # Drop through and start pumping

            # In pumping state
            # Only blink when pumping
            self.pumping_started_flag = True
            self.pump.pump_on()
            self.idle_timer = Timer()
            # self.blink()
            return self.set_and_return_state(self.ENGAGE_PUMP)
        except Exception as e:
            self.error_string = str(format_exception(e))
            self.remote_notifier.http.do_error_post("check_water_level_state", str(e))
            return self.REMOTE_NOTIFIER_ERROR

    def notify_remote(self):

        did_remote_display = False
        if self.last_pump_state is self.READY_TO_PUMP and self.pump_state == self.IDLE:
            # Can miss notify if state goes from ready back to idle
            self.last_remote_cmd = self.IDLE

        if self.pump_state == self.IDLE:
            if (self.need_to_send_remote_pumping_started):
                # If Ping failed, then no need to do remote command, display error and return
                if not self.remote_notifier.http.last_http_status_success():
                    return
                self.need_to_send_remote_pumping_started = False
                self.idle_timer.reset_timer(self.seconds_between_pumping_status_to_remote)
                self.last_remote_cmd = self.ENGAGE_PUMP
                self.display.display_remote("pump event")
                did_remote_display = True
                return self.handle_remote_response(self.ENGAGE_PUMP,
                                                   self.remote_notifier.pump_event(self.ENGAGE_PUMP))

            if self.idle_timer.start_time is None or self.idle_timer.is_timed_out():
                # Don't flood the server with pumping status
                self.idle_timer.start_timer(self.seconds_between_pumping_status_to_remote)
                try:
                    # At the start of very loop event, check-in with remote in case it wants to change our state
                    # Plus let them know our current state, so the remote can validate our current state
                    # NOTE: All remote_cmd command must be ACKed to ensure communication is healthy.
                    #       After ack is received on remote, it goes into idle state waiting for normal status processing
                    #       If ack is not received within remote timeout period, a notification email or text is sent.
                    self.display.display_remote("status")
                    did_remote_display = True
                    self.last_remote_cmd = "status"
                    response = self.remote_notifier.send_status_handshake(self.pump_state, self.create_status_object())
                    # Set timer for next remote status call
                    self.idle_timer.start_timer(self.seconds_between_pumping_status_to_remote)

                    if hasattr(response, "status_code"):
                        self.debug.print_debug("controller","remote_cmd return-code " + str(response.status_code) + " text " + self.remote_notifier.http.get_response_text(response))

                    remote_cmd = self.remote_notifier.http.remote_cmd  # remote_cmd is returned in server json.

                    if remote_cmd == self.PUMPING_CANCELED:
                        # Canceled happens during pumping when pump verification times out on remote,
                        # and it attempts a stop us.
                        # This should only happen if there is something wrong with pump, and it's not pumping.
                        # NOTE: Both sides go into idle and this side will attempt to start pumping again
                        #       if the water level measurements trigger the pump.
                        # This is like a reset. There is no "permanent" stop pumping.
                        self.stop_pumping(self.PUMPING_CANCELED)
                        return (
                            self.handle_remote_response(
                                self.PUMPING_CANCELED,
                                self.remote_notifier.send_pumping_canceled_ack(self.pump_state)))
                    elif remote_cmd == self.START_PUMPING:
                        # For what ever reason, the remote can turn on pump
                        # This has not been tested to see if this code will handle gracefully
                        self.pump_state = self.ENGAGE_PUMP
                        self.pump.pump_on()
                        return self.handle_remote_response(
                            self.PUMPING_STARTED,
                            self.remote_notifier.send_start_pumping_ack(self.pump_state))
                    elif remote_cmd == self.STOP_PUMPING:
                        # Remote can signal to stop pumping at anytime
                        # NOTE: Both sides go into idle and this side will start pumping again
                        #       if the water level measurements trigger the pump.
                        # This is like a reset. There is no "permanent" stop pumping.
                        self.stop_pumping(self.STOP_PUMPING)
                        self.pump_state = self.IDLE
                        return self.handle_remote_response(
                            self.PUMPING_STOPPED,
                            self.remote_notifier.send_stop_pumping_ack(self.pump_state))
                except Exception as e:
                    print("WARNING: Remote communication failed. Error: %s" % str(format_exception(e)))
                    self.remote_notifier.http.do_error_post("status handshake", str(format_exception(e)))

        elif (self.last_remote_cmd != self.READY_TO_PUMP and
              (self.last_pump_state != self.READY_TO_PUMP and self.pump_state == self.READY_TO_PUMP)):
            # If Ping failed, then no need to do remote command, display error and return
            if not self.remote_notifier.http.last_http_status_success():
                return
            self.last_remote_cmd = self.READY_TO_PUMP
            self.display.display_remote("ready to pump")
            did_remote_display = True
            return self.handle_remote_response(self.READY_TO_PUMP,
                                               self.remote_notifier.send_ready_to_pump(self.pump_state))

        # elif self.last_remote_cmd != self.PUMPING_VERIFIED and self.pump_state == self.PUMPING_VERIFIED:
        #     if self.remote_notifier.http.last_status_code == "Ping Fail":
        #         return
        #     self.last_remote_cmd = self.PUMPING_VERIFIED
        #     return self.handle_remote_response(self.PUMPING_VERIFIED,
        #                                        self.remote_notifier.pumping_confirmed(self.pump_state))

        return did_remote_display