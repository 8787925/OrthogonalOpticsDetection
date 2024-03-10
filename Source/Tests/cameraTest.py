#!/usr/bin/env python3
# NeoPixel library strandtest example
# Author: Tony DiCola (tony@tonydicola.com)
#
# Direct port of the Arduino NeoPixel library strandtest example.  Showcases
# various animations on a strip of NeoPixels.

import time
from picamera2 import Picamera2
import argparse
import numpy as np 
from PIL import Image

NUMBER_OF_CAMERAS = 2
picam_CameraList = []

for i in range(NUMBER_OF_CAMERAS):
    picam_CameraList.append(Picamera2(i))
    capture_config = picam_CameraList[i].create_still_configuration()
    picam_CameraList[i].start()

def captureAndAverage(cameraNumber = 0): 
    with picam_CameraList[cameraNumber].controls as ctrl:
        ctrl.AnalogueGain = 1.0
        ctrl.ExposureTime = 4000000
    time.sleep(2)

    imgs = 20  # Capture 20 images to average
    sumv = None

    for _ in range(imgs):
        if sumv is None:
            sumv = np.longdouble(picam_CameraList[cameraNumber].capture_array())
            img = Image.fromarray(np.uint8(sumv))
            img.save("OriginalImage_Camera_" + str(cameraNumber) + ".tiff")
        else:
            sumv += np.longdouble(picam_CameraList[cameraNumber].capture_array())

    img = Image.fromarray(np.uint8(sumv / imgs))
    img.save("AveragedImage_Camera_" + str(cameraNumber) + ".tiff")

# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to clear LEDs on exit')

    try:
        while True:
            captureAndAverage()
            print('Picture test')
            time.sleep(.1)


    except KeyboardInterrupt:
        if args.clear:
            print('Picture test exit')