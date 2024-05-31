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
NUMBER_OF_FRAMES = 10

picam2a = Picamera2()
camera_configa = picam2a.create_still_configuration(
        main={"size": (1920, 1080)},
        queue = False)
picam2a.configure(camera_configa)
picam2a.set_controls({"ExposureTime": 10000, "AnalogueGain": 5})


async def client():
    global picam2a
    async with websockets.connect("ws://" + WEBSOCKET_SLAVE + ":" + str(WEBSOCKET_PORT)) as websocket:
        # Send command to execute function
        command = {'action': 'start_camera'}
        await websocket.send(json.dumps(command))

        startResult = await websocket.recv()
        startResult = json.loads(startResult)
        if (startResult['result'] == 'success'): 
            #good to capture locally
            time.sleep(1)
            picam2a.start(show_preview=False)

            for i in range(NUMBER_OF_FRAMES):
                localImage = picam2a.capture_array()
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
                large_array = np.load(buffer)
                cv2.imwrite('testImage' + str(i) + '.jpg', large_array)
                cv2.imwrite('localImageTest' + str(i) + '.jpg', localImage)
                print(f"Received array shape: {large_array.shape}")
            
            command = {'action': 'LED_OFF'}
            await websocket.send(json.dumps(command))
            print('Done')
            exit()
            #large_data = b"".join(full_data)
            #captureResult = await websocket.recv()
            #captureResult = np.array(json.loads(captureResult))
       
        else: 
            #didn't work
            exit()

        print("Received numpy array:")

if __name__ == "__main__":
    asyncio.run(client())