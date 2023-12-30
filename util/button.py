import board
import digitalio
from digitalio import DigitalInOut, Direction, Pull

class Button:
    def __init__(self, button_pins: list[board.pin]):
        self.buttons = []

        offset = 0
        for b in button_pins:
            a_button = digitalio.DigitalInOut(b)
            a_button.direction = digitalio.Direction.INPUT
            if(offset == 0):
                a_button.pull = Pull.UP
            else:
                a_button.pull = Pull.DOWN
            self.buttons.append(a_button)
            offset += 1

    def button_pushed(self):
        offset = 0
        # print("Start  button")
        # print("**** ")
        for b in self.buttons:
            # print("Button "+str(b.value)+"  "+str(offset))
            if offset == 0:
                if not b.value:
                    # print("button pressed "+str(offset))
                    return 0
            else:
                if b.value:
                    # print("button pressed"+str(offset))
                    return offset
            offset += 1
        return -1
