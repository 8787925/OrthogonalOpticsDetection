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
from CalibrationFileManager import CalibrationFileManager
from HomographyCalibrator import HomographyCalibrator
from SensitivityMapper import SensitivityMapper

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
NUMBER_OF_FRAMES = 10
NUMBER_OF_CALIBRATION_FRAMES = 15
FIRST_CALIBRATION_FRAME = 7
HOMOGRAPHY_CALIBRATION_NAME = 'wallCalibration_image_1080.pickle'
HomographyMatrix = []
CALIBRATION_NEEDED = True
calibrationFramesAccumulated = 0
rawCalibrationImageSet_1 = []
rawCalibrationImageSet_2 = []
NUMBER_OF_CAMERAS = 2

# Standard camera resolutions dictionary
STANDARD_RESOLUTIONS = {
    '480p': (640, 480),
    '720p': (1280, 720),
    '1080p': (1920, 1080),
    '1440p': (2560, 1440),
    '4K': (3840, 2160),
    '8K': (7680, 4320),
    'VGA': (640, 480),
    'SVGA': (800, 600),
    'XGA': (1024, 768),
    'SXGA': (1280, 1024),
    'UXGA': (1600, 1200),
    'QVGA': (320, 240),
    'HVGA': (480, 320),
    'nHD': (640, 360),
    'qHD': (960, 540),
    'WVGA': (800, 480),
    'FWVGA': (854, 480),
    'WSVGA': (1024, 600),
    'WXGA': (1366, 768)
}

# Current camera resolution setting
CAMERA_RESOLUTION = '1080p'  # Change this to use different resolutions

def get_camera_resolution(resolution_name):
    """
    Translate resolution name to (horizontal, vertical) tuple
    
    Args:
        resolution_name (str): Name of the resolution (e.g., '1080p', '720p', '4K')
    
    Returns:
        tuple: (horizontal_resolution, vertical_resolution)
    
    Raises:
        ValueError: If resolution name is not found in STANDARD_RESOLUTIONS
    """
    if resolution_name not in STANDARD_RESOLUTIONS:
        available_resolutions = ', '.join(STANDARD_RESOLUTIONS.keys())
        raise ValueError(f"Resolution '{resolution_name}' not found. Available resolutions: {available_resolutions}")
    
    return STANDARD_RESOLUTIONS[resolution_name]

# Get current camera resolution
CAMERA_H_RESOLUTION, CAMERA_V_RESOLUTION = get_camera_resolution(CAMERA_RESOLUTION)

def set_camera_resolution(resolution_name):
    """
    Set a new camera resolution and update the global variables
    
    Args:
        resolution_name (str): Name of the resolution (e.g., '1080p', '720p', '4K')
    
    Returns:
        tuple: (horizontal_resolution, vertical_resolution)
    
    Raises:
        ValueError: If resolution name is not found in STANDARD_RESOLUTIONS
    """
    global CAMERA_RESOLUTION, CAMERA_H_RESOLUTION, CAMERA_V_RESOLUTION
    
    h_res, v_res = get_camera_resolution(resolution_name)
    CAMERA_RESOLUTION = resolution_name
    CAMERA_H_RESOLUTION = h_res
    CAMERA_V_RESOLUTION = v_res
    
    logger.info(f"Camera resolution set to {resolution_name}: {h_res}x{v_res}")
    return h_res, v_res

def list_available_resolutions():
    """
    Return a list of all available resolution names
    
    Returns:
        list: List of available resolution names
    """
    return list(STANDARD_RESOLUTIONS.keys())

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

# Initialize calibration file manager
calibration_manager = CalibrationFileManager(HOMOGRAPHY_CALIBRATION_NAME, SENSITIVITY_MAP_NAME)

# Initialize homography calibrator
homography_calibrator = HomographyCalibrator(
    calibration_frames=NUMBER_OF_CALIBRATION_FRAMES,
    first_calibration_frame=FIRST_CALIBRATION_FRAME,
    debug_output=True
)

# Initialize sensitivity mapper
sensitivity_mapper = SensitivityMapper(
    sensitivity_frames=NUMBER_OF_SENSITIVITY_FRAMES,
    first_sensitivity_frame=FIRST_SENSITIVITY_FRAME,
    debug_output=True,
    camera_resolution=(CAMERA_H_RESOLUTION, CAMERA_V_RESOLUTION)
)

# Load existing calibration files using the manager
HomographyMatrix, Sensitivity_Map = calibration_manager.load_both_calibrations()

# Set calibration status based on loaded files
CALIBRATION_NEEDED = HomographyMatrix is None
sensitivityMapNeeded = Sensitivity_Map is None

# Initialize empty arrays if calibration data wasn't loaded
if HomographyMatrix is None:
    HomographyMatrix = []
if Sensitivity_Map is None:
    Sensitivity_Map = []

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

async def start_frame_buffering(websocket):
    """Start buffering frames on the slave side"""
    try:
        await send_command_with_retry(websocket, {'action': 'start_buffering'})
        response = await websocket.recv()
        result = json.loads(response)
        if result.get('result') == 'success':
            logger.info("Frame buffering started on slave")
            return True
        else:
            logger.error(f"Failed to start frame buffering: {result.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Error starting frame buffering: {e}")
        return False

async def capture_buffered_frame(websocket):
    """Request slave to capture a frame and store it in buffer"""
    try:
        await send_command_with_retry(websocket, {'action': 'capture_buffered'})
        response = await websocket.recv()
        result = json.loads(response)
        if result.get('result') == 'success':
            logger.debug("Buffered frame captured on slave")
            return True
        else:
            logger.error(f"Failed to capture buffered frame: {result.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Error capturing buffered frame: {e}")
        return False

async def transfer_all_buffered_frames(websocket):
    """Request all buffered frames from slave and return them as a list"""
    try:
        await send_command_with_retry(websocket, {'action': 'transfer_all_frames'})
        
        # Receive the number of frames first
        frame_count_data = await websocket.recv()
        frame_count = json.loads(frame_count_data)['frame_count']
        await websocket.send("Ok")
        logger.info(f"Receiving {frame_count} buffered frames from slave")
        
        frames = []
        for i in range(frame_count):
            logger.info(f"Receiving frame {i+1}/{frame_count}")
            
            # Receive frame data
            full_data = bytearray()
            while True:
                chunk = await websocket.recv()
                if chunk == b"FRAME_END":
                    break
                full_data.extend(chunk)
                await websocket.send("Ok")
            
            # Deserialize the frame
            buffer = io.BytesIO(full_data)
            buffer.seek(0)
            remote_frame = np.load(buffer)
            frames.append(np.fliplr(remote_frame))
        
        logger.info(f"Successfully received {len(frames)} buffered frames")
        return frames
        
    except ConnectionClosed:
        logger.error("Connection closed during buffered frame transfer")
        raise
    except Exception as e:
        logger.error(f"Error in transfer_all_buffered_frames: {e}")
        raise

async def stop_frame_buffering(websocket):
    """Stop buffering frames on the slave side"""
    try:
        await send_command_with_retry(websocket, {'action': 'stop_buffering'})
        response = await websocket.recv()
        result = json.loads(response)
        if result.get('result') == 'success':
            logger.info("Frame buffering stopped on slave")
            return True
        else:
            logger.error(f"Failed to stop frame buffering: {result.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Error stopping frame buffering: {e}")
        return False

async def clear_slave_buffer(websocket):
    """Clear the frame buffer on the slave side"""
    try:
        await send_command_with_retry(websocket, {'action': 'clear_buffer'})
        response = await websocket.recv()
        result = json.loads(response)
        if result.get('result') == 'success':
            logger.info("Slave frame buffer cleared")
            return True
        else:
            logger.error(f"Failed to clear slave buffer: {result.get('message', 'Unknown error')}")
            return False
    except Exception as e:
        logger.error(f"Error clearing slave buffer: {e}")
        return False

async def send_camera_configuration(websocket):
    """Send camera configuration to slave"""
    try:
        # Extract current camera configuration
        camera_config = {
            'resolution': {
                'width': CAMERA_H_RESOLUTION,
                'height': CAMERA_V_RESOLUTION,
                'name': CAMERA_RESOLUTION  # Include resolution name for reference
            },
            'controls': {
                'ExposureTime': 10000,
                'AnalogueGain': 5
            },
            'queue': False
        }
        
        command = {
            'action': 'set_camera_config',
            'config': camera_config
        }
        
        await send_command_with_retry(websocket, command)
        response = await websocket.recv()
        result = json.loads(response)
        
        if result.get('result') == 'success':
            logger.info(f"Camera configuration sent to slave successfully ({CAMERA_RESOLUTION}: {CAMERA_H_RESOLUTION}x{CAMERA_V_RESOLUTION})")
            return True
        else:
            logger.error(f"Failed to send camera configuration: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending camera configuration: {e}")
        return False

async def update_camera_controls(websocket, controls):
    """Update camera controls on slave during operation"""
    try:
        command = {
            'action': 'update_camera_controls',
            'controls': controls
        }
        
        await send_command_with_retry(websocket, command)
        response = await websocket.recv()
        result = json.loads(response)
        
        if result.get('result') == 'success':
            logger.info(f"Camera controls updated on slave: {controls}")
            return True
        else:
            logger.error(f"Failed to update camera controls: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating camera controls: {e}")
        return False

async def start_remote_camera(websocket):
    """Start the remote camera with synchronized configuration"""
    try:
        # First send camera configuration to ensure identical settings
        if not await send_camera_configuration(websocket):
            logger.error("Failed to send camera configuration to slave")
            return False
        
        # Then start the camera
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
    """Perform homography calibration between local and remote cameras using buffered approach"""
    global CALIBRATION_NEEDED, HomographyMatrix
    
    if not CALIBRATION_NEEDED:
        return True
        
    print("Performing homography calibration")
    
    # Start buffering on slave
    if not await start_frame_buffering(websocket):
        logger.error("Failed to start frame buffering for calibration")
        return False
    
    local_frames = []
    
    # Capture all calibration frames
    for i in range(NUMBER_OF_CALIBRATION_FRAMES):
        local_frame = localCamera.capture_array()
        
        # Save local frame for debugging
        cv2.imwrite(f'localCalImg{i}.jpg', local_frame)
        
        # Request slave to capture and buffer frame
        if not await capture_buffered_frame(websocket):
            logger.error(f"Failed to capture buffered calibration frame {i}")
            return False
        
        print(f"Frame {i} of {NUMBER_OF_CALIBRATION_FRAMES} captured")
        local_frames.append(local_frame)
    
    # Transfer all buffered frames from slave (while buffering is still active)
    remote_frames = await transfer_all_buffered_frames(websocket)
    
    # Now stop buffering
    if not await stop_frame_buffering(websocket):
        logger.error("Failed to stop frame buffering for calibration")
        return False
    
    if len(remote_frames) != len(local_frames):
        logger.error(f"Calibration frame count mismatch: local={len(local_frames)}, remote={len(remote_frames)}")
        return False
    
    # Save remote frames for debugging
    for i, remote_frame in enumerate(remote_frames):
        cv2.imwrite(f'remoteCalImg{i}.jpg', remote_frame)
    
    await websocket.send(json.dumps({'action': 'CAMERA_OFF'}))
    
    # Calculate homography matrix using the calibrator
    calculated_homography = homography_calibrator.calculate_homography_matrix(local_frames, remote_frames)
    
    if calculated_homography is None:
        logger.error("Failed to calculate homography matrix")
        return False
    
    # Validate the calculated homography
    if not homography_calibrator.validate_homography_matrix(calculated_homography):
        logger.error("Calculated homography matrix failed validation")
        return False
    
    # Save homography matrix using calibration manager
    HomographyMatrix = calculated_homography
    if calibration_manager.save_homography_matrix(HomographyMatrix):
        logger.info("Homography matrix saved successfully")
        CALIBRATION_NEEDED = False
        return True
    else:
        logger.error("Failed to save homography matrix")
        return False

async def perform_sensitivity_mapping(websocket):
    """Generate sensitivity mapping between cameras using buffered approach"""
    global sensitivityMapNeeded
    
    if not sensitivityMapNeeded:
        return True
        
    if not await start_remote_camera(websocket):
        return False
        
    print("Performing sensitivity mapping")
    
    # Start buffering on slave
    if not await start_frame_buffering(websocket):
        logger.error("Failed to start frame buffering for sensitivity mapping")
        return False
    
    local_frames = []
    
    # Capture all sensitivity frames
    for i in range(NUMBER_OF_SENSITIVITY_FRAMES):
        local_frame = localCamera.capture_array()
        local_frames.append(local_frame)
        
        # Request slave to capture and buffer frame
        if not await capture_buffered_frame(websocket):
            logger.error(f"Failed to capture buffered sensitivity frame {i}")
            return False
    
    # Transfer all buffered frames from slave (while buffering is still active)
    remote_frames = await transfer_all_buffered_frames(websocket)
    
    # Now stop buffering
    if not await stop_frame_buffering(websocket):
        logger.error("Failed to stop frame buffering for sensitivity mapping")
        return False
    
    if len(remote_frames) != len(local_frames):
        logger.error(f"Sensitivity frame count mismatch: local={len(local_frames)}, remote={len(remote_frames)}")
        return False
    
    # Generate sensitivity map using the mapper
    global Sensitivity_Map, sensitivityMapNeeded
    calculated_sensitivity_map = sensitivity_mapper.generate_sensitivity_map_from_raw_frames(
        local_frames, remote_frames, HomographyMatrix
    )
    
    if calculated_sensitivity_map is None:
        logger.error("Failed to generate sensitivity map")
        return False
    
    # Validate the calculated sensitivity map
    if not sensitivity_mapper.validate_sensitivity_map(calculated_sensitivity_map):
        logger.error("Calculated sensitivity map failed validation")
        return False
    
    # Save sensitivity map using calibration manager
    Sensitivity_Map = calculated_sensitivity_map
    if calibration_manager.save_sensitivity_map(Sensitivity_Map):
        logger.info("Sensitivity map saved successfully")
        sensitivityMapNeeded = False
        return True
    else:
        logger.error("Failed to save sensitivity map")
        return False

async def perform_detection_sequence(websocket):
    """Main detection sequence with LED flashing and buffered frame transfer"""
    logger.info("Starting detection sequence with buffered frame transfer")
    
    try:
        # Start buffering on slave
        if not await start_frame_buffering(websocket):
            logger.error("Failed to start frame buffering")
            return False
        
        # Buffer to store local frames
        local_frames = []
        
		# Turn on LED
        await send_command_with_retry(websocket, {'action': 'LED_ON'})
        time.sleep(0.5)		
        
        # Capture all frames first (buffered)
        for i in range(NUMBER_OF_FRAMES):
            logger.info(f"Capturing frame {i+1}/{NUMBER_OF_FRAMES}")

            # Capture local frame and store in buffer
            local_frame = localCamera.capture_array()
            local_frames.append(local_frame)
            
            # Request slave to capture and buffer frame
            if not await capture_buffered_frame(websocket):
                logger.error(f"Failed to capture buffered frame {i+1}")
                return False
            
            logger.info(f"Buffered frame {i+1}/{NUMBER_OF_FRAMES}")
        
        # Turn off LED after all captures
        await send_command_with_retry(websocket, {'action': 'LED_OFF'})
        
        # Transfer all buffered frames from slave (while buffering is still active)
        logger.info("Transferring all buffered frames from slave")
        remote_frames = await transfer_all_buffered_frames(websocket)
        
        # Now stop buffering on slave
        if not await stop_frame_buffering(websocket):
            logger.error("Failed to stop frame buffering")
            return False
        
        if len(remote_frames) != len(local_frames):
            logger.error(f"Frame count mismatch: local={len(local_frames)}, remote={len(remote_frames)}")
            return False
        
        # Process all frame pairs
        logger.info("Processing all captured frame pairs")
        for i, (local_frame, remote_frame) in enumerate(zip(local_frames, remote_frames)):
            # Align and process images
            aligned_local = align_fromHomography(local_frame, HomographyMatrix)
            cv2.imwrite(f'RemoteImage{i}.jpg', remote_frame)
            cv2.imwrite(f'LocalImageTest{i}.jpg', aligned_local)

            # Perform difference detection
            difference_image = performDifferenceIdentity(aligned_local, remote_frame)
            cv2.imwrite(f'DifferenceImage{i}.jpg', difference_image)
            
            logger.info(f"Processed frame {i+1}/{NUMBER_OF_FRAMES}, shape: {remote_frame.shape}")
        
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