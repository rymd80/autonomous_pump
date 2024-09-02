import time
from traceback import format_exception

import board
import digitalio

from util.debug import Debug
from util.http_functions import get_response_text
from util.properties import Properties
from util.pump_motor_controller import PumpMotorController
from util.remote_event_notifier import RemoteEventNotifier
from util.simple_timer import Timer
from util.water_level import WaterLevelReader
from util.pumping_display import PumpingDisplay

# Variables to help keep track of which water level sensor is the top and which to bottom.
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
        self.last_pump_elapsed_time = None
        self.need_to_send_remote_pumping_started = False
        self.pump_start_time = None
        self.pump_event_count = 0
        self.remote_notifier = RemoteEventNotifier(properties, debug)
        self.timer = Timer()
        self.idle_timer = Timer()
        self.seconds_to_wait_for_pumping_verification = self.properties.defaults["seconds_to_wait_for_pumping_verification"]
        self.seconds_between_pumping_status_to_remote = self.properties.defaults["seconds_between_pumping_status_to_remote"]
        self.seconds_to_pump_before_timeout = self.properties.defaults["seconds_to_pump_before_timeout"]

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
                self.error_string = get_response_text(remote_response)
            except Exception as e:
                pass
            return self.REMOTE_NOTIFIER_ERROR

    def stop_pumping(self,pumping_state):
        self.debug.print_debug("controller","**** stop_pumping **** ("+pumping_state+")")
        self.pump.pump_off()
        self.timer.cancel_timer()
        self.pumping_started_flag = False
        self.pumping_verified_flag = False
        self.remote_notifier.http.reset_id()

    def create_status_object(self):
        water_level_state = self.get_water_state_action()
        return {
            "pump_state": self.pump_state,
            "water_level_state": water_level_state,
            "pumping_started_flag": str(self.pumping_started_flag),
            "pumping_verified_flag": str(self.pumping_verified_flag),
            "top_sensor_level": self.water_level_readers[top].print_water_state(),
            "bottom_sensor_level": self.water_level_readers[bottom].print_water_state(),
            "last_pump_elapsed_time": self.last_pump_elapsed_time,
            "pump_event_count": self.pump_event_count,
            "last_http_code": self.remote_notifier.http.last_status_code,
            "last_http_error": self.remote_notifier.http.last_error
        }

    # Uses water level in the two water measurement sensors to return a water state action
    # This method is highly coupled with check_water_level_state to walk through the pumping lifecycle
    def get_water_state_action(self):
        bottom_has_water = self.water_level_readers[bottom].water_present()
        top_has_water = self.water_level_readers[top].water_present()

        if not bottom_has_water and not top_has_water:
            return self.IDLE

        elif not self.pumping_started_flag and bottom_has_water and not top_has_water:
            return self.READY_TO_PUMP

        # Once the pumping_started flag look for the bottom to have water, but the top doesn't have water.
        # This state verifies the pump is working.
        # NOTE: We use the flag pumping_verified to allow the next elif to get executed after the verification
        elif not self.pumping_verified_flag and self.pumping_started_flag and bottom_has_water and not top_has_water:
            return self.PUMPING_VERIFIED

        # Once the pumping_started flag set, we stay pumping until the bottom water_level has no water
        elif not self.pumping_started_flag and bottom_has_water and top_has_water:
            return self.ENGAGE_PUMP

        elif self.pumping_started_flag and bottom_has_water:
            return self.ENGAGE_PUMP

        else:
            self.debug.print_debug("controller","UNKNOWN STATE: bottom has water %s, top has water %s, pumping_started %s"
                                   % (str(bottom_has_water), str(top_has_water), str(self.pumping_started_flag)))
            return self.UNKNOWN

    # This is the main pumping logic method
    def check_water_level_state(self):
        self.error_string = "No Error"  # If an error is generated, the error string only lasts for one call
        self.debug.print_debug("controller","check_state: pump_state[%s], last_pump_state[%s], pumping_started_flag[%s], pumping_verified[%s]" %
                               (self.pump_state, self.last_pump_state, self.pumping_started_flag, self.pumping_verified_flag))

        if self.pump_state is None:
            self.pump.pump_off()
            self.pumping_started_flag = False
            self.pumping_verified_flag = False
            self.idle_timer.start_timer(self.seconds_between_pumping_status_to_remote)
            self.need_to_send_remote_pumping_started = False
            return self.set_and_return_state(self.IDLE)

        # Timer starts when pumping starts.
        # Timer canceled as soon as the pumping verification happens
        if self.timer.is_timed_out():
            self.debug.print_debug("controller","TIMED OUT. Elapsed: " + self.timer.get_elapsed())
            self.pump.pump_off()
            if self.pumping_verified_flag:
                # Have verification but pumping didn't finish on time so send pumping timeout
                self.display.display_remote("pumping timeout")
                self.remote_notifier.http.do_error_post("Pumping TIMED OUT", "Elapsed: " + self.timer.get_elapsed())
                self.remote_notifier.pumping_timout(self.pump_state,
                                            {"pumping_started_flag": str(self.pumping_started_flag),
                                                       "pumping_verified_flag": str(self.pumping_verified_flag)})
            else:
                # Haven't gotten pumping verification so send verification timeout
                self.display.display_remote("verification timeout")
                self.remote_notifier.http.do_error_post("PUMPING TIMED OUT", "Elapsed: " + self.timer.get_elapsed())
                self.remote_notifier.missed_pumping_verification(self.pump_state)

            self.need_to_send_remote_pumping_started = False # Gets set when pumping_verified_flag gets set
            self.pumping_started_flag = False
            self.pumping_verified_flag = False
            self.timer.cancel_timer()
            return self.set_and_return_state(self.IDLE)

        # After remote status and timer check, it's time to read the water levels
        # and see if we need to change state, i.e. start or stop pump
        water_level_state = self.get_water_state_action()

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
                if self.pumping_started_flag:
                    # For now... because of the extra gap between the bottom float and the bottom of the reservoir,
                    # if we've been pumping, keep pumping for another 30 seconds.
                    time.sleep(20)
                # Turn off pump and reset pumping and verification flags
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
                self.pumping_verified_flag = True
                # Only send a pump event notification to remote only if pumping_verified
                self.need_to_send_remote_pumping_started = True
                # Finishing the pumping is a timed event that starts when pumping verified
                self.timer.reset_timer(self.seconds_to_pump_before_timeout)
                # We didn't stop pump, we are still pumping, return that the verification state has been reached
                return self.set_and_return_state(self.PUMPING_VERIFIED)

            # It's possible to start pumping on startup if water level full
            # If last pump state is IDLE, and we have water, then also start pumping
            elif ((self.pump_state == self.IDLE or self.pump_state == self.READY_TO_PUMP)
                  and water_level_state == self.ENGAGE_PUMP):
                # When we start pumping, then start pumping verification timer
                self.timer.start_timer(self.seconds_to_wait_for_pumping_verification)
                # Drop through and start pumping

            if self.pump_start_time is None:
                self.pump_start_time = time.monotonic()

            self.pumping_started_flag = True
            self.pump.pump_on()
            self.idle_timer.reset_timer(self.seconds_between_pumping_status_to_remote)
            return self.set_and_return_state(self.ENGAGE_PUMP)
        except Exception as e:
            self.error_string = str(format_exception(e))
            self.remote_notifier.http.do_error_post("check_water_level_state", str(e))
            return self.REMOTE_NOTIFIER_ERROR

    # Handles the high level remote calls to send pumping info to the backend
    # The remote call can take some time so the backend calls are timed to avoid interfere with the pumping.
    def notify_remote(self):
        did_remote_display = False
        if self.last_pump_state is self.READY_TO_PUMP and self.pump_state == self.IDLE:
            # Can miss notify if state goes from ready back to idle
            self.last_remote_cmd = self.IDLE

        if self.pump_state == self.READY_TO_PUMP:
            self.check_idle_timer()

        if self.pump_state == self.IDLE:
            if (self.need_to_send_remote_pumping_started):
                # If Ping failed, then no need to do remote command, display error and return
                if not self.remote_notifier.http.last_http_status_success():
                    self.debug.print_debug("notify_remote", "not last_http_status_success, returning." )
                    return
                self.need_to_send_remote_pumping_started = False
                self.idle_timer.reset_timer(self.seconds_between_pumping_status_to_remote)
                self.last_pump_elapsed_time = time.monotonic() - self.pump_start_time
                self.pump_start_time = None
                self.pump_event_count += 1
                self.last_remote_cmd = self.ENGAGE_PUMP
                self.display.display_remote("pump event")
                did_remote_display = True
                self.timer.cancel_timer()
                self.remote_notifier.pump_event(self.ENGAGE_PUMP,
        {"last_pump_elapsed_time": self.last_pump_elapsed_time,"pump_event_count": self.pump_event_count})

            self.check_idle_timer()

        elif (self.last_remote_cmd != self.READY_TO_PUMP and
              (self.last_pump_state != self.READY_TO_PUMP and self.pump_state == self.READY_TO_PUMP)):
            # If Ping failed, then no need to do remote command, display error and return
            if not self.remote_notifier.http.last_http_status_success():
                return
            self.last_remote_cmd = self.READY_TO_PUMP
            self.display.display_remote("ready to pump")
            did_remote_display = True
            self.handle_remote_response(self.READY_TO_PUMP,
                                               self.remote_notifier.send_ready_to_pump(self.pump_state))

        # elif self.last_remote_cmd != self.PUMPING_VERIFIED and self.pump_state == self.PUMPING_VERIFIED:
        #     if self.remote_notifier.http.last_status_code == "Ping Fail":
        #         return
        #     self.last_remote_cmd = self.PUMPING_VERIFIED
        #     return self.handle_remote_response(self.PUMPING_VERIFIED,
        #                                        self.remote_notifier.pumping_confirmed(self.pump_state))

        return did_remote_display
    def check_idle_timer(self):
        if self.idle_timer.start_time is None or self.idle_timer.is_timed_out():
            # Don't flood the server with pumping status
            self.idle_timer.reset_timer(self.seconds_between_pumping_status_to_remote)
            try:
                # At the start of every idle event, check-in with remote in case it wants to change our state
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
                    self.debug.print_debug("notify_remote", "remote_cmd return-code " + str(
                        response.status_code) + " text " + get_response_text(response))

                remote_cmd = self.remote_notifier.http.remote_cmd  # remote_cmd is returned in server json.

                if remote_cmd == self.PUMPING_CANCELED:
                    # Canceled happens during pumping when pump verification times out on remote,
                    # and it attempts a stop us.
                    # This should only happen if there is something wrong with pump, and it's not pumping.
                    # NOTE: Both sides go into idle and this side will attempt to start pumping again
                    #       if the water level measurements trigger the pump.
                    # This is like a reset. There is no "permanent" stop pumping.
                    self.stop_pumping(self.PUMPING_CANCELED)
                    self.remote_notifier.send_pumping_canceled_ack(self.pump_state)
                elif remote_cmd == self.START_PUMPING:
                    # For what ever reason, the remote can turn on pump
                    # This has not been tested to see if this code will handle gracefully
                    self.pump_state = self.ENGAGE_PUMP
                    self.pump.pump_on()
                    self.remote_notifier.send_start_pumping_ack(self.pump_state)
            except Exception as e:
                self.remote_notifier.http.do_error_post("status handshake", str(format_exception(e)))
                self.display.display_error(["Error sending to remote. ", str(e)])
                self.debug.print_debug("notify_remote",
                                       "WARNING: Remote communication failed. Error: %s" % str(format_exception(e)))

