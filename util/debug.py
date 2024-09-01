import os


class Debug:

    def __init__(self):
        self.debug = False
        self.remote_set = False
        self.check_debug_enable()
        self.remote_lines = []

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

    def toggle_remote_debug(self,new_value:bool=None):
        if new_value is None:
            self.remote_set = not self.remote_set
        else:
            self.remote_set = new_value

    def debug_enabled(self):
        return self.debug

    def print_debug(self, caller, message):
        # if self.remote_set:
        debug_line = "[" + '%-10s' % caller + "] "+ message
        if self.debug:
            print(debug_line)

        if self.remote_set:
            self.remote_lines.append(debug_line)

    def clear_remote_lines(self):
        self.remote_lines = []

    def get_remote_lines(self):
        return self.remote_lines
