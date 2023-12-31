import os


class Debug:

    def __init__(self):
        self.debug = False
        self.local_set = False
        self.check_debug_enable()

    def check_debug_enable(self):
        if self.local_set:
            # Used to turn on/off debug via button
            return self.debug

        files_in_dir = os.listdir()
        a_debug = "debug" in files_in_dir
        if a_debug != self.debug:
            if self.debug:
                print("Debug OFF")
            else:
                print("Debug ON")

        self.debug = a_debug
        return a_debug

    def toggle_local_debug(self):
        self.local_set = not self.local_set
        if self.local_set:
            self.debug = True
        # When local_set is false, debug flag will be set by presence of the debug file.
        self.check_debug_enable()

    def debug_enabled(self):
        return self.debug

    def print_debug(self, caller, message):
        if self.debug:
            print("[" + '%-10s' % caller + "] "+ message)
