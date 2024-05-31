import asyncio
import websockets
import numpy as np
import json
from picamera2 import Picamera2, Preview
import time
import cv2
from Libraries import PiRAW2TIF_16bit
import io
from Libraries.LargeLEDArray import *

#this code is meant to be ran on a computer who is running the 'sink'
#of a trigger/sink system.
#
#The code will start up and await commands to start
#after starting it will reply 
#
#This code is the Server code of a websocket arrangement

WEBSOCKET_MASTER = 'camera0bee.lan'
WEBSOCKET_SLAVE = 'beemonitor.lan'
WEBSOCKET_PORT = 18873
FRAGMENT_SIZE = 1024*1024

cameraIsPrimed = False
cameraIsStarted = False 
ledFlashColor = [0, 50, 0]

def startCamera():
    global cameraIsStarted
    global cameraIsPrimed
    picam2a = Picamera2(0)
    camera_configa = picam2a.create_still_configuration(
        main={"size": (1920, 1080)},
        queue = True)
    picam2a.configure(camera_configa)
    picam2a.set_controls({"ExposureTime": 10000, "AnalogueGain": 5})
    picam2a.start(show_preview=False)

    #for i in range(3): 
    #     myArray = picam2a.capture_array()
    #     cv2.imwrite('quickCam' + str(i) + '.jpg', myArray)

    cameraIsStarted = True
    return picam2a

def captureFrame(camera, captures = 1, DO_TIFF = False): 
    data_a = []
    for frame in range(captures): 
            if DO_TIFF:
                    data_a.append(camera.capture_array("raw"))
                   
            else: 
                    data_a.append(camera.capture_array())
            #img_b = cv2.cvtColor(img2[2], cv2.COLOR_YUV420p2RGB) #alternatively cv2.COLOR_YUV2RGB_I420
            print("Captured frame " + str(frame))
    return data_a

# WebSocket server handler
async def handler(websocket, path):
    global cameraIsStarted
    ledArray = LargeLEDArray()
    async for message in websocket:
        command = json.loads(message)
        if command['action'] == 'start_camera':
            # Execute the function and get the numpy array
            if cameraIsStarted == False:
                cameraInstance = startCamera()

            if cameraIsStarted: 
                 startResult = {'result': 'success'}
            else:
                 startResult = {'result': 'failure'}
            
            ledArray.setAllLEDs([0, 0, 0])
            await websocket.send(json.dumps(startResult))

        elif command['action'] == 'capture':
            if cameraIsStarted:
                ledArray.setAllLEDs(ledFlashColor)
                result_array = captureFrame(camera = cameraInstance)
                # Convert the numpy array to a list for JSON serialization
                #sendContent(result_array, websocket)
                large_array = np.array(result_array[0])
                buffer = io.BytesIO()
                np.save(buffer, large_array)
                buffer.seek(0)
                data = buffer.read()

                # Send the binary data in chunks
                for i in range(0, len(data), FRAGMENT_SIZE):
                    chunk = data[i:i + FRAGMENT_SIZE]
                    #print("Sending " + str(i))
                    await websocket.send(chunk)
                    okToSend = await websocket.recv()
                
                # Send a signal to indicate the end of transmission
                await websocket.send(b"END")

        elif command['action'] == 'LED_OFF':
             ledArray.setAllLEDs([0, 0, 0])

async def sendContent(large_array, websocket): 
    # Serialize the array to a binary format
    buffer = io.BytesIO()
    np.save(buffer, large_array)
    buffer.seek(0)
    data = buffer.read()

    # Send the binary data in chunks
    for i in range(0, len(data), FRAGMENT_SIZE):
        chunk = data[i:i + FRAGMENT_SIZE]
        await websocket.send(chunk)
    
    # Send a signal to indicate the end of transmission
    await websocket.send(b"END")

# Start the WebSocket server
async def main():
    async with websockets.serve(handler, '0.0.0.0', WEBSOCKET_PORT):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())