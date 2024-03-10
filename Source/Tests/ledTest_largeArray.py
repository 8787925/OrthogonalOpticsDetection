#!/usr/bin/env python3
# Code designed to test the circular implementation of the 
# LED array

import time
from rpi_ws281x import *
import argparse

zero_DegreeLedList = []

# LED strip configuration:
LED_COUNT_LIST     = [60, 48, 40, 32, 24, 16, 12]     # Number of LEDs in each successive ring
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating a signal (try 10)
LED_BRIGHTNESS = 255      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53
LED_COUNT = 0

# Get the total number of LEDs in the system by counting the ring content
LED_RING_ADDRESSES = []
for i in LED_COUNT_LIST:
    LED_RING_ADDRESSES.append([LED_COUNT, (LED_COUNT + i-1)]) 
    LED_COUNT = LED_COUNT + i
    

# Update the ring of LEDs
def ledRingCommand(strip, color, ringNumbers):
    localLED_Colors = []

    for _ in range(strip.numPixels()): 
        localLED_Colors.append(Color(0, 0, 0)) #assume un-lit 
    
    for z in ringNumbers:
        for i in range(LED_RING_ADDRESSES[z][0], LED_RING_ADDRESSES[z][1]+1):
            localLED_Colors[i] = color

    for i in range(strip.numPixels()): 
        strip.setPixelColor(i, localLED_Colors[i])

    strip.show()

# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    if LED_COUNT > 0:
        # Create WS2812 object
        strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        # Intialize the library (must be called once before other functions).
        strip.begin()
    else: 
        print('LED Configuration Problem, No LEDs Counted')

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    try:
        testColorList = [Color(50, 0, 0), Color(0, 50, 0), Color(0, 0, 50)]
        while True:

            #for each ring
            for colors in testColorList:
                for i in range(len(LED_COUNT_LIST)):
                    #command a color
                    ledRingCommand(strip, colors, [i])
                    time.sleep(150/1000)

            #turn off colors
            ledRingCommand(strip, Color(0, 0, 0), [0])
            time.sleep(1)

    except KeyboardInterrupt:
        ledRingCommand(strip, Color(0, 0, 0), [0])
        time.sleep(150/1000)

        if args.clear:
            print('Exit test')