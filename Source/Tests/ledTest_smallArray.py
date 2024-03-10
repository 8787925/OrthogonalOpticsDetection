#!/usr/bin/env python3

import time
from rpi_ws281x import *
import argparse

zero_DegreeLedList = [6, 7, 8, 9, 10, 11, 12, 13]

# LED strip configuration:
LED_COUNT      = 60     # Number of LED pixels.
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
#LED_PIN        = 10      # GPIO pin connected to the pixels (10 uses SPI /dev/spidev0.0).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating a signal (try 10)
LED_BRIGHTNESS = 255      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

# Define functions which animate LEDs in various ways.
def ledRingCommand(strip, color, ledHalf, wait_ms=50):
    for i in range(strip.numPixels()):
        if (i in zero_DegreeLedList):
            if (ledHalf):
                strip.setPixelColor(i, Color(0, 0, 0))
            else:
                strip.setPixelColor(i, color)
        else: 
            if (ledHalf):
                strip.setPixelColor(i, color)
            else:
                strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    # Create NeoPixel object with appropriate configuration.
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    # Intialize the library (must be called once before other functions).
    strip.begin()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    try:
        while True:
            ledRingCommand(strip, Color(0, 255, 0), 1)
            time.sleep(1)
            ledRingCommand(strip, Color(0, 0, 0), 0)
            print('Flash test')
            time.sleep(.1)

    except KeyboardInterrupt:
        if args.clear:
            print('Exit test')