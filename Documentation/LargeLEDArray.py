#!/usr/bin/env python3
# Code designed to test the circular implementation of the 
# LED array

import time
from rpi_ws281x import *
import argparse

# LED strip configuration:
LED_COUNT_LIST     = [60, 48, 40, 32, 24, 16, 12]     # Number of LEDs in each successive ring
LED_PIN        = 18      # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating a signal (try 10)
LED_BRIGHTNESS = 255      # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53

class LargeLEDArray: 
    def __init__(self): 
        # Get the total number of LEDs in the system by counting the ring content
        self.LED_RING_ADDRESSES = []
        self.LED_COUNT = 0
        for i in LED_COUNT_LIST:
            self.LED_RING_ADDRESSES.append([self.LED_COUNT, (self.LED_COUNT + i-1)]) 
            self.LED_COUNT = self.LED_COUNT + i

        if self.LED_COUNT > 0:
            # Create WS2812 object
            self.LEDstrip = Adafruit_NeoPixel(self.LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
            # Intialize the library (must be called once before other functions).
            self.LEDstrip.begin()
        else: 
            raise ValueError('No LEDs Accounted For')

    # Update the ring LED colors by overwrite
    def appendLEDRingCommand(self, color, ringNumbers): 
        for ring in ringNumbers:
            for i in range(self.LED_RING_ADDRESSES[ring][0], self.LED_RING_ADDRESSES[ring][1]+1):
                self.LEDstrip.setPixelColor(i,Color(color[0], color[1], color[2]))

        self.LEDstrip.show()

    # Display the color on the ring of LEDs
    def exclusiveLEDRingCommand(self, color, ringNumbers):
        for ledAddress in range(self.LEDstrip.numPixels()): 
            self.LEDstrip.setPixelColor(ledAddress, Color(0, 0, 0)) #assume un-lit 
        
        for ring in ringNumbers:
            for i in range(self.LED_RING_ADDRESSES[ring][0], self.LED_RING_ADDRESSES[ring][1]+1):
                self.LEDstrip.setPixelColor(i,Color(color[0], color[1], color[2]))

        self.LEDstrip.show()

    def appendLEDRingAddress_Append(self, color, ring, address): 
        for rings in ring: 
            for addresses in address: 
                self.ledDirectAddressAppend(color, self.LED_RING_ADDRESSES[rings] + addresses)

    def ledDirectAddress(self, color, address): 
        self.LEDstrip.setPixelColor(address, Color(color[0], color[1], color[2]))
        self.LEDstrip.show()

    def ledDirectAddressAppend(self, color, address): 
        self.LEDstrip.setPixelColor(address, Color(color[0], color[1], color[2]))

    def ledUpdate(self): 
        self.LEDstrip.show()

    def ledClearAll(self): 
        for i in range(self.LEDstrip.numPixels): 
            self.LEDstrip.setPixelColor(i, Color(0, 0, 0))

        self.LEDstrip.show()

    def setAllLEDs(self, color): 
        for i in range(self.LEDstrip.numPixels): 
            self.LEDstrip.setPixelColor(i, Color(color[0], color[1], color[2]))

        self.LEDstrip.show()

    def setLEDRingAddress(self, RingList, AddressLists, color):
        for Ring in RingList:
            for Address in AddressLists[Ring]:
                linearAddress = self.translateRingToLinearAddress(Ring, Address)
                self.LEDstrip.setPixelColor(linearAddress, Color(color[0], color[1], color[2]))

        self.LEDstrip.show()

    def translateRingToLinearAddress(self, Ring, Address): 
        return self.LED_RING_ADDRESSES[Ring][0] + Address

    def getLEDCount(self):
        return self.LED_COUNT