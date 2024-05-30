import asyncio
import websockets
import json
import numpy as np
import io
import cv2
import time 

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

async def client():
    async with websockets.connect("ws://" + WEBSOCKET_SLAVE + ":" + str(WEBSOCKET_PORT)) as websocket:
        # Send command to execute function
        command = {'action': 'start_camera'}
        await websocket.send(json.dumps(command))
        #time.sleep(0.5)
        startResult = await websocket.recv()
        startResult = json.loads(startResult)
        if (startResult['result'] == 'success'): 
            #good to capture
            command['action'] = 'capture'
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
            cv2.imwrite('testImage.jpg', large_array)
            print(f"Received array shape: {large_array.shape}")

            #large_data = b"".join(full_data)
            #captureResult = await websocket.recv()
            #captureResult = np.array(json.loads(captureResult))
       
        else: 
            #didn't work
            exit()

        print("Received numpy array:")

if __name__ == "__main__":
    asyncio.run(client())