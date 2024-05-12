from CalibrationCard import ColorCalibration
import cv2
import numpy as np

CameraCalibrationFilePrefix = 'calibrationRawImage_Camera_'
CameraCalibrationFileExtension = '.tiff'
NumberOfCameras = 1

image = []
localCalibrationCard = ColorCalibration()
for cameraNumber in range(NumberOfCameras):
    image = cv2.imread('calibrationRawImage_Camera_' + str(cameraNumber) + CameraCalibrationFileExtension)
    localCalibrationCard.calibrateImage_byRef(image)

image = cv2.imread('downloadFromPi/detectionScript_Camera_0.tiff')
calibratedImage1 = localCalibrationCard.applyImageCalibration(image, displayResult=True)

