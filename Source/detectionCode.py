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
import argparse
from matplotlib import pyplot as plt
from Libraries import PiRAW2TIF_16bit
from OrthogonalOpticsDetection.Documentation.LargeLEDArray import *
from alignImages import align_images, align_fromHomography
import pickle
import os

NUMBER_OF_CAMERAS = 2
NUMBER_OF_FRAME_PAIRS = 4
CAMERAS_ARE_MIRRORED = [False, True] #Camera 1 is mirrored to match camera 0
picam_List = []

#Initialize the cameras
for i in range(NUMBER_OF_CAMERAS):
    picam_List.append(Picamera2(camera_num=i))
    capture_config = picam_List[i].create_still_configuration(raw={})
    picam_List[i].configure(capture_config)
    picam_List[i].start()

LEDArray = LargeLEDArray()

HOMOGRAPHY_CALIBRATION_NAME = 'wallCalibration_image.pickle'
HomographyMatrix = []
CALIBRATION_NEEDED = True

if os.path.exists(HOMOGRAPHY_CALIBRATION_NAME): 
    with open(HOMOGRAPHY_CALIBRATION_NAME, 'rb') as f:
        HomographyMatrix = pickle.load(f)
    CALIBRATION_NEEDED = False

#Gather the transformation array from the calibration file

#picam2.set_controls({"ExposureTime": 1000000}) 
#picam2.set_controls({"AnalogueGain": 1}) 

time.sleep(2)
ledFlashColor = [0, 50, 0]

def captureAndToggle(waitTime):
    greenAndTiff = []
    g0 = []
    g1 = []

    LEDArray.setAllLEDs(ledFlashColor)
    time.sleep(waitTime)

    rawImage = []
    for i in range(NUMBER_OF_CAMERAS):
        rawImage.append(picam_List[i].capture_array("raw"))

    #We captured the images - convert them into np16 sized arrays in BGR format (cv2 format)
    greenImageArray = []
    for i in range(NUMBER_OF_CAMERAS): 
        greenImageArray.append(PiRAW2TIF_16bit.imageGreenExtraction(rawImage[i], 'detectionScript_Camera_' + str(i), True, CAMERAS_ARE_MIRRORED[i]))

    #we now have two corrected images, we need to correct index 1 to match 2
    alignedCameraImage = align_fromHomography(greenImageArray[1][2], HomographyMatrix);
    
    #greenAndTiff_off = imageGreenExtraction(rawImage1, 'rawImage_Off', True)
    #greenAndTiff_on = imageGreenExtraction(rawImage2, 'rawImage_On', True)
    
    #Capture LED Off
    g0.append(greenAndTiff_off[0])
    g1.append(greenAndTiff_off[1])

    #Capture LEDOn
    g0.append(greenAndTiff_on[0])
    g1.append(greenAndTiff_on[1])

    deltaGreen0 = np.uint16(np.abs(np.int32(g0[1]) - np.int32(g0[0])))
    deltaGreen1 = np.uint16(np.abs(np.int32(g1[1]) - np.int32(g1[0])))

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

    try:
        if CALIBRATION_NEEDED:
            rawCalibrationImage = [] 
            raw16BitImages = []
            print('No calibration file found, generating optics calibrations')
            HomographyMatrix = []
            for z in range(NUMBER_OF_FRAME_PAIRS): 
                for i in range(NUMBER_OF_CAMERAS): 
                    rawCalibrationImage.append(picam_List[i].capture_array("raw"))
                    raw16BitImages.append(PiRAW2TIF_16bit.imageGreenExtraction(rawCalibrationImage[i], 'calibrationRawImage_Camera_' + str(i), True, CAMERAS_ARE_MIRRORED[i]))
                print('frame capture ' + str(z) + ' completed out of ' + str(NUMBER_OF_FRAME_PAIRS))
                #We've collected the images, now we need to generate the homography matrix
                HomographyMatrix.append(align_images(raw16BitImages[0][2], raw16BitImages[1][2]))
                print('frame comparison ' + str(z) + ' completed out of ' + str(NUMBER_OF_FRAME_PAIRS))
                
            print('Captures complete, generating optics calibration matrix')
            HomographyMatrix_Output = np.mean(HomographyMatrix, axis=0)

            with open(HOMOGRAPHY_CALIBRATION_NAME, 'wb') as f:
                pickle.dump(HomographyMatrix_Output, f)

            HomographyMatrix = HomographyMatrix_Output

        while True:
            captureAndToggle(0.1)
            print('Picture and Flash Test')
            time.sleep(.1)


    except KeyboardInterrupt:
        if args.clear:
            LEDArray.ledClearAll()
            print('Picture test exit')