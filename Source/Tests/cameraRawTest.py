#!/usr/bin/env python3
# Code meant to test and demonstrate the use of the 'raw' feature
# of the Raspberry Pi HQ camera and the PiCamera2 library

import time
from picamera2 import Picamera2
import argparse
import numpy as np 
from PIL import Image

NUMBER_OF_CAMERAS = 2
picam_List = []

for i in range(NUMBER_OF_CAMERAS):
    picam_List.append(Picamera2(camera_num=i))
    capture_config = picam_List[i].create_still_configuration(raw={})
    picam_List[i].configure(capture_config)
    picam_List[i].start()

def captureAndSaveRaw():
    for i in range(NUMBER_OF_CAMERAS): 
        rawImage = picam_List[i].capture_array("raw")
        #np.save('./raw12BitImage_daylight.npy', rawImage)
        img = Image.fromarray(rawImage)
        img.save('rawImageTest_Camera_' + str(i) + '.tiff')

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
            print('Picture test')
            time.sleep(.1)


    except KeyboardInterrupt:
        if args.clear:
            print('Picture test exit')