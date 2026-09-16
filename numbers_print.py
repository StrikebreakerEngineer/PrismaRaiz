import os  # Added to get terminal dimensions
import sys
import time

import pyfiglet
from colorama import Fore, Style, init

init()

GREEN = Fore.RED
BRIGHT = Fore.LIGHTGREEN_EX
RESET = Style.RESET_ALL

# 1. Get the current width of your terminal window dynamically
try:
    TERMINAL_WIDTH = os.get_terminal_size().columns
except OSError:
    TERMINAL_WIDTH = 80  # Fallback if running in a non-standard environment

def slow_print(text, speed=0.002):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)

# Pass the width parameter to stop early wrapping
title = pyfiglet.figlet_format("=== NUMBERS ===", font="slant", width=TERMINAL_WIDTH)
slow_print(BRIGHT + title + RESET, 0.003)

time.sleep(1)

items = [
    "NPBT: 33/47, 69/204",
    "MPL: 29/41, 50/192",
    "PM@S: 19/31, 29/110",
    "ON-DATE: 8/12, 8/13",
    "B&C: 0/0, 0/5",
    "NM@S: 12/20, 22/79"
]

for item in items:
    # Added width here as well
    text = pyfiglet.figlet_format(item, font="standard", width=TERMINAL_WIDTH)
    slow_print(GREEN + text + RESET, 0.002)
    time.sleep(0.05)

title = pyfiglet.figlet_format("=== SOCIAL MEDIA ===", font="slant", width=TERMINAL_WIDTH)
slow_print(BRIGHT + title + RESET, 0.003)

items = [
    "Referrals: 24, 46",
    "NPBT: 5, 5",
    "Contacted: 95.7%"
]

for item in items:
    # Added width here as well
    text = pyfiglet.figlet_format(item, font="standard", width=TERMINAL_WIDTH)
    slow_print(GREEN + text + RESET, 0.002)
    time.sleep(0.05)
