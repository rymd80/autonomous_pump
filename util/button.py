import board
import digitalio
from digitalio import DigitalInOut, Direction, Pull

class Button:
    def __init__(self, button_pins: list[board.pin]):
        self.buttons = []

        for b in button_pins:
            a_button = digitalio.DigitalInOut(b)
            a_button.direction = digitalio.Direction.INPUT
            a_button.pull = Pull.UP
            self.buttons.append(a_button)

    def button_pushed(self):
        offset = 0
        # print("Start  button")
        for b in self.buttons:
            # print("Button "+str(b.value)+"  "+str(offset))
            offset += 1
            # print(str(b.value))
            if not b.value:
                print("button pressed")
                return True
        return False
