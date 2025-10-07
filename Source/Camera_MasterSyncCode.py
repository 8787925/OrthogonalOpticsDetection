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
import pickle
import logging
from websockets.exceptions import ConnectionClosed, WebSocketException

#this code is meant to be ran on the computer who is running the 'Trigger' camera
#
#First it sends a 'startup' command, to the 'Sink' computer, and awaits signal that the camera is ready
#
#This code is technically the 'client' code of a websocket arrangement

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# Connection settings
MAX_RETRY_ATTEMPTS = 5
INITIAL_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 30.0  # seconds
CONNECTION_TIMEOUT = 30  # seconds
HEARTBEAT_INTERVAL = 10  # seconds

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

async def connect_with_retry(max_attempts=MAX_RETRY_ATTEMPTS):
    """Establish WebSocket connection with exponential backoff retry"""
    attempt = 0
    delay = INITIAL_RETRY_DELAY
    
    while attempt < max_attempts:
        try:
            logger.info(f"Attempting to connect to ws://{WEBSOCKET_SLAVE}:{WEBSOCKET_PORT} (attempt {attempt + 1}/{max_attempts})")
            websocket = await websockets.connect(
                f"ws://{WEBSOCKET_SLAVE}:{WEBSOCKET_PORT}",
                ping_interval=HEARTBEAT_INTERVAL,
                ping_timeout=CONNECTION_TIMEOUT,
                close_timeout=10
            )
            logger.info("Successfully connected to slave")
            return websocket
            
        except Exception as e:
            attempt += 1
            if attempt < max_attempts:
                logger.warning(f"Connection failed: {e}. Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)  # Exponential backoff with cap
            else:
                logger.error(f"Failed to connect after {max_attempts} attempts")
                raise
    
    return None

async def send_command_with_retry(websocket, command, max_attempts=3):
    """Send command with retry logic"""
    for attempt in range(max_attempts):
        try:
            await websocket.send(json.dumps(command))
            return True
        except ConnectionClosed:
            logger.warning(f"Connection closed while sending command (attempt {attempt + 1})")
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
            else:
                raise
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            if attempt < max_attempts - 1:
                await asyncio.sleep(1)
            else:
                raise
    return False

async def reset_remote_slave(websocket):
    """Send reset command to slave to clean up its resources"""
    try:
        logger.info("Sending reset command to slave")
        reset_command = {'action': 'reset'}
        await send_command_with_retry(websocket, reset_command)
        response = await websocket.recv()
        result = json.loads(response)
        if result.get('result') == 'success':
            logger.info("Slave reset successful")
            return True
        else:
            logger.warning(f"Slave reset failed: {result.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Error resetting slave: {e}")
        return False

async def send_command_and_receive_data(websocket, command):
    """Send a command and receive binary data response with error handling"""
    try:
        await send_command_with_retry(websocket, command)
        
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
        remote_frame = np.load(buffer)
        return np.fliplr(remote_frame)
        
    except ConnectionClosed:
        logger.error("Connection closed during data transfer")
        raise
    except Exception as e:
        logger.error(f"Error in send_command_and_receive_data: {e}")
        raise

async def start_remote_camera(websocket):
    """Start the remote camera and return success status with retry logic"""
    try:
        command = {'action': 'start_camera'}
        await send_command_with_retry(websocket, command)
        start_result = await websocket.recv()
        start_result = json.loads(start_result)
        success = start_result['result'] == 'success'
        if success:
            logger.info("Remote camera started successfully")
        else:
            logger.error("Failed to start remote camera")
        return success
    except Exception as e:
        logger.error(f"Error starting remote camera: {e}")
        return False

async def perform_calibration_routine(websocket):
    """Perform homography calibration between local and remote cameras"""
    global CALIBRATION_NEEDED, HomographyMatrix
    
    if not CALIBRATION_NEEDED:
        return True
        
    print("Performing homography calibration")
    local_frames = []
    remote_frames = []
    
    for i in range(NUMBER_OF_CALIBRATION_FRAMES):
        local_frame = localCamera.capture_array()
        remote_frame = await send_command_and_receive_data(websocket, {'action': 'capture'})
        
        print(f"Frame {i} of {NUMBER_OF_CALIBRATION_FRAMES} captured")
        cv2.imwrite(f'remoteCalImg{i}.jpg', remote_frame)
        cv2.imwrite(f'localCalImg{i}.jpg', local_frame)
        
        if i >= FIRST_CALIBRATION_FRAME:
            local_frames.append(local_frame)
            remote_frames.append(remote_frame)
    
    await websocket.send(json.dumps({'action': 'CAMERA_OFF'}))
    print("Calculating Homography")
    
    # Calculate homography matrices
    homography_matrices = []
    for j, (local_frame, remote_frame) in enumerate(zip(local_frames, remote_frames)):
        homography_matrices.append(align_images(local_frame, remote_frame))
        print(f'Frame comparison {j} completed out of {len(local_frames)}')
    
    # Save homography matrix
    HomographyMatrix = np.mean(homography_matrices, axis=0)
    with open(HOMOGRAPHY_CALIBRATION_NAME, 'wb') as f:
        pickle.dump(HomographyMatrix, f)
    
    CALIBRATION_NEEDED = False
    return True

async def perform_sensitivity_mapping(websocket):
    """Generate sensitivity mapping between cameras"""
    global sensitivityMapNeeded
    
    if not sensitivityMapNeeded:
        return True
        
    if not await start_remote_camera(websocket):
        return False
        
    print("Performing sensitivity mapping")
    local_frames = []
    remote_frames = []
    
    for i in range(NUMBER_OF_SENSITIVITY_FRAMES):
        local_frame = localCamera.capture_array()
        remote_frame = await send_command_and_receive_data(websocket, {'action': 'capture'})
        
        if i >= FIRST_SENSITIVITY_FRAME:
            aligned_local = align_fromHomography(local_frame, HomographyMatrix)
            local_frames.append(aligned_local)
            remote_frames.append(remote_frame)
    
    # Process sensitivity data
    sensitivityMapRoutine(False, local_frames, remote_frames)
    return True

async def perform_detection_sequence(websocket):
    """Main detection sequence with LED flashing and error handling"""
    logger.info("Starting detection sequence")
    
    try:
        for i in range(NUMBER_OF_FRAMES):
            logger.info(f"Processing frame {i+1}/{NUMBER_OF_FRAMES}")
            
            # Turn on LED
            await send_command_with_retry(websocket, {'action': 'LED_ON'})
            time.sleep(0.5)
            
            # Capture frames
            local_frame = localCamera.capture_array()
            remote_frame = await send_command_and_receive_data(websocket, {'action': 'capture'})
            
            # Align and process images
            aligned_local = align_fromHomography(local_frame, HomographyMatrix)
            cv2.imwrite(f'RemoteImage{i}.jpg', remote_frame)
            cv2.imwrite(f'LocalImageTest{i}.jpg', aligned_local)

            # Perform difference detection
            difference_image = performDifferenceIdentity(aligned_local, remote_frame)
            cv2.imwrite(f'DifferenceImage{i}.jpg', difference_image)
            
            logger.info(f"Processed frame {i+1}/{NUMBER_OF_FRAMES}, shape: {remote_frame.shape}")
        
        # Turn off LED
        await send_command_with_retry(websocket, {'action': 'LED_OFF'})
        logger.info('Detection sequence completed successfully')
        return True
        
    except ConnectionClosed:
        logger.error("Connection lost during detection sequence")
        return False
    except Exception as e:
        logger.error(f"Error in detection sequence: {e}")
        return False

async def client():
    """Main client function with robust connection handling"""
    global localCamera
    
    websocket = None
    try:
        # Establish connection with retry
        websocket = await connect_with_retry()
        
        # Reset slave state to ensure clean start
        await reset_remote_slave(websocket)
        
        # Start remote camera
        if not await start_remote_camera(websocket):
            logger.error("Failed to start remote camera")
            return False
        
        # Start local camera
        logger.info("Starting local camera")
        time.sleep(1)
        localCamera.start(show_preview=False)
        
        # Perform calibration if needed
        if CALIBRATION_NEEDED:
            logger.info("Starting calibration routine")
            if not await perform_calibration_routine(websocket):
                logger.error("Calibration failed")
                return False
        
        # Perform sensitivity mapping if needed
        if sensitivityMapNeeded:
            logger.info("Starting sensitivity mapping")
            if not await perform_sensitivity_mapping(websocket):
                logger.error("Sensitivity mapping failed")
                return False
        
        # Restart remote camera for detection
        if not await start_remote_camera(websocket):
            logger.error("Failed to restart remote camera for detection")
            return False
        
        # Run main detection sequence
        logger.info("Starting detection sequence")
        await perform_detection_sequence(websocket)
        
        logger.info("All operations completed successfully")
        return True
        
    except ConnectionClosed:
        logger.error("Connection lost during operation")
        return False
    except Exception as e:
        logger.error(f"Error in client operation: {e}")
        return False
    finally:
        # Clean up resources
        try:
            if localCamera:
                localCamera.stop()
                logger.info("Local camera stopped")
        except Exception as e:
            logger.error(f"Error stopping local camera: {e}")
            
        if websocket:
            try:
                # Send final LED off command
                await websocket.send(json.dumps({'action': 'LED_OFF'}))
                await websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing websocket: {e}")

async def client_with_retry():
    """Client wrapper with automatic retry on failure"""
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            logger.info(f"Starting client operation (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})")
            success = await client()
            if success:
                logger.info("Client operation completed successfully")
                return True
            else:
                logger.warning(f"Client operation failed (attempt {attempt + 1})")
                
        except Exception as e:
            logger.error(f"Client operation error (attempt {attempt + 1}): {e}")
            
        # Wait before retry (except on last attempt)
        if attempt < MAX_RETRY_ATTEMPTS - 1:
            delay = INITIAL_RETRY_DELAY * (2 ** attempt)  # Exponential backoff
            delay = min(delay, MAX_RETRY_DELAY)  # Cap the delay
            logger.info(f"Waiting {delay} seconds before retry...")
            await asyncio.sleep(delay)
    
    logger.error("All retry attempts failed")
    return False

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

def sensitivityMapRoutine(accumulate_frame, local_frames, remote_frames): 
    """Generate sensitivity map from multiple frame pairs"""
    global Sensitivity_Accumulation, Sensitivity_Map, Sensitivity_Frames_Accumulated
    
    if accumulate_frame:
        # This mode is no longer used with the new structure
        return
    
    if not local_frames or not remote_frames:
        return
        
    # Process all frame pairs
    difference_frames = []
    for i, (local_frame, remote_frame) in enumerate(zip(local_frames, remote_frames)):
        difference_frame = np.float32(local_frame) - np.float32(remote_frame)
        difference_frames.append(difference_frame)
        
        # Save individual frames for debugging
        cv2.imwrite(f'sensitivity_Diff{i}.jpg', np.uint8(np.abs(difference_frame)))
        cv2.imwrite(f'sensitivity_Local{i}.jpg', np.abs(local_frame))
        cv2.imwrite(f'sensitivity_Remote{i}.jpg', np.abs(remote_frame))
    
    # Calculate mean sensitivity map
    stacked_sensitivity = np.stack(difference_frames, axis=0)
    float_map = np.float32(np.mean(stacked_sensitivity, axis=0))
    float_map = np.abs(float_map)
    Sensitivity_Map = np.reciprocal(float_map + 1)  # +1 accounts for perfect match approaching 0

    # Save sensitivity map
    with open(SENSITIVITY_MAP_NAME, 'wb') as f:
        pickle.dump(Sensitivity_Map, f)

    # Create visualization images
    sensitivity_image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    
    # Blue channel
    sensitivity_image[:,:,0] = np.uint8(Sensitivity_Map[:,:,0] * 255)
    cv2.imwrite('./sensitivityMatrixBlue.png', sensitivity_image)
    sensitivity_image[:,:,0] = 0
    
    # Green channel
    sensitivity_image[:,:,1] = np.uint8(Sensitivity_Map[:,:,1] * 255)
    cv2.imwrite('./sensitivityMatrixGreen.png', sensitivity_image)
    sensitivity_image[:,:,1] = 0

    # Red channel
    sensitivity_image[:,:,2] = np.uint8(Sensitivity_Map[:,:,2] * 255)
    cv2.imwrite('./sensitivityMatrixRed.png', sensitivity_image)
    
    print("Sensitivity mapping complete")

if __name__ == "__main__":
    try:
        logger.info("Starting camera master sync application")
        success = asyncio.run(client_with_retry())
        if success:
            logger.info("Application completed successfully")
        else:
            logger.error("Application failed")
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        logger.info("Application shutdown")