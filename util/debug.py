import os


class Debug:

    def __init__(self):
        self.debug = False
        self.check_debug_enable()

    def check_debug_enable(self):
        files_in_dir = os.listdir()
        a_debug = "debug" in files_in_dir
        if a_debug != self.debug:
            if self.debug:
                print("Debug OFF")
            else:
                print("Debug ON")

        self.debug = a_debug
        return a_debug

    def debug_enabled(self):
        return self.debug

    def print_debug(self, caller, message):
        if self.debug:
            print("[" + '%-10s' % caller + "] "+ message)
