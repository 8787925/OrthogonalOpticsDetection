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
import logging
from websockets.exceptions import ConnectionClosed, WebSocketException

#this code is meant to be ran on a computer who is running the 'sink'
#of a trigger/sink system.
#
#The code will start up and await commands to start
#after starting it will reply 
#
#This code is the Server code of a websocket arrangement

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

WEBSOCKET_MASTER = 'camera0bee.lan'
WEBSOCKET_SLAVE = 'beemonitor.lan'
WEBSOCKET_PORT = 18873
FRAGMENT_SIZE = 1024*1024
CAMERA_H_RESOLUTION = 1920
CAMERA_V_RESOLUTION = 1080
CONNECTION_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 10  # seconds

cameraIsPrimed = False
cameraIsStarted = False 
ledFlashColor = [0, 50, 0]

def stopCamera(camera_instance):
    """Stop the camera and clean up resources properly"""
    global cameraIsStarted
    global cameraIsPrimed
    
    try:
        if camera_instance and cameraIsStarted:
            logger.info("Stopping camera...")
            camera_instance.stop()
            cameraIsStarted = False
            logger.info("Camera stopped successfully")
            return True
    except Exception as e:
        logger.error(f"Error stopping camera: {e}")
        cameraIsStarted = False  # Reset state even if stop failed
        return False
    return False

def closeCamera(camera_instance):
    """Properly close and release camera resources"""
    global cameraIsStarted
    global cameraIsPrimed
    
    try:
        if camera_instance:
            if cameraIsStarted:
                logger.info("Stopping camera before closing...")
                camera_instance.stop()
                cameraIsStarted = False
                
            logger.info("Closing camera to release resources...")
            camera_instance.close()
            cameraIsPrimed = False
            logger.info("Camera closed and resources released")
            return True
    except Exception as e:
        logger.error(f"Error closing camera: {e}")
        # Reset states even if close failed
        cameraIsStarted = False
        cameraIsPrimed = False
        return False
    return False

def cleanup_resources(state):
    """Clean up camera and LED resources safely"""
    try:
        if state.get('cameraInstance'):
            logger.info("Cleaning up camera resources...")
            closeCamera(state['cameraInstance'])
            state['cameraInstance'] = None
            state['cameraIsStarted'] = False
            state['cameraIsPrimed'] = False
        
        if state.get('ledArray'):
            logger.info("Turning off LEDs...")
            state['ledArray'].setAllLEDs([0, 0, 0])
            
        logger.info("Resources cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during resource cleanup: {e}")


def reset_state():
    """Reset the state to initial values"""
    return {
        'cameraIsPrimed': False,
        'cameraIsStarted': False,
        'cameraInstance': None,
        'ledArray': LargeLEDArray(),
        'last_heartbeat': time.time(),
    }

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
    try:
        if not state['cameraIsStarted']:
            # If camera exists but is not started, check if it's properly configured
            if state.get('cameraInstance') and state['cameraIsPrimed']:
                try:
                    state['cameraInstance'].start(show_preview=False)
                    state['cameraIsStarted'] = True
                    logger.info("Restarted existing camera")
                except Exception as e:
                    logger.warning(f"Failed to restart existing camera: {e}. Creating new camera.")
                    # Clean up the old camera and create a new one
                    closeCamera(state['cameraInstance'])
                    state['cameraInstance'] = startCamera(CAMERA_V_RESOLUTION, CAMERA_H_RESOLUTION)
                    state['cameraIsPrimed'] = True
                    state['cameraIsStarted'] = True
            else:
                # Create a new camera instance
                state['cameraInstance'] = startCamera(CAMERA_V_RESOLUTION, CAMERA_H_RESOLUTION)
                state['cameraIsPrimed'] = True
                state['cameraIsStarted'] = True

        result = {'result': 'success' if state['cameraIsStarted'] else 'failure'}
        state['ledArray'].setAllLEDs([0, 0, 0])
        await websocket.send(json.dumps(result))
        logger.info("Camera started successfully")
    except Exception as e:
        logger.error(f"Error starting camera: {e}")
        result = {'result': 'error', 'message': str(e)}
        try:
            await websocket.send(json.dumps(result))
        except:
            pass  # Connection might be closed
        
async def handle_capture(command, websocket, state):
    try:
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
            logger.info("Frame captured and sent successfully")
        else:
            logger.warning("Capture requested but camera not started")
    except ConnectionClosed:
        logger.warning("Connection closed during capture")
        raise
    except Exception as e:
        logger.error(f"Error during capture: {e}")

async def handle_camera_off(command, websocket, state):
    try:
        if state.get('cameraInstance') and state['cameraIsStarted']:
            success = stopCamera(state['cameraInstance'])
            state['cameraIsStarted'] = False
            if success:
                logger.info("Camera stopped via handle_camera_off")
            result = {'result': 'success' if success else 'error'}
            await websocket.send(json.dumps(result))
    except Exception as e:
        logger.error(f"Error in handle_camera_off: {e}")
        result = {'result': 'error', 'message': str(e)}
        try:
            await websocket.send(json.dumps(result))
        except:
            pass

async def handle_led_on(command, websocket, state):
    try:
        state['ledArray'].setAllLEDs(ledFlashColor)
        logger.debug("LED turned on")
    except Exception as e:
        logger.error(f"Error turning on LED: {e}")

async def handle_led_off(command, websocket, state):
    try:
        state['ledArray'].setAllLEDs([0, 0, 0])
        logger.debug("LED turned off")
    except Exception as e:
        logger.error(f"Error turning off LED: {e}")

async def handle_set_led_color(command, websocket, state):
    try:
        global ledFlashColor
        if 'color' in command:
            ledFlashColor = command['color']
            result = {'result': 'success', 'color': ledFlashColor}
            logger.info(f"LED color set to {ledFlashColor}")
        else:
            result = {'result': 'error', 'message': 'No color specified'}
        await websocket.send(json.dumps(result))
    except Exception as e:
        logger.error(f"Error setting LED color: {e}")

async def handle_ping(command, websocket, state):
    """Handle heartbeat/ping requests"""
    try:
        state['last_heartbeat'] = time.time()
        pong_response = {'action': 'pong', 'timestamp': state['last_heartbeat']}
        await websocket.send(json.dumps(pong_response))
        logger.debug("Heartbeat responded")
    except Exception as e:
        logger.error(f"Error responding to ping: {e}")

async def handle_reset(command, websocket, state):
    """Handle reset requests to clean up resources"""
    try:
        logger.info("Reset requested - cleaning up resources")
        cleanup_resources(state)
        # Reset state but keep the websocket connection
        new_state = reset_state()
        state.update(new_state)
        result = {'result': 'success', 'message': 'Resources reset'}
        await websocket.send(json.dumps(result))
        logger.info("Reset completed successfully")
    except Exception as e:
        logger.error(f"Error during reset: {e}")
        result = {'result': 'error', 'message': str(e)}
        try:
            await websocket.send(json.dumps(result))
        except:
            pass

ACTION_HANDLERS = {
    'start_camera': handle_start_camera,
    'capture': handle_capture,
    'CAMERA_OFF': handle_camera_off,
    'LED_ON': handle_led_on,
    'LED_OFF': handle_led_off,
    'SET_LED_COLOR': handle_set_led_color,
    'ping': handle_ping,
    'reset': handle_reset,
}

async def handler(websocket, path):
    state = reset_state()
    client_address = websocket.remote_address
    logger.info(f"New client connected from {client_address}")
    
    try:
        async for message in websocket:
            try:
                command = json.loads(message)
                action = command.get('action')
                
                if action in ACTION_HANDLERS:
                    await ACTION_HANDLERS[action](command, websocket, state)
                else:
                    logger.warning(f"Unknown action received: {action}")
                    error_response = {'result': 'error', 'message': f'Unknown action: {action}'}
                    await websocket.send(json.dumps(error_response))
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                error_response = {'result': 'error', 'message': 'Invalid JSON format'}
                try:
                    await websocket.send(json.dumps(error_response))
                except:
                    break
            except ConnectionClosed:
                logger.info(f"Client {client_address} disconnected")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
    except ConnectionClosed:
        logger.info(f"Connection with {client_address} closed")
    except WebSocketException as e:
        logger.error(f"WebSocket error with {client_address}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error with {client_address}: {e}")
    finally:
        # Clean up resources when client disconnects
        logger.info(f"Cleaning up resources for {client_address}")
        cleanup_resources(state)

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
    logger.info(f"Starting WebSocket server on {WEBSOCKET_PORT}")
    
    # Set up server with better configuration
    server = await websockets.serve(
        handler, 
        '0.0.0.0', 
        WEBSOCKET_PORT,
        ping_interval=HEARTBEAT_INTERVAL,
        ping_timeout=CONNECTION_TIMEOUT,
        close_timeout=10
    )
    
    logger.info(f"WebSocket server listening on ws://0.0.0.0:{WEBSOCKET_PORT}")
    logger.info("Server ready to accept connections. Press Ctrl+C to stop.")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("Server stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}")