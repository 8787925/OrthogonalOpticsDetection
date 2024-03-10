#!/usr/bin/env python3
# NeoPixel library strandtest example
# Author: Tony DiCola (tony@tonydicola.com)
#
# Direct port of the Arduino NeoPixel library strandtest example.  Showcases
# various animations on a strip of NeoPixels.

import time
from picamera2 import Picamera2
import numpy as np 
from PIL import Image
from rpi_ws281x import *
import argparse
from matplotlib import pyplot as plt
from PiRAW2TIF_16bit import *

zero_DegreeLedList = [6, 7, 8, 9, 10, 11, 12, 13]

# LED strip configuration:
LED_COUNT      = 16     # Number of LED pixels.
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
#LED_PIN        = 10      # GPIO pin connected to the pixels (10 uses SPI /dev/spidev0.0).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating a signal (try 10)
LED_BRIGHTNESS = 255      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

picam2 = Picamera2()
capture_config = picam2.create_still_configuration()
picam2.configure(capture_config)
picam2.start()

picam2.set_controls({"ExposureTime": 1000000}) 
picam2.set_controls({"AnalogueGain": 1}) 

time.sleep(2)
ledFlashColor = Color(0, 255, 0)

# Define flash ring
def ledRingCommand(strip, color, ledHalf):
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

def captureAndToggle(strip, waitTime):
    greenAndTiff = []
    g0 = []
    g1 = []

    ledRingCommand(strip, ledFlashColor, 0)
    time.sleep(waitTime)
    rawImage1 = picam2.capture_array("raw")
    ledRingCommand(strip, ledFlashColor, 1)
    rawImage2 = picam2.capture_array("raw")

    greenAndTiff_off = imageGreenExtraction(rawImage1, 'rawImage_Off', True)
    greenAndTiff_on = imageGreenExtraction(rawImage2, 'rawImage_On', True)
    
    #Capture LED Off
    g0.append(greenAndTiff_off[0])
    g1.append(greenAndTiff_off[1])

    #Capture LEDOn
    g0.append(greenAndTiff_on[0])
    g1.append(greenAndTiff_on[1])

    deltaGreen0 = np.uint16(np.abs(np.int32(g0[1]) - np.int32(g0[0])))
    deltaGreen1 = np.uint16(np.abs(np.int32(g1[1]) - np.int32(g1[0])))

    ledRingCommand(strip, Color(0, 0, 0), 1)
    ledRingCommand(strip, Color(0, 0, 0), 0)

    #plot and save image plot
    fig = plt.imshow(deltaGreen0, cmap='hot', interpolation='none')
    plt.show()
    plt.savefig('./plotImage_g0.png')

    #plot and save image plot
    fig = plt.imshow(deltaGreen1, cmap='hot', interpolation='none')
    plt.show()
    plt.savefig('./plotImage_g1.png')
    
# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    try:
        while True:
            captureAndToggle(strip, 0.1)
            print('Picture and Flash Test')
            time.sleep(.1)


    except KeyboardInterrupt:
        if args.clear:
            ledRingCommand(strip, Color(0, 0, 0), 0)
            ledRingCommand(strip, Color(0, 0, 0), 1)
            print('Picture test exit')