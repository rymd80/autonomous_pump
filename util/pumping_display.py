import board
import displayio
import terminalio
import time

# can try import bitmap_label below for alternative
from adafruit_display_text import label
import adafruit_displayio_sh1107

from util.water_level import WaterLevelReader

WIDTH = 128
HEIGHT = 64
BORDER = 2


class PumpingDisplay:
    def __init__(self):
        displayio.release_displays()

        # Use for I2C
        i2c = board.I2C()  # uses board.SCL and board.SDA
        # i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller
        display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)

        self.display = adafruit_displayio_sh1107.SH1107(display_bus, width=WIDTH, height=HEIGHT, rotation=0)

        # print("Done init PumpingDisplay")

    def initialize_display(self):
        # Make the display context,
        splash = displayio.Group()
        self.display.show(splash)

        color_bitmap = displayio.Bitmap(WIDTH, HEIGHT, 1)
        color_palette = displayio.Palette(1)
        color_palette[0] = 0xFFFFFF  # White

        bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
        splash.append(bg_sprite)

        # Draw a smaller inner rectangle in black
        inner_bitmap = displayio.Bitmap(WIDTH - BORDER * 2, HEIGHT - BORDER * 2, 1)
        inner_palette = displayio.Palette(1)
        inner_palette[0] = 0x000000  # Black
        inner_sprite = displayio.TileGrid(
            inner_bitmap, pixel_shader=inner_palette, x=BORDER, y=BORDER
        )
        splash.append(inner_sprite)
        return splash

    def display_status(self, address, water_level_state, program_start, pump_start,
                       water_level_readers: list[WaterLevelReader], http_status: str):
        main_group = self.initialize_display()

        text_area = label.Label(terminalio.FONT, text="Addr: " + address, color=0xFFFFFF, x=8, y=7)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="State: " + water_level_state, color=0xFFFFFF, x=8, y=17)
        main_group.append(text_area)

        water_level_status_display = (water_level_readers[1].print_water_state() + " - " +
                                      water_level_readers[0].print_water_state())
        text_area = label.Label(terminalio.FONT, text=water_level_status_display, color=0xFFFFFF, x=8, y=27)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text=http_status, color=0xFFFFFF, x=8, y=37)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="Start " + self.format_elapsed_ms(program_start),
                                color=0xFFFFFF, x=8, y=47)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="Pump " + self.format_elapsed_ms(pump_start),
                                color=0xFFFFFF, x=8, y=57)
        main_group.append(text_area)

    def display_error(self, error):
        main_group = self.initialize_display()

        text_area = label.Label(terminalio.FONT, text="***ERROR***", color=0xFFFFFF, x=8, y=7)
        main_group.append(text_area)

        y = 18
        x = 17
        count = 0
        offset = 0
        width = 18

        while count < 5 and offset < len(error):
            end = min([offset + width, len(error)])
            start = max([0, offset - 1])
            # print(f"offset {offset} end {end} {error[start:end]}")
            count += 1
            text_area = label.Label(terminalio.FONT, text=error[start:end], color=0xFFFFFF, x=x, y=y)
            main_group.append(text_area)
            y += 10
            offset += width + 1

    @staticmethod
    def format_elapsed_ms(start):
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
        # if (seconds > 0):
        #      out = out+str(seconds) + "s "
        return out
