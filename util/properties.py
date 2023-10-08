import json

from util.debug import Debug


class Properties:

    def __init__(self, debug: Debug):
        self.debug = debug
        self.remote_url = None
        self.defaults = {}
        self.read_defaults()

    def read_defaults(self):
        try:
            # Reads json file and creates if json file doesn't exist
            with open('secrets.json', ) as f:
                self.defaults = json.load(f)
        except Exception as e:
            # print ("Let's just ignore all exceptions, like this one: %s" % str(e))
            print("WARNING: Didn't read secrets.json, using default values. Error: %s" % str(e))
            self.defaults = {
                "component_id": "1",
                "ssid": "Fios-4LC2c",
                "password": "password",
                "ping_ip": "192.168.1.200",
                "remote_url": "http://192.168.1.200:/component/pump1",
                "water_levels": {"Bottom": 1100, "Middle": 900, "Top": 1100}
            }
            # Can't write to the feather file system
            # with open('defaults.json', 'w', encoding='utf-8') as f:
            #     json.dump(self.defaults, f, ensure_ascii=False, indent=4)

        self.remote_url = self.defaults["remote_url"]
        self.debug.print_debug("read_defaults: ssid[%s], password[%s], remote_url[%s]" %
                               (self.defaults["ssid"], self.defaults["password"], self.defaults["remote_url"]))

        return self.defaults

