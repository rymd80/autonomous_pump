import os
import gc
# import uuid
import ipaddress
import json
import ssl
import time
from traceback import format_exception

import adafruit_requests
import microcontroller
import socketpool
import wifi

from util.debug import Debug
from util.properties import Properties
from util.common import CommonFunctions
from util.simple_timer import Timer


class HttpFunctions:
    def __init__(self, properties: Properties, debug: Debug):
        self.properties = properties
        self.transaction_count = 0
        self.error_count = 0
        self.debug = debug
        self.requests = None
        self.pool = None
        self.debug.print_debug("-->http","init in HttpFunctions")
        self.ip_address = "None"
        self.event_id = "None"
        self.remote_url = os.getenv("REMOTE_URL")
        self.last_status_code = 200  # FYI - Used in display in code.py
        self.last_error = "N"
        self.need_to_connect = True
        self.last_action = None
        self.remote_cmd = None
        self.error_timer = Timer()

        # dies early if ysou can't connect to Wi-Fi, sets ip_address if connected

        # If SocketPool wasn't successful, don't bother with hello
        # The code will keep trying to connect.
        self.get_pool()

    def last_http_status_success(self):
        if (self.last_status_code >= 200 and self.last_status_code < 300) or self.error_timer.is_timed_out():
            if self.error_timer.is_timed_out():
                # Goal here is to keep trying to do http every 30 seconds after an error
                # A connect && pianf success cancels the error timer.
                self.error_timer.reset_timer(60)
            return True
        self.debug.print_debug("-->http", "last_http_status_success error: " + self.last_error)
        return False

    def success(self, response):
        if response is not None and "status_code" in response:
            if response["status_code"] >= 200 and response["status_code"] < 300:
                self.error_timer.cancel_timer()
                return True
            #return 200 >= response["status_code"] < 300

        self.error_timer.start_timer(60)
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
                self.last_error = str(format_exception(e))
                self.need_to_connect = True
                self.debug.print_debug("-->http","GetPool error: "+self.last_error+". Tries: " + str(tries))
                time.sleep(2)
        self.debug.print_debug("-->http","**ERROR*** Failed to get SocketPool")

    def connect(self):
        start = time.monotonic()
        tries = 0
        self.ip_address = None
        while not self.ip_address and tries < 10:
            if self.pool is None:
                self.get_pool()

            if self.pool is None:
                self.debug.print_debug("-->http","No pool")
                self.ip_address = None
                self.need_to_connect = True
                self.last_error = "No Pool"
                self.last_status_code = 0
                self.error_timer.start_timer(30)
                return

            self.debug.print_debug("-->http","Connecting to WiFi...")
            try:
                self.requests = adafruit_requests.Session(self.pool, ssl.create_default_context())
                wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
                self.ip_address = str(wifi.radio.ipv4_address)
                self.need_to_connect = False
                self.last_status_code = 200
                self.last_error = ""
                self.debug.print_debug("-->http","Connected! IP: " + self.ip_address)
                if not self.ping(os.getenv("PING_IP")):
                    self.need_to_connect = True
                    return {
                        "status_code": 0,
                        "text": "Ping Failed"
                    }

                self.debug.print_debug("-->http","connect elapsed " + CommonFunctions.format_elapsed_ms(start))
                self.error_timer.cancel_timer()
                return
            except ConnectionError as e:
                tries += 1
                self.ip_address = None
                self.pool = None
                self.last_error = "NOT Connected"
                self.last_status_code = 0
                self.last_error = str(format_exception(e))
                self.need_to_connect = True
                self.debug.print_debug("-->http","Connection Error:"+ self.last_error)
                time.sleep(2)
                gc.collect()
        self.error_timer.start_timer(60)
        self.debug.print_debug("-->http","**ERROR***  Didn't Connect!")
        self.debug.print_debug(self.last_error)
        self.do_error_post("connect", self.last_error)  # This will send self.last_error to remote
        return

    def process_response(self, response, debug_txt, tries, start):
        self.debug.print_debug("-->http",
                               debug_txt + str(response.status_code) + " text " +
                               self.get_response_text(response))
        self.debug.print_debug("-->http", "tries " + str(tries))

        self.debug.print_debug("-->http", "elapsed: "+CommonFunctions.format_elapsed_ms(start))

        self.last_status_code = response.status_code
        self.last_error = ""
        if response.status_code < 200 or response.status_code > 299:
            self.last_error = "Remote code " + response.status_code

    def check_connection(self):
        start = time.monotonic()
        try:
            if self.need_to_connect:
                self.connect()

            if self.pool is None:
                self.need_to_connect = True
                self.last_error = "No Pool"
                self.last_status_code = 0
                return {
                    "status_code": 0,
                    "text": "No Pool"
                }

            if self.ip_address is None:
                self.need_to_connect = True
                self.last_error = "Couldn't Connect"
                self.last_status_code = 0
                return {
                    "status_code": 0,
                    "text": "Couldn't Connect"
                }

            if not self.ping(os.getenv("PING_IP")):
                self.need_to_connect = True
                return {
                    "status_code": 0,
                    "text": "Ping Failed"
                }
            self.debug.print_debug("-->http","check_connection elapsed "+CommonFunctions.format_elapsed_ms(start))
            return {
                "status_code": 200,
                "text": "Connected"
            }
        except ConnectionError as e:
            self.last_error = str(format_exception(e))
            self.debug.print_debug("-->http",self.last_error)
            self.do_error_post("check_connection", self.last_error)  # This will send self.last_error to remote
            return {
                "status_code": 0,
                "text": self.last_error
            }

    def do_hello(self):
        start = time.monotonic()
        connect_response = self.check_connection()
        if not self.success(connect_response):
            self.debug.print_debug("-->http",connect_response["text"])
            return connect_response

        start_time = time.monotonic()
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                response = self.requests.get(self.remote_url + "/component/hello")
                self.process_response(response,"hello to remote response: ",tries, start_time)
                self.transaction_count += 1
                self.debug.print_debug("-->http","hello elapsed " + CommonFunctions.format_elapsed_ms(start))
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
            except Exception as e:
                tries += 1
                self.last_error = str(format_exception(e))
                self.debug.print_debug("-->http","hello error: " + self.last_error)
                self.last_status_code = 0
                self.need_to_connect = True
                time.sleep(2)

        self.do_error_post("hello", self.last_error)  # This will send self.last_error to remote
        self.debug.print_debug("http", "do_hello failed")

    def reset_id(self):
        if isinstance(self.event_id, int):
            self.do_error_post("reset_id", "event_id unexpectedly an int")
        else:
            self.event_id = "None"

    def do_error_post(self, action, error=None):
        if self.requests is None:
            return

        start = time.monotonic()

        if self.pool is None or self.ip_address is None:
            self.debug.print_debug("*http*","do_error_post no connection")
            return {
                "status_code": 0,
                "text": "Couldn't do_error_post"
            }

        # If we can't ping, there is no reason to attempt a POST
        if not self.ping_default():
            self.need_to_connect = True
            return {
                "status_code": 0,
                "text": "Ping Failed"
            }

        start_time = time.monotonic()

        headers = {'Content-Type': 'application/json'}
        post_body = {"type": "error", "eventId": self.event_id, "componentId": "1",
                     "action": action,
                     "errorCount": str(self.error_count), "lastError": error}
        url = '{}/component/error?mission=Pump1Mission'.format(self.remote_url)
        self.debug.print_debug("-->http","Post url: " + url)
        last_exception = None
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                self.process_response(response,"error_post response code: ",tries, start_time)
                self.transaction_count += 1
                self.debug.print_debug("-->http","do_error_post elapsed " + CommonFunctions.format_elapsed_ms(start))
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
            except Exception as e:
                tries += 1
                last_exception = e  # Can't be too long for display, may need to truncate
                self.last_status_code = 0
                time.sleep(2)

        self.last_error = str(last_exception)  # Can't be too long for display, may need to truncate
        formatted_exception = str(format_exception(last_exception))
        self.debug.print_debug("-->http","do_error_post Error -- Error:  " + " error " + formatted_exception)
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 200:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't send error"
        }

    def do_debug_log_post(self, log_lines):
        if self.requests is None or log_lines is None:
            return {
                "status_code": 0,
                "text": "Couldn't do_log_post"
            }
        if len(log_lines) <1:
            # No debug lines, not an error, return success
            self.debug.print_debug("-->http", "NO LOG LINES.")
            return {
                "status_code": 200,
                "text": ""
            }

        start = time.monotonic()

        if self.pool is None or self.ip_address is None:
            self.debug.print_debug("-->http", "No pool, ip address")
            return {
                "status_code": 0,
                "text": "Couldn't do_log_post"
            }

        # If we can't ping, there is no reason to attempt a POST
        if not self.ping_default():
            self.need_to_connect = True
            self.debug.print_debug("-->http", "Ping failed.")
            return {
                "status_code": 0,
                "text": "Ping Failed"
            }

        start_time = time.monotonic()

        headers = {'Content-Type': 'application/json'}

        post_body = []
        if isinstance(log_lines, list):
            # self.debug.print_debug("-->http", "making post body, "+str(len(log_lines))+" size.")
            for log_line in log_lines:
                post_body.append(log_line)
        else:
            # self.debug.print_debug("-->http", "making post body, single line.")
            post_body.append(log_lines)

        url = '{}/component/debug?mission=Pump1Mission'.format(self.remote_url)
        # self.debug.print_debug("-->http","Debug LOG Post url: " + url)
        # self.debug.print_debug("-->http","Debug LOG Post body: " + json.dumps(post_body))
        last_exception = None
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                self.process_response(response,"do_debug_log_post response code: ",tries, start_time)
                self.transaction_count += 1
                # self.debug.print_debug("-->http","do_debug_log_post elapsed " + CommonFunctions.format_elapsed_ms(start))
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
            except Exception as e:
                tries += 1
                last_exception = e  # Can't be too long for display, may need to truncate
                self.last_status_code = 0
                time.sleep(2)

        self.last_error = str(last_exception)  # Can't be too long for display, may need to truncate
        formatted_exception = str(format_exception(last_exception))
        self.debug.print_debug("-->http","do_error_post Error -- Error:  " + " error " + formatted_exception)
        self.need_to_connect = True
        self.error_count += 1
        if self.error_count > 200:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't send error"
        }

    def do_post(self, api_action: str, pump_state: str, misc_status):
        connect_response = self.check_connection()
        if not self.success(connect_response):
            self.debug.print_debug("-->http","Not success check_connection: code " + str(connect_response["status_code"])+ ", " + self.get_response_text(connect_response))
            return connect_response
        else:
            self.debug.print_debug("-->http","POST")


        headers = {'Content-Type': 'application/json'}
        post_body = {"action": api_action, "eventId": self.event_id, "pumpState": pump_state,
                     "componentId": str(self.properties.defaults["component_id"]),
                     "miscStatus": misc_status, "errorCount": str(self.error_count)}
        # Don't change the contents of post_body without coordinating with the server side
        self.debug.print_debug("-->http","post_body " + str(post_body))
        # eventid = str(uuid.uuid4())
        url = '{}/component/mission?mission=Pump1Mission'.format(self.remote_url)
        self.debug.print_debug("-->http","Post url: " + url)

        last_exception = None
        tries = 0
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 3:
            try:
                start_time = time.monotonic()
                response = self.requests.post(url=url, headers=headers, data=json.dumps(post_body))
                self.debug.print_debug("-->http","post elapsed " + CommonFunctions.format_elapsed_ms(start_time))
                if hasattr(response, "status_code"):
                    try:
                        res = json.loads(response.text)
                        if "eventId" in res:
                            self.event_id = res["eventId"]
                            self.debug.print_debug("-->http","Got remote eventId " + self.event_id)
                        if "cmd" in res:
                            self.remote_cmd = res["cmd"]
                        else:
                            self.remote_cmd = None
                    except Exception as e:
                        self.remote_cmd = None

                    self.process_response(response,"get return code ", tries, start_time)
                    self.transaction_count += 1
                    return {
                        "status_code": response.status_code,
                        "text": response.text
                    }
                else:
                    self.last_status_code = 0
                    self.debug.print_debug("-->http","Post: Unknown response. type: " + type(response) + " - dir: ".join(dir(response)))
                    self.last_error = "Post: Unknown response. type: " + type(response) + " - dir: ".join(dir(response))
                    return {
                        "status_code": 0,
                        "text": self.last_error
                    }

            except Exception as e:
                tries += 1
                last_exception = e  # Can't be too long for display, may need to truncate
                self.last_status_code = 0
                self.need_to_connect = True
                time.sleep(2)

        self.last_error = str(last_exception)  # Can't be too long for display, may need to truncate
        formatted_exception = str(format_exception(last_exception))
        self.debug.print_debug("-->http", "do_post Error -- Error: " + formatted_exception)
        self.do_error_post("post", formatted_exception)
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

        self.debug.print_debug("-->http","GET")

        url = '{}/component/mission?mission=Pump1Mission&component_id="{}"&event_id={}&verb={}}'.format(
            self.remote_url, self.properties.defaults["component_id"],self.event_id, api_verb)
        self.debug.print_debug("-->http","Get url: " + url)

        tries = 0
        last_exception = None
        # Wi-Fi can be a little flaky so try a few times before recording an error
        while tries < 5:
            try:
                start_time = time.monotonic()
                response = self.requests.get(url)
                self.debug.print_debug("-->http","get elapsed " + CommonFunctions.format_elapsed_ms(start_time))
                if "status_code" in response:
                    self.process_response(response,"get return code ", tries, start_time)
                    self.transaction_count += 1
                    return {
                        "status_code": response.status_code,
                        "text": response.text
                    }

                error = "Get: Unknown response. type: " + type(response) + " - dir: ".join(dir(response))
                self.debug.print_debug("-->http",error)
                self.last_error = error

                return {
                    "status_code": 0,
                    "text": "Get: Unknown response. type: " + type(response) + " - dir: ".join(dir(response))
                }

            except Exception as e:
                tries += 1
                last_exception = e  # Can't be too long for display, may need to truncate
                self.last_status_code = 0
                self.need_to_connect = True
                time.sleep(3)

        self.debug.print_debug("-->http", "do_get Error -- Error: " + str(format_exception(last_exception)))
        self.last_error = str(last_exception)  # Can't be too long for display, may need to truncate
        self.do_error_post("get")
        self.need_to_connect = True
        self.error_count += 1

        if self.error_count > 20:
            microcontroller.reset()  # When 200 error threshold is hit, then reboot the device.
        return {
            "status_code": 0,
            "text": "Couldn't Get"
        }

    # Ping host defined in settings.toml
    def ping_default(self):
        return self.ping(os.getenv("PING_IP"))

    # If connect to Wi-Fi successful but ping fails, don't attempt Post or Get
    def ping(self, ip):
        try:
            self.debug.print_debug("-->http","Ping address ip "+ip)
            ping_ip = ipaddress.IPv4Address(ip)
            tries = 0
            while tries < 5:
                ping = wifi.radio.ping(ip=ping_ip)

                if ping is not None:
                    self.last_status_code = 200
                    self.debug.print_debug("-->http", "Ping SUCCESS ")
                    self.error_timer.cancel_timer()
                    return True
                else:
                    tries += 1

            self.last_error = "Ping Error"
            self.last_status_code = 0
            self.debug.print_debug("-->http", "Ping FAIL ")
        except Exception as e:
            self.last_error = str(e)# Can't be too long for display, may need to truncate
            self.last_status_code = 0
            # To avoid over communicating, just return false, if we get exception
            # If the connect to Wi-Fi failed, then this will fail as well
            self.debug.print_debug("-->http","ping error "+str(format_exception(e)))

        self.error_timer.start_timer(30)
        return False

    def get_response_text(self, response):
        if isinstance(response, dict):
            if "text" in response:
                return response["text"]
        elif hasattr(response, "text"):
            return response.text

        return "Unknown type: "+type(response)+" - dir: ".join(dir(response))

