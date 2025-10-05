import asyncio
import websockets
import json
import numpy as np
import json
from picamera2 import Picamera2, Preview
import time
import cv2
from Libraries import PiRAW2TIF_16bit
import io
from alignImages import *
import os
from matplotlib import pyplot as plt

#this code is meant to be ran on the computer who is running the 'Trigger' camera
#
#First it sends a 'startup' command, to the 'Sink' computer, and awaits signal that the camera is ready
#
#This code is technically the 'client' code of a websocket arrangement

# Name of master computer
WEBSOCKET_MASTER = 'camera0bee.lan'
WEBSOCKET_SLAVE = 'beemonitor.lan'
WEBSOCKET_PORT = 18873
FRAGMENT_SIZE = 1 #indicies
NUMBER_OF_FRAMES = 15
NUMBER_OF_CALIBRATION_FRAMES = 15
FIRST_CALIBRATION_FRAME = 7
HOMOGRAPHY_CALIBRATION_NAME = 'wallCalibration_image_1080.pickle'
HomographyMatrix = []
CALIBRATION_NEEDED = True
calibrationFramesAccumulated = 0
rawCalibrationImageSet_1 = []
rawCalibrationImageSet_2 = []
NUMBER_OF_CAMERAS = 2
CAMERA_H_RESOLUTION = 1920
CAMERA_V_RESOLUTION = 1080

#sensitivity accumulation 
sensitivityMapNeeded = True
SENSITIVITY_MAP_NAME = 'sensitivityMap_1080.pickle'
Sensitivity_Map = []
Sensitivity_Accumulation = []
Sensitivity_Frames_Accumulated = 0
NUMBER_OF_SENSITIVITY_FRAMES = 15
FIRST_SENSITIVITY_FRAME = FIRST_CALIBRATION_FRAME
DIFFERENCE_GAIN = 5
DIFFERENCE_FLOOR = 100

if os.path.exists(SENSITIVITY_MAP_NAME): 
    with open(SENSITIVITY_MAP_NAME, 'rb') as f:
        Sensitivity_Map = pickle.load(f)
    sensitivityMapNeeded = False

if os.path.exists(HOMOGRAPHY_CALIBRATION_NAME): 
    with open(HOMOGRAPHY_CALIBRATION_NAME, 'rb') as f:
        HomographyMatrix = pickle.load(f)
    CALIBRATION_NEEDED = False

localCamera = Picamera2()
camera_configa = localCamera.create_still_configuration(
        main={"size":(CAMERA_H_RESOLUTION,CAMERA_V_RESOLUTION)},
        queue = False)
localCamera.configure(camera_configa)
localCamera.set_controls({"ExposureTime": 10000, "AnalogueGain": 5})

async def client():
    global localCamera
    async with websockets.connect("ws://" + WEBSOCKET_SLAVE + ":" + str(WEBSOCKET_PORT)) as websocketObj:
        # Send command to execute function
        command = {'action': 'start_camera'}
        await websocketObj.send(json.dumps(command))
        localCalibrationFrame = []
        remoteCalibrationFrame = []
        startResult = await websocketObj.recv()
        startResult = json.loads(startResult)
        if (startResult['result'] == 'success'): 
            #good to capture locally
            time.sleep(1)
            localCamera.start(show_preview=False)
            
            #if there's no homography already
            if CALIBRATION_NEEDED:
                # perform calibration routine
                print("Performing homography calibration")
                for i in range(NUMBER_OF_CALIBRATION_FRAMES): 
                    localCalibrationFrame = localCamera.capture_array()
                    command['action'] = 'capture'

                    #capture remotely
                    await websocketObj.send(json.dumps(command))

                    full_data = bytearray()
                    while True:
                        chunk = await websocketObj.recv()
                        if chunk == b"END":
                            break
                        full_data.extend(chunk)
                        await websocketObj.send("Ok")
                    
                    # Deserialize the binary data back into a NumPy array
                    buffer = io.BytesIO(full_data)
                    buffer.seek(0)
                    remoteCalibrationFrame = np.load(buffer)
                    remoteCalibrationFrame = np.fliplr(remoteCalibrationFrame)
                    print("Frame " + str(i) + " of " + str(NUMBER_OF_CALIBRATION_FRAMES) + " captured")

                    cv2.imwrite('remoteCalImg' + str(i) + '.jpg', remoteCalibrationFrame)
                    cv2.imwrite('localCalImg' + str(i) + '.jpg', localCalibrationFrame)
                    if i>= FIRST_CALIBRATION_FRAME: 
                        calibrationRoutine(True, localCalibrationFrame, remoteCalibrationFrame)

                command['action'] = 'CAMERA_OFF'

                #turn off camera
                await websocketObj.send(json.dumps(command))
                print("Calculating Homography")
                calibrationRoutine(False, localCalibrationFrame, remoteCalibrationFrame)

                if sensitivityMapNeeded: 
                    command = {'action': 'start_camera'}
                    await websocketObj.send(json.dumps(command))
                    startResult = await websocketObj.recv()
                    startResult = json.loads(startResult)
                    if (startResult['result'] == 'success'):
                        #then we're good to get some frames and send them for processing 
                        for i in range(NUMBER_OF_SENSITIVITY_FRAMES):
                            localSensitivityFrame = localCamera.capture_array()
                            command['action'] = 'capture'

                            #capture remotely
                            await websocketObj.send(json.dumps(command))

                            full_data = bytearray()
                            while True:
                                chunk = await websocketObj.recv()
                                if chunk == b"END":
                                    break
                                full_data.extend(chunk)
                                await websocketObj.send("Ok")
                            
                            # Deserialize the binary data back into a NumPy array
                            buffer = io.BytesIO(full_data)
                            buffer.seek(0)
                            remoteSensitivityFrame = np.load(buffer)
                            remoteSensitivityFrame = np.fliplr(remoteSensitivityFrame)
                            
                            if i >= FIRST_SENSITIVITY_FRAME:
                                localSensitivityFrame = align_fromHomography(localSensitivityFrame, HomographyMatrix);
                                sensitivityMapRoutine(True, localSensitivityFrame, remoteSensitivityFrame)

                        sensitivityMapRoutine(False, localSensitivityFrame, remoteSensitivityFrame)

            for i in range(NUMBER_OF_FRAMES):
                command = {'action': 'LED_ON'}
                await websocketObj.send(json.dumps(command))
                time.sleep(0.5)
                localFrame = localCamera.capture_array()
                command['action'] = 'capture'

                #capture remotely
                await websocketObj.send(json.dumps(command))

                full_data = bytearray()
                while True:
                    chunk = await websocketObj.recv()
                    if chunk == b"END":
                        break
                    full_data.extend(chunk)
                    await websocketObj.send("Ok")
                
                # Deserialize the binary data back into a NumPy array
                buffer = io.BytesIO(full_data)
                buffer.seek(0)
                remoteFrame = np.load(buffer)
                remoteFrame = np.fliplr(remoteFrame)
                # Align and correct images
                    #we now have two corrected images, we need to correct index 1 to match 2
                localFrame = align_fromHomography(localFrame, HomographyMatrix);
    
                cv2.imwrite('testImage' + str(i) + '.jpg', remoteFrame)
                cv2.imwrite('localImageTest' + str(i) + '.jpg', localFrame)
                differenceImage = performDifferenceIdentity(localFrame, remoteFrame)
                
                cv2.imwrite('differneceImage' + str(i) + '.jpg', differenceImage)

                print(f"Received array shape: {remoteFrame.shape}")
            
            command = {'action': 'LED_OFF'}
            await websocketObj.send(json.dumps(command))

            command = {'action': 'CAMERA_OFF'}
            await websocketObj.send(json.dumps(command))

            print('Done')
            exit()
            #large_data = b"".join(full_data)
            #captureResult = await websocket.recv()
            #captureResult = np.array(json.loads(captureResult))
       
        else: 
            #didn't work
            exit()

        print("Received numpy array:")

def performDifferenceIdentity(localFrame, remoteFrame): 
    #subtract the two images to create a difference image
    differenceFrame = np.float32(localFrame) - np.float32(remoteFrame)

    #De-sensitize via the sensitivity map
    differenceFrame = np.multiply(differenceFrame, Sensitivity_Map)

    #Apply a gain to the resulting difference map
    differenceFrame = np.uint8(np.abs(differenceFrame) * DIFFERENCE_GAIN)

    #Apply a threshold for the floor sensitivity of difference
    differencePixels = differenceFrame > DIFFERENCE_FLOOR

    #draw some circles where the threshold is met
    # Define the radius of the circles
    radius = 5

    # Define the thickness of the circles (-1 means filled circle)
    thickness = -1

    USE_CONTOURS = False

    if USE_CONTOURS:
        # Threshold the difference image
        _, thresh = cv2.threshold(differenceFrame[:,:,1], 20, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Draw circles around the contours
        for contour in contours:
            if cv2.contourArea(contour) > 10:  # You can adjust the contour area threshold as needed
                (x, y), radius = cv2.minEnclosingCircle(contour)
                center = (int(x), int(y))
                cv2.circle(localFrame, center, 5, [0, 0, 255], thickness)
    else:
        # Find the indices where the binary matrix is True
        y_indices, x_indices = np.where(differencePixels[:,:,1])

        # Iterate over the indices and draw the circles on the image
        for (x, y) in zip(x_indices, y_indices):
            cv2.circle(localFrame, (x, y), radius, [0,0,255], thickness)
    
    #Mark the floor-clearing areas in frame1 and output
    return localFrame

def sensitivityMapRoutine(accumulateFrame, localFrame, remoteFrame): 
    # accumulate an arbitrary number of frames
    global Sensitivity_Accumulation
    global Sensitivity_Map
    global Sensitivity_Frames_Accumulated
    
    if accumulateFrame: 
        differenceFrame = np.float32(localFrame)-np.float32(remoteFrame)
        cv2.imwrite('sensitivity_Diff' + str(Sensitivity_Frames_Accumulated) + '.jpg', np.uint8(np.abs(differenceFrame)))
        cv2.imwrite('sensitivity_Local' + str(Sensitivity_Frames_Accumulated) + '.jpg', np.abs(localFrame))
        cv2.imwrite('sensitivity_Remote' + str(Sensitivity_Frames_Accumulated) + '.jpg', np.abs(remoteFrame))
        Sensitivity_Accumulation.append(differenceFrame)
        Sensitivity_Frames_Accumulated = Sensitivity_Frames_Accumulated + 1
    elif Sensitivity_Frames_Accumulated>0:
        stackedSensitivity = np.stack(Sensitivity_Accumulation, axis=0)
        floatMap = np.float32(np.mean(stackedSensitivity, axis=0))
        floatMap = np.abs(floatMap)
        Sensitivity_Map = np.reciprocal(floatMap + 1) #+1 here accounts for the fact that a perfect match approaches 0

        with open(SENSITIVITY_MAP_NAME, 'wb') as f:
            pickle.dump(Sensitivity_Map, f)

        sensitivityImage = np.zeros((CAMERA_V_RESOLUTION, CAMERA_H_RESOLUTION, 3), dtype=np.uint8)
        
        #Print diff image of all 3 colors
        sensitivityImage[:,:,0] = np.int8(Sensitivity_Map[:,:,0] * 255)
        cv2.imwrite('./sensitivityMatrixBlue.png', sensitivityImage)
        sensitivityImage[:,:,0] = sensitivityImage[:,:,0] * 0
        
        sensitivityImage[:,:,1] = np.int8(Sensitivity_Map[:,:,1] * 255)
        cv2.imwrite('./sensitivityMatrixGreen.png', sensitivityImage)
        sensitivityImage[:,:,1] = sensitivityImage[:,:,1] * 0

        sensitivityImage[:,:,2] = np.int8(Sensitivity_Map[:,:,2] * 255)
        cv2.imwrite('./sensitivityMatrixRed.png', sensitivityImage)
        sensitivityImage[:,:,2] = sensitivityImage[:,:,2] * 0

async def captureFrame(websocket, Frames): 
    global localCamera
    command = []
    for i in range(Frames): 
        localImage = localCamera.capture_array()
        command['action'] = 'capture'

        #capture remotely
        await websocket.send(json.dumps(command))

        full_data = bytearray()
        while True:
            chunk = await websocket.recv()
            if chunk == b"END":
                break
            full_data.extend(chunk)
            await websocket.send("Ok")
        
        # Deserialize the binary data back into a NumPy array
        buffer = io.BytesIO(full_data)
        buffer.seek(0)
        remoteFrame = np.load(buffer)
        remoteFrame = np.fliplr(remoteFrame)
        print("Frame " + str(i) + " of " + str(NUMBER_OF_CALIBRATION_FRAMES) + " captured")
        return {"Local": localImage, "Remote": remoteFrame}
        #cv2.imwrite('remoteCalImg' + str(i) + '.jpg', remoteFrame)
        #cv2.imwrite('localCalImg' + str(i) + '.jpg', localImage)


def calibrationRoutine(accumulateFrames, frame1, frame2): 
    global rawCalibrationImageSet_1
    global rawCalibrationImageSet_2
    global calibrationFramesAccumulated
    global HomographyMatrix

    if calibrationFramesAccumulated == 0:
        rawCalibrationImageSet_1 = [] 

    if accumulateFrames: 
        rawCalibrationImageSet_1.append(frame1)
        rawCalibrationImageSet_2.append(frame2)
        calibrationFramesAccumulated = calibrationFramesAccumulated + 1
    else: 
        HomographyMatrix = []
        for z in range(calibrationFramesAccumulated): 
            #We've collected the images, now we need to generate the homography matrix
            HomographyMatrix.append(align_images(rawCalibrationImageSet_1[z], rawCalibrationImageSet_2[z]))
            print('frame comparison ' + str(z) + ' completed out of ' + str(calibrationFramesAccumulated))
            
        print('Captures complete, generating optics calibration matrix')
        HomographyMatrix_Output = np.mean(HomographyMatrix, axis=0)

        with open(HOMOGRAPHY_CALIBRATION_NAME, 'wb') as f:
            pickle.dump(HomographyMatrix_Output, f)

        HomographyMatrix = HomographyMatrix_Output
if __name__ == "__main__":
    asyncio.run(client())