from time import time


class Timer:

    def __init__(self):
        self.start_time = None
        self.max_seconds = None

    def start_timer(self, seconds: int):
        self.max_seconds = seconds
        self.start_time = int(time())
        # print("start_time",str(self.start_time))

    def reset_timer(self, seconds: int):
        self.max_seconds = seconds
        self.start_time = int(time())

    def is_timing(self):
        return not (self.start_time is None)

    def cancel_timer(self):
        self.start_time = None

    def is_timed_out(self):
        if self.start_time is None or self.max_seconds is None:
            return False
        running_time = int(time()) - self.start_time
        return running_time > self.max_seconds

    def get_elapsed(self):
        if self.start_time is None:
            return "Not timing"
        return str(int(time()) - self.start_time)
