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



class HttpFunctions:
    def __init__(self, properties: Properties, debug: Debug):
        self.properties = properties
        self.transaction_count = 0
        self.error_count = 0
        self.debug = debug
        self.requests = None
        self.pool = None
        self.debug.print_debug("init in HttpFunctions")
        self.ip_address = "None"
        self.event_id = "None"
        self.remote_url = self.properties.defaults["remote_url"]
        self.properties.read_defaults()
        self.last_status_code = "N"  # FYI - Used in display in code.py
        self.last_error = "N"
        self.need_to_connect = True
        self.last_action = None
        self.remote_cmd = None
        # dies early if ysou can't connect to Wi-Fi, sets ip_address if connected

        # If SocketPool wasn't successful, don't bother with hello
        # The code will keep trying to connect.
        self.get_pool()

    def success(self, response):
        if "status_code" in response:
            return 200 >= response["status_code"] < 300
        return False
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
                self.debug.print_debug("GetPool error: "+self.last_error+". Tries: " + str(tries))
                time.sleep(2)
        self.debug.print_debug("**ERROR*** Failed to get SocketPool")

    def connect(self):
        tries = 0
        self.ip_address = None
        while not self.ip_address and tries < 10:
            if self.pool is None:
                self.get_pool()

            if self.pool is None:
                self.debug.print_debug("No pool")
                self.ip_address = None
                self.need_to_connect = True
                self.last_status_code = "NO Pool"
                return

            self.debug.print_debug("\nConnecting to WiFi...")
            try:
                self.requests = adafruit_requests.Session(self.pool, ssl.create_default_context())
                wifi.radio.connect(self.properties.defaults["ssid"], self.properties.defaults["password"])
                self.ip_address = str(wifi.radio.ipv4_address)
                self.need_to_connect = False
                self.last_status_code = "Connected"
                self.last_error = "N"
                self.debug.print_debug("Connected! IP: " + self.ip_address)
                if not self.ping(self.properties.defaults["ping_ip"]):
                    return {
                        "status_code": 0,
                        "text": "Ping Failed"
                    }

                return
            except ConnectionError as e:
                tries += 1
                self.ip_address = None
                self.pool = None
                self.last_status_code = "NOT Connected"
                self.last_error = self.format_exception(e)
                self.need_to_connect = True
                self.debug.print_debug("Connection Error:"+ self.last_error)
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

    def do_hello(self):
        connect_response = self.check_connection()
        if not self.success(connect_response):
            print(connect_response["text"])
            self.debug.print_debug(connect_response["text"])
            return connect_response

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                response = self.requests.get(self.remote_url + "/component/hello")
                print(self.get_response_text(response))
                self.transaction_count += 1
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                self.debug.print_debug("hello error: " + self.last_error)
                self.last_status_code = "E"
                self.need_to_connect = True
                time.sleep(2)

        self.do_error_post("hello", self.last_error)  # This will send self.last_error to remote

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
        while tries < 3:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                self.debug.print_debug("post response code: " + str(response.status_code) + " text " + response)
                # return (response.status_code,response.text)
                self.last_status_code = str(response.status_code)
                self.transaction_count += 1
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                time.sleep(2)

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

        connect_response = self.check_connection()
        if not self.success(connect_response):
            self.debug.print_debug("Not success check_connection: code " + str(connect_response["status_code"])+ ", " + self.get_response_text(connect_response))
            return connect_response
        else:
            self.debug.print_debug("POST")

        headers = {'Content-Type': 'application/json'}
        post_body = {"action": api_action, "eventId": self.event_id, "pumpState": pump_state,
                     "componentId": str(self.properties.defaults["component_id"]),
                     "miscStatus": misc_status, "errorCount": str(self.error_count)}
        # Don't change the contents of post_body without coordinating with the server side
        self.debug.print_debug("post_body " + str(post_body))
        # eventid = str(uuid.uuid4())
        url = '{}/component/mission?mission=Pump1Mission'.format(self.remote_url)
        self.debug.print_debug("Post url: " + url)

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                if hasattr(response, "status_code"):
                    self.debug.print_debug("get return code " + str(response.status_code) + " text " + self.get_response_text(connect_response))
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
                    return {
                        "status_code": response.status_code,
                        "text": response.text
                    }
                else:
                    self.debug.print_debug("Post: Unknown response. type: " + type(response) + " - dir: ".join(dir(response)))
                    return {
                        "status_code": 0,
                        "text": "Post: Unknown response. type: " + type(response) + " - dir: ".join(dir(response))
                    }

            except Exception as e:
                tries += 1
                self.last_error = self.format_exception(e)
                self.last_status_code = "E"
                self.need_to_connect = True
                time.sleep(2)

        self.debug.print_debug("do_post error -- Error: " + self.last_error)
        self.do_error_post("post", self.last_error)
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 20:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't Post"
        }

    def do_get(self, api_verb: str):

        connect_response = self.check_connection()
        if not self.success(connect_response):
            return connect_response

        self.debug.print_debug("GET")

        url = '{}/component/mission?mission=Pump1Mission&component_id="{}"&event_id={}&verb={}}'.format(
            self.remote_url, self.properties.defaults["component_id"],self.event_id, api_verb)
        self.debug.print_debug("Get url: " + url)

        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                response = self.requests.get(url)
                if "status_code" in response:
                    self.debug.print_debug("get return code " + str(response.status_code) + " text " + response.text)
                    self.last_status_code = str(response.status_code)
                    self.transaction_count += 1
                    return {
                        "status_code": response.status_code,
                        "text": response.text
                    }

                self.debug.print_debug("Get: Unknown response. type: " + type(response) + " - dir: ".join(dir(response)))
                return {
                    "status_code": 0,
                    "text": "Get: Unknown response. type: " + type(response) + " - dir: ".join(dir(response))
                }

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
        if self.error_count > 20:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't Get"
        }

    # If connect to Wi-Fi successful but ping fails, don't attempt Post or Get
    def ping(self, ip):
        try:
            self.debug.print_debug("Ping address ip "+ip)
            ping_ip = ipaddress.IPv4Address(ip)
            tries = 0
            while tries < 5:
                ping = wifi.radio.ping(ip=ping_ip)

                if ping is not None:
                    return True
                else:
                    tries += 1

            self.last_error = "Ping Failed"
            self.last_status_code = "Ping Fail"
        except Exception as e:
            # To avoid over communicating, just return false, if we get exception
            # If the connect to Wi-Fi failed, then this will fail as well
            self.debug.print_debug("ping error "+str(e))

        return False

    def get_response_text(self, response):
        if isinstance(response, dict):
            if "text" in response:
                return response["text"]
        elif hasattr(response, "text"):
            return response.text

        return "Unknown type: "+type(response)+" - dir: ".join(dir(response))

    def format_exception(self, exc):
        return "".join(traceback.format_exception(None, exc, exc.__traceback__, limit=-1))
