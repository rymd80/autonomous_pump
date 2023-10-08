import gc
# import uuid
import ipaddress
import json
import ssl
import time
import traceback

import adafruit_requests
import microcontroller
import socketpool
import wifi

from util.debug import Debug
from util.properties import Properties


class RemoteEventNotifier:
    def __init__(self, properties: Properties, debug: Debug):
        self.properties = properties
        self.transaction_count = 0
        self.error_count = 0
        self.debug = debug
        self.requests = None
        self.debug.print_debug("init in RemoteEventNotifier")
        self.ip_address = "None"
        self.event_id = "None"
        self.remote_url = self.properties.defaults["remote_url"]
        self.properties.read_defaults()
        self.last_status_code = "N"  # FYI - Used in display in code.py
        self.last_error = "N"
        self.need_to_connect = True
        self.last_action = None
        self.remote_cmd = None
        # dies early if you can't connect to Wi-Fi, sets ip_address if connected

        # If SocketPool wasn't successful, don't bother with hello
        # The code will keep trying to connect.
        self.get_pool()

    def get_pool(self):
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 10:
            try:
                self.pool = socketpool.SocketPool(wifi.radio)
                return
            except Exception as e:
                self.pool = None
                tries += 1
                self.last_error = self.format_exception(e)
                self.need_to_connect = True
                print("GetPool error:", self.last_error, ". Tries: " + str(tries))
                time.sleep(2)
        self.debug.print_debug("**ERROR*** Failed to get SocketPool")

    def connect(self):
        if self.pool is None:
            self.get_pool()

        if self.pool is None:
            self.ip_address = None
            self.need_to_connect = True
            self.last_status_code = "NO Pool"
            return

        tries = 0
        self.ip_address = None
        while not self.ip_address and tries < 10:
            self.debug.print_debug("\nConnecting to WiFi...")
            try:
                self.requests = adafruit_requests.Session(self.pool, ssl.create_default_context())
                wifi.radio.connect(self.properties.defaults["ssid"], self.properties.defaults["password"])
                self.ip_address = str(wifi.radio.ipv4_address)
                self.need_to_connect = False
                self.last_status_code = "Connected"
                self.last_error = "N"
                self.debug.print_debug("Connected! IP: " + self.ip_address)
                return
            except ConnectionError as e:
                tries += 1
                self.ip_address = None
                self.pool = None
                self.last_status_code = "NOT Connected"
                self.last_error = self.format_exception(e)
                self.need_to_connect = True
                self.debug.print_debug("Connection Error:"+ str(e))
                time.sleep(2)
                gc.collect()
        self.debug.print_debug("**ERROR***  Didn't Connect!")
        self.debug.print_debug(self.last_error)
        self.do_error_post("connect", self.last_error)  # This will send self.last_error to remote
        return

    def check_connection(self):
        try:
            if self.need_to_connect:
                self.connect()

            if self.pool is None:
                self.need_to_connect = True
                self.last_status_code = "No Pool"
                return {
                    "status_code": 0,
                    "text": "No Pool"
                }
            if self.ip_address is None:
                self.need_to_connect = True
                self.last_status_code = "Couldn't Connect"
                return {
                    "status_code": 0,
                    "text": "Couldn't Connect"
                }

            if not self.ping(self.properties.defaults["ping_ip"]):
                return {
                    "status_code": 0,
                    "text": "Ping Failed"
                }
            return {
                "status_code": 200,
                "text": "Connected"
            }
        except ConnectionError as e:
            self.last_error = self.format_exception(e)
            self.debug.print_debug(self.last_error)
            self.do_error_post("check_connection", self.last_error)  # This will send self.last_error to remote
            return {
                "status_code": 0,
                "text": self.last_error
            }

        # try:
        #     ssid = self.properties.defaults["ssid"]
        #     self.debug.print_debug(f"Connecting to {ssid}")
        #     wifi.radio.connect(self.properties.defaults["ssid"], self.properties.defaults["password"])
        #     self.ip_address = str(wifi.radio.ipv4_address)
        # except Exception as e:
        #     print ("WARNING: Didn't connect to Wi-Fi. Error: %s" % str(e) )
        #     self.ip_address = "NOT FOUND"
        #     raise e
        # try:
        #     pool = socketpool.SocketPool(wifi.radio)
        #     for network in wifi.radio.start_scanning_():
        #         self.debug.print_debug \
        #             ("\t%s\t\tRSSI: %d\tChannel: %d" % (network.ssid, network.rssi, network.channel))
        #     wifi.radio.stop_scanning_networks()
        #     self.session =adafruit_requests.Session(pool, ssl.create_default_context())
        #     return self.session
        # except Exception as e:
        #     print ("WARNING: Didn't create session. Error: %s" % str(e) )
        #     raise e

    def do_hello(self):
        connect_response = self.check_connection()
        if connect_response["status_code"] != 200:
            print(connect_response["text"])
            self.debug.print_debug(connect_response["text"])
            return connect_response

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                response = self.requests.get(self.remote_url + "/component/hello")
                print(response.text)
                self.transaction_count += 1
                return
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                self.last_status_code = "E"
                self.need_to_connect = True
                time.sleep(3)

        self.do_error_post("hello", self.last_error)  # This will send self.last_error to remote

    def success(self, response):
        if isinstance(response.status_code, int):
            return 200 <= response.status_code < 300
        else:
            self.do_error_post("checking success", "status code not int. status code: " + str(response.status_code))
            return False

    def reset_id(self):
        if isinstance(self.event_id, int):
            self.do_error_post("reset_id", "event_id unexpectedly an int")
        else:
            self.event_id = "None"

    def do_error_post(self, action, error=None):
        if self.requests is None:
            return

        if self.pool is None or self.ip_address is None:
            self.debug.print_debug("do_error_post no connection")
            return {
                "status_code": 0,
                "text": "Couldn't do_error_post"
            }

        headers = {'Content-Type': 'application/json'}
        post_body = {"type": "error", "eventId": self.event_id, "componentId": "1",
                     "action": action,
                     "errorCount": str(self.error_count), "lastError": error}
        url = '{}/component/error?mission=Pump1Mission'.format(self.remote_url)
        self.debug.print_debug("Post url: " + url)
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                self.debug.print_debug("post response code: " + str(response.status_code) + " text " + response.text)
                # return (response.status_code,response.text)
                self.last_status_code = str(response.status_code)
                self.transaction_count += 1
                return response
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                time.sleep(3)

        self.debug.print_debug("do_error_post exception  " + " error " + self.last_error)
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 200:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't send error"
        }

    def do_post(self, api_action: str, pump_state: str, misc_status):
        # when the program starts, the water level can be in any kind of state,
        # this logic tries to synchronize some of the unknowns

        self.debug.print_debug("POST")

        connect_response = self.check_connection()
        if connect_response["status_code"] != 200:
            return connect_response

        headers = {'Content-Type': 'application/json'}
        post_body = {"action": api_action, "eventId": self.event_id, "pumpState": pump_state,
                     "componentId": str(self.properties.defaults["component_id"]),
                     "miscStatus": misc_status, "errorCount": str(self.error_count), "lastError": self.last_error}
        # Don't change the contents of post_body without coordinating with the server side
        self.debug.print_debug("post_body " + str(post_body))
        # eventid = str(uuid.uuid4())
        url = '{}/component/mission?mission=Pump1Mission'.format(self.remote_url)
        self.debug.print_debug("Post url: " + url)

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                try:
                    res = json.loads(response.text)
                    if "eventId" in res:
                        self.event_id = res["eventId"]
                        self.debug.print_debug("Got remote eventId " + self.event_id)
                    if "cmd" in res:
                        self.remote_cmd = res["cmd"]
                    else:
                        self.remote_cmd = None
                except Exception as e:
                    self.remote_cmd = None

                self.last_status_code = str(response.status_code)
                self.transaction_count += 1
                return response
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                time.sleep(3)

        self.debug.print_debug("do_post error -- Error: " + self.last_error)
        self.do_error_post("post", self.last_error)
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 200:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't Post"
        }

    def do_get(self, api_verb: str):
        self.debug.print_debug("GET")

        connect_response = self.check_connection()
        if connect_response["status_code"] != 200:
            return connect_response

        url = '{}/component/mission?mission=Pump1Mission&component_id="{}"&event_id={}&verb={}}'.format(
            self.remote_url, self.properties.defaults["component_id"],self.event_id, api_verb)
        self.debug.print_debug("Get url: " + url)

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                response = self.requests.get(url)
                self.debug.print_debug("get return code " + str(response.status_code) + " text " + response.text)
                self.last_status_code = str(response.status_code)
                self.transaction_count += 1
                return response
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                self.last_status_code = "E"
                self.need_to_connect = True
                time.sleep(3)

        self.debug.print_debug("do_get Error -- Error: " + self.last_error)
        self.do_error_post("get")
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 200:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't Get"
        }

    def send_status_handshake(self, pump_state: str, misc_status: json):
        self.debug.print_debug("status_handshake " + str(pump_state))
        return self.do_post("status_handshake", pump_state, misc_status)

    def send_unknown_status(self, pump_state: str):
        self.debug.print_debug("send_unknown_status")
        return self.do_post("send_unknown_status", pump_state, "None")

    def send_pumping_canceled_ack(self, pump_state: str):
        self.debug.print_debug("send_pumping_canceled_ack")
        return self.do_post("pumping_canceled_ack", pump_state, "None")

    def send_start_pumping_ack(self, pump_state: str):
        self.debug.print_debug("send_start_pumping_ack")
        return self.do_post("start_pumping_ack", pump_state, "None")

    def send_stop_pumping_ack(self, pump_state: str):
        self.debug.print_debug("send_stop_pumping_ack")
        return self.do_post("stop_pumping_ack", pump_state, "None")

    def send_ready_to_pump(self, pump_state: str):
        # This is the point in the lifecyle where an event id is assigned.
        # We only go forward once we get the event id from the server
        self.debug.print_debug("send_ready_to_pump")
        # TODO - at some poing (when doing another deployment, change read_ to ready_
        return self.do_post("ready_to_pump", pump_state, "None")

    def start_pumping(self, pump_state: str):
        self.debug.print_debug("start_pumping")
        return self.do_post("start_pumping", pump_state, "None")

    def pumping_confirmed(self, pump_state: str):
        self.debug.print_debug("pumping_confirmed")
        return self.do_post("pumping_confirmed", pump_state, "None")

    def pumping_finished(self, pump_state: str):
        self.debug.print_debug("pumping_finished")
        return self.do_post("pumping_finished", pump_state, "None")

    def missed_pumping_verification(self, pump_state: str):
        self.debug.print_debug("missed_pumping_verification")
        return self.do_post("missed_pumping_verification", pump_state, "None")

    def ping(self, ip):
        ping_ip = ipaddress.IPv4Address(ip)
        tries = 0
        while tries < 5:
            ping = wifi.radio.ping(ip=ping_ip)
            if ping is not None:
                return True
            else:
                tries += 1

        self.last_error = "Ping Failed"
        self.last_status_code = "Ping"

        return False

    def format_exception(self, exc):
        # types.FrameType
        return "".join(traceback.format_exception(None, exc, exc.__traceback__, limit=-1))
