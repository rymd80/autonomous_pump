import board
import displayio
import terminalio

from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
import adafruit_displayio_sh1107

from util.common import CommonFunctions
from util.debug import Debug
from util.properties import Properties
from util.remote_event_notifier import RemoteEventNotifier

from util.water_level import WaterLevelReader

BORDER = 2

# ***********************************************************************************************
# PumpingDisplay
# ***********************************************************************************************
class PumpingDisplay:
    def __init__(self, debug: Debug, properties: Properties):
        self.debug = debug
        self.properties = properties

        self.display = board.DISPLAY

    def initialize_display(self, border:bool):
        # Start the display context,
        main_group = displayio.Group()

        if not border:
            color_bitmap = displayio.Bitmap(self.display.width, self.display.height, 1)
            color_palette = displayio.Palette(1)
            color_palette[0] = 0x000000  # 0xFFFFFF  # White

            bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
            main_group.append(bg_sprite)
            return main_group

        color_bitmap = displayio.Bitmap(self.display.width, self.display.height, 1)
        color_palette = displayio.Palette(1)
        color_palette[0] = 0xFFFFFF  # White

        bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
        main_group.append(bg_sprite)

        # Draw a smaller inner rectangle in black
        inner_bitmap = displayio.Bitmap(self.display.width - BORDER * 2, self.display.height - BORDER * 2, 1)
        inner_palette = displayio.Palette(1)
        inner_palette[0] = 0x000000  # Black
        inner_sprite = displayio.TileGrid(
             inner_bitmap, pixel_shader=inner_palette, x=BORDER, y=BORDER
         )
        main_group.append(inner_sprite)
        return main_group

    def display_status(self, address, pump_state:str, remote_notifier: RemoteEventNotifier, program_start, pump_start,
                       water_level_readers: list[WaterLevelReader]):

        main_group = self.initialize_display(False)

        start_elapsed = CommonFunctions.format_elapsed_ms(program_start)
        pump_elapsed = CommonFunctions.format_elapsed_ms(pump_start)

        if remote_notifier.http.last_http_status_success():
            http = "200"
        else:
            http = remote_notifier.http.last_error

        http_status = "#%sC:%sE#:%d" % (
            "{:,}".format(remote_notifier.http.transaction_count), http,remote_notifier.http.error_count)

        self.debug.print_debug("display","pump_state " + pump_state+
                               " levels " + water_level_readers[1].print_water_state() + " - " +
                               water_level_readers[0].print_water_state())
        self.debug.print_debug("display","http_status " + http_status)
        self.debug.print_debug("display","start_elapsed " + start_elapsed)
        self.debug.print_debug("display","pump_elapsed " + pump_elapsed)

        if address is None:
            address = "None"

        text_area = label.Label(terminalio.FONT, scale=2, text="Addr: " + address, color=0xfffb96, x=8, y=11) # 0xfeda75
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text="State: " + pump_state, color=0xfa7e1e, x=8, y=34)
        main_group.append(text_area)

        water_level_status_display = (water_level_readers[1].print_water_state() + " - " +
                                      water_level_readers[0].print_water_state())
        text_area = label.Label(terminalio.FONT, scale=2, text=water_level_status_display, color=0x74d600, x=8, y=57)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text=http_status, color=0x8b9dc3, x=8, y=80)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text="Start: " + start_elapsed,
                                color=0xFFFFFF, x=8, y=104)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text="Pump: " + pump_elapsed,
                                color=0xFFFFFF, x=8, y=126)
        main_group.append(text_area)

        self.display.root_group = main_group

    def display_remote(self, action):
        self.debug.print_debug("display","**** display_remote: action " + action)

        main_group = self.initialize_display(True)

        text_area = label.Label(terminalio.FONT, scale=3, text="Notify", color=0xfa7e1e, x=8, y=20)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text=action, color=0xfffb96, x=8, y=50)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, scale=2, text="Please wait", color=0x74d600, x=8, y=74)
        main_group.append(text_area)

        self.display.root_group = main_group

    def display_error(self, error):
        self.debug.print_debug("display","**** display_error: " + error)

        main_group = self.initialize_display(True)

        text_area = label.Label(terminalio.FONT, scale=2, text="***ERROR***", color=0xFFFFFF, x=8, y=8)
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
            text_area = label.Label(terminalio.FONT, scale=2, text=error[start:end], color=0xFFFFFF, x=x, y=y)
            main_group.append(text_area)
            y += 10
            offset += width + 1

        self.display.root_group = main_group

# ***********************************************************************************************
# PumpingDisplay_i2c
# ***********************************************************************************************
class PumpingDisplay_i2c:
    def __init__(self, debug: Debug, properties: Properties):
        self.display = board.DISPLAY
        self.debug = debug
        self.properties = properties

        self.width = 128
        self.height = 64
        # Use for I2C
        i2c = board.I2C()  # uses board.SCL and board.SDA
        # i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller
        display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)

        self.display = adafruit_displayio_sh1107.SH1107(display_bus, width=self.width, height=self.height, rotation=0)

    def initialize_display(self):
        try:
            displayio.release_displays()
        except Exception as e:
            pass

        # Start the display context,
        main_group = displayio.Group()

        color_bitmap = displayio.Bitmap(self.display.width, self.display.height, 1)
        color_palette = displayio.Palette(1)
        color_palette[0] = 0xFFFFFF  # White

        bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
        main_group.append(bg_sprite)

        # Draw a smaller inner rectangle in black
        inner_bitmap = displayio.Bitmap(self.display.width - BORDER * 2, self.display.height - BORDER * 2, 1)
        inner_palette = displayio.Palette(1)
        inner_palette[0] = 0x000000  # Black
        inner_sprite = displayio.TileGrid(
            inner_bitmap, pixel_shader=inner_palette, x=BORDER, y=BORDER
        )
        main_group.append(inner_sprite)

        return main_group

    def display_status(self, address, pump_state:str, remote_notifier: RemoteEventNotifier, program_start, pump_start,
                       water_level_readers: list[WaterLevelReader]):

        main_group = self.initialize_display()

        start_elapsed = CommonFunctions.format_elapsed_ms(program_start)
        pump_elapsed = CommonFunctions.format_elapsed_ms(pump_start)

        if remote_notifier.http.last_http_status_success():
            http = "200"
        else:
            http = remote_notifier.http.last_error

        http_status = "#%sC:%sE#:%d" % (
            "{:,}".format(remote_notifier.http.transaction_count), http,remote_notifier.http.error_count)

        self.debug.print_debug("display","pump_state " + pump_state+
                               " levels " + water_level_readers[1].print_water_state() + " - " +
                               water_level_readers[0].print_water_state())
        self.debug.print_debug("display","http_status " + http_status)
        self.debug.print_debug("display","start_elapsed " + start_elapsed)
        self.debug.print_debug("display","pump_elapsed " + pump_elapsed)

        if address is None:
            address = "None"

        text_area = label.Label(terminalio.FONT, text="Addr: " + address, color=0xFFFFFF, x=8, y=7)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="State: " + pump_state, color=0xFFFFFF, x=8, y=17)
        main_group.append(text_area)

        water_level_status_display = (water_level_readers[1].print_water_state() + " - " +
                                      water_level_readers[0].print_water_state())
        text_area = label.Label(terminalio.FONT, text=water_level_status_display, color=0xFFFFFF, x=8, y=27)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text=http_status, color=0xFFFFFF, x=8, y=37)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="Start: " + start_elapsed,
                                color=0xFFFFFF, x=8, y=47)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="Pump: " + pump_elapsed,
                                color=0xFFFFFF, x=8, y=57)
        main_group.append(text_area)

        self.display.show(main_group)

    def display_remote(self, action):
        self.debug.print_debug("display","**** display_remote: action " + action)

        main_group = self.initialize_display()

        text_area = label.Label(terminalio.FONT, text="Notify", color=0xFFFFFF, x=8, y=7)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text=action, color=0xFFFFFF, x=8, y=20)
        main_group.append(text_area)

        text_area = label.Label(terminalio.FONT, text="Please wait", color=0xFFFFFF, x=8, y=40)
        main_group.append(text_area)

        self.display.show(main_group)
    def display_error(self, error):
        self.debug.print_debug("display","**** display_error: " + error)

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

        self.display.show(main_group)

