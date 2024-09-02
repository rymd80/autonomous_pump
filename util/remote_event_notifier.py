import gc
# import uuid
import json
from util.debug import Debug
from util.http_functions import HttpFunctions
from util.properties import Properties

class RemoteEventNotifier:
    def __init__(self, properties: Properties, debug: Debug):
        self.http = HttpFunctions(properties, debug)
        self.debug = debug

    def send_startup_notification(self, misc_status: json):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_startup_notification")
            return self.http.do_action_post("startup_notification", "startup", misc_status)

    def send_status_handshake(self, pump_state: str, misc_status: json):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","status_handshake " + str(pump_state))
            return self.http.do_action_post("status_handshake", pump_state, misc_status)

    def send_unknown_status(self, pump_state: str):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_unknown_status")
            return self.http.do_action_post("send_unknown_status", pump_state, "None")
        else:
            return None

    def send_pumping_canceled_ack(self, pump_state: str):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_pumping_canceled_ack")
            return self.http.do_action_post("pumping_canceled_ack", pump_state, "None")
        else:
            return None

    def send_start_pumping_ack(self, pump_state: str):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_start_pumping_ack")
            return self.http.do_action_post("start_pumping_ack", pump_state, "None")
        else:
            return None

    def send_stop_pumping_ack(self, pump_state: str):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_stop_pumping_ack")
            return self.http.do_action_post("stop_pumping_ack", pump_state, "None")
        else:
            return None

    def send_ready_to_pump(self, pump_state: str):
        # This is the point in the lifecyle where an event id is assigned.
        # We only go forward once we get the event id from the server
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","send_ready_to_pump")
            return self.http.do_action_post("ready_to_pump", pump_state, "None")
        else:
            return None

    def pump_event(self, pump_state: str, misc_status: json):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","pump_event")
            return self.http.do_action_post("pump_event", pump_state, misc_status)
        else:
            return None

    def pumping_confirmed(self, pump_state: str):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","pumping_confirmed")
            return self.http.do_action_post("pumping_confirmed", pump_state, "None")
        else:
            return None

    def pumping_timout(self, pump_state: str, misc_status: json):
        if self.http.last_http_status_success():
            self.debug.print_debug("remote","pumping_timeout")
            return self.http.do_action_post("pumping_timeout", pump_state, misc_status)
        else:
            return None

    def missed_pumping_verification(self, pump_state: str):
        self.debug.print_debug("remote","missed_pumping_verification")
        return self.http.do_action_post("missed_pumping_verification", pump_state, "None")

    def send_debug_logs_to_remote(self):
        #  self.debug.print_debug("remote","\n***** send_logs_to_remote. Number of log lines: "+str(len(self.debug.get_remote_lines()))+"\n")
        self.http.do_debug_log_post(self.debug.get_remote_lines())
        self.debug.clear_remote_lines()
