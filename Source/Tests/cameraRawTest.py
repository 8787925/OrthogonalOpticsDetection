#!/usr/bin/env python3
# Code meant to test and demonstrate the use of the 'raw' feature
# of the Raspberry Pi HQ camera and the PiCamera2 library

import time
from picamera2 import Picamera2
import argparse
import numpy as np 
from Libraries import PiRAW2TIF_16bit

NUMBER_OF_CAMERAS = 2
CAMERAS_ARE_MIRRORED = [False, True] #Camera 1 is mirrored to match camera 0
picam_List = []

#Initialize the cameras
for i in range(NUMBER_OF_CAMERAS):
    picam_List.append(Picamera2(camera_num=i))
    capture_config = picam_List[i].create_still_configuration(raw={})
    picam_List[i].configure(capture_config)
    picam_List[i].start()

# Capture from all available cameras in sequence, saving via the piRaw2Tiff library
def captureAndSaveRaw():
    for i in range(NUMBER_OF_CAMERAS): 
        rawImage = picam_List[i].capture_array("raw")
        PiRAW2TIF_16bit.imageGreenExtraction(rawImage, 'rawImage_Test_Camera_REF_internal' + str(i), True, CAMERAS_ARE_MIRRORED[i])

# Main program logic follows:
if __name__ == '__main__':
    # Process arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clear', action='store_true', help='clear the display on exit')
    args = parser.parse_args()

    print ('Press Ctrl-C to quit.')
    if not args.clear:
        print('Use "-c" argument to exit')

    try:
        while True:
            captureAndSaveRaw()
            print('Picture test complete, CTRL + C to Exit before next picture')
            time.sleep(.1)


    except KeyboardInterrupt:
        for i in range(NUMBER_OF_CAMERAS): 
            picam_List[i].stop()
        if args.clear:
            print('Picture test exit')