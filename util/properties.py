import json

from util.debug import Debug


class Properties:

    def __init__(self, debug: Debug):
        self.debug = debug
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
                "debug_sleep_time": 6,
                "display_interval": 5,
                "seconds_to_wait_for_pumping_verification": 30,
                "seconds_between_pumping_status_to_remote": 300,
                "component_id": "1"
            }
            # Can't write to the feather file system
            # with open('defaults.json', 'w', encoding='utf-8') as f:
            #     json.dump(self.defaults, f, ensure_ascii=False, indent=4)

        self.debug.print_debug("properties","read_defaults:\n seconds_to_wait_for_pumping_verification[%s],\n seconds_between_pumping_status_to_remote[%s],\n component_id[%s]" %
                               (self.defaults["seconds_to_wait_for_pumping_verification"], self.defaults["seconds_between_pumping_status_to_remote"], self.defaults["component_id"]))

        return self.defaults

