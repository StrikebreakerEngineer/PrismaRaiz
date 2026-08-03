import time
import sys
import pyfiglet
from colorama import Fore, Style, init

init()

GREEN = Fore.RED
BRIGHT = Fore.LIGHTGREEN_EX
RESET = Style.RESET_ALL

def slow_print(text, speed=0.002):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)

# Big special title
title = pyfiglet.figlet_format("NUMBERS", font="slant")

slow_print(BRIGHT + title + RESET, 0.003)

time.sleep(1)

# Smaller entries
items = [
    "NPBT:",
    "MPL:",
    "PM@S:",
    "ON-DATE:",
    "B&C:",
    "NM@S:"
]

for item in items:
    text = pyfiglet.figlet_format(item, font="standard")
    slow_print(GREEN + text + RESET, 0.002)
    time.sleep(0.4)