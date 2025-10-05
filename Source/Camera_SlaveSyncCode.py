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
CAMERA_H_RESOLUTION = 1920
CAMERA_V_RESOLUTION = 1080

cameraIsPrimed = False
cameraIsStarted = False 
ledFlashColor = [0, 50, 0]

def startCamera(V_res, H_res):
    global cameraIsStarted
    global cameraIsPrimed
    picam2a = Picamera2(0)
    camera_configa = picam2a.create_still_configuration(
        main={"size": (H_res,V_res)},
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

async def handle_start_camera(command, websocket, state):
    if not state['cameraIsStarted']:
        if state['cameraIsPrimed']:
            state['cameraInstance'].start(show_preview=False)
        else:
            state['cameraInstance'] = startCamera(CAMERA_V_RESOLUTION, CAMERA_H_RESOLUTION)
            state['cameraIsPrimed'] = True
        state['cameraIsStarted'] = True

    result = {'result': 'success' if state['cameraIsStarted'] else 'failure'}
    state['ledArray'].setAllLEDs([0, 0, 0])
    await websocket.send(json.dumps(result))

async def handle_capture(command, websocket, state):
    if state['cameraIsStarted']:
        result_array = captureFrame(camera=state['cameraInstance'])
        large_array = np.array(result_array[0])
        buffer = io.BytesIO()
        np.save(buffer, large_array)
        buffer.seek(0)
        data = buffer.read()
        for i in range(0, len(data), FRAGMENT_SIZE):
            chunk = data[i:i + FRAGMENT_SIZE]
            await websocket.send(chunk)
            await websocket.recv()
        await websocket.send(b"END")

async def handle_camera_off(command, websocket, state):
    state['cameraInstance'].stop()
    state['cameraIsStarted'] = False

async def handle_led_on(command, websocket, state):
    state['ledArray'].setAllLEDs(ledFlashColor)

async def handle_led_off(command, websocket, state):
    state['ledArray'].setAllLEDs([0, 0, 0])

async def handle_set_led_color(command, websocket, state):
    global ledFlashColor
    if 'color' in command:
        ledFlashColor = command['color']
        result = {'result': 'success', 'color': ledFlashColor}
    else:
        result = {'result': 'error', 'message': 'No color specified'}
    await websocket.send(json.dumps(result))

ACTION_HANDLERS = {
    'start_camera': handle_start_camera,
    'capture': handle_capture,
    'CAMERA_OFF': handle_camera_off,
    'LED_ON': handle_led_on,
    'LED_OFF': handle_led_off,
    'SET_LED_COLOR': handle_set_led_color,
}

async def handler(websocket, path):
    state = {
        'cameraIsPrimed': False,
        'cameraIsStarted': False,
        'cameraInstance': None,
        'ledArray': LargeLEDArray(),
    }
    async for message in websocket:
        command = json.loads(message)
        action = command.get('action')
        handler_func = ACTION_HANDLERS.get(action)
        if handler_func:
            await handler_func(command, websocket, state)

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