import time

class CommonFunctions:
    def __init__(self):
        pass

    @staticmethod
    def format_elapsed_ms(start):
        if start is None:
            return "None Yet"
        # Get time and components
        ms = time.monotonic() - start

        negative = ms < -1
        if negative:
            ms = ms * -1

        days = int(ms / 86400)
        ms = ms % 86400
        hours = int(ms / 3600)
        ms = ms % 3600
        minutes = int(ms / 60)
        seconds = int(ms % 60)

        # ms = ms % 60
        # seconds = int(ms)
        # print("seconds  "+str(seconds))
        out = ""
        if negative:
            out = out + "-"
        if days > 0:
            out = out + str(days) + "d "
        if hours > 0:
            out = out + str(hours) + "h "
        if minutes > 0:
            out = out + str(minutes) + "m "
        if minutes < 1:
                 out = out+str(seconds) + "s "
        return out