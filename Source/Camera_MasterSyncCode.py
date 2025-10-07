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
from collections import namedtuple
from typing import Optional

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

# Frame buffer for decoupling capture from transfer
FrameData = namedtuple('FrameData', ['frame_id', 'data', 'timestamp'])
frame_buffer_queue = asyncio.Queue(maxsize=30)  # Buffer up to 30 frames
frame_receiver_task = None
frame_id_counter = 0
pending_frame_ids = set()  # Track frames we're waiting for
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

async def continuous_frame_receiver(websocket):
    """Background task that continuously receives frames and buffers them"""
    logger.info("Starting continuous frame receiver")
    
    try:
        while True:
            # Wait for frame data to arrive
            full_data = bytearray()
            frame_id = None
            
            # First message should be frame metadata
            try:
                metadata_msg = await websocket.recv()
                if isinstance(metadata_msg, str):
                    metadata = json.loads(metadata_msg)
                    frame_id = metadata.get('frame_id')
                    await websocket.send("OK")
                else:
                    # If it's binary data, it might be the old protocol
                    logger.warning("Received unexpected binary data as first message")
                    continue
            except json.JSONDecodeError:
                logger.warning("Failed to parse frame metadata")
                continue
            
            # Now receive the actual frame data
            while True:
                chunk = await websocket.recv()
                if chunk == b"END":
                    break
                full_data.extend(chunk)
                await websocket.send("OK")
            
            # Deserialize the frame data
            buffer = io.BytesIO(full_data)
            buffer.seek(0)
            frame_data = np.load(buffer)
            frame_data = np.fliplr(frame_data)
            
            # Create frame object with metadata
            frame_obj = FrameData(
                frame_id=frame_id,
                data=frame_data,
                timestamp=time.time()
            )
            
            # Add to buffer queue (non-blocking to avoid deadlock)
            try:
                frame_buffer_queue.put_nowait(frame_obj)
                logger.debug(f"Buffered frame {frame_id}")
                
                # Remove from pending set if it was there
                if frame_id in pending_frame_ids:
                    pending_frame_ids.discard(frame_id)
                    
            except asyncio.QueueFull:
                logger.warning("Frame buffer queue is full, dropping oldest frame")
                try:
                    # Drop oldest frame to make room
                    frame_buffer_queue.get_nowait()
                    frame_buffer_queue.put_nowait(frame_obj)
                except asyncio.QueueEmpty:
                    pass
                    
    except ConnectionClosed:
        logger.info("Frame receiver stopped - connection closed")
    except Exception as e:
        logger.error(f"Error in continuous frame receiver: {e}")
    finally:
        logger.info("Continuous frame receiver task ended")

async def start_frame_receiver(websocket):
    """Start the background frame receiver task"""
    global frame_receiver_task
    
    if frame_receiver_task is None or frame_receiver_task.done():
        frame_receiver_task = asyncio.create_task(continuous_frame_receiver(websocket))
        logger.info("Started frame receiver task")
    
    return frame_receiver_task

async def stop_frame_receiver():
    """Stop the background frame receiver task"""
    global frame_receiver_task
    
    if frame_receiver_task and not frame_receiver_task.done():
        frame_receiver_task.cancel()
        try:
            await frame_receiver_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped frame receiver task")
    
    frame_receiver_task = None

async def clear_frame_buffer():
    """Clear all frames from the buffer queue"""
    cleared_count = 0
    try:
        while True:
            frame_buffer_queue.get_nowait()
            cleared_count += 1
    except asyncio.QueueEmpty:
        pass
    
    if cleared_count > 0:
        logger.info(f"Cleared {cleared_count} frames from buffer")
    
    # Also clear pending frame IDs
    pending_frame_ids.clear()

async def get_buffer_status():
    """Get current buffer status for debugging"""
    buffer_size = frame_buffer_queue.qsize()
    pending_count = len(pending_frame_ids)
    
    status = {
        'buffer_size': buffer_size,
        'pending_frames': pending_count,
        'pending_ids': list(pending_frame_ids)
    }
    
    logger.debug(f"Buffer status: {status}")
    return status

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

async def trigger_remote_capture(websocket, frame_id):
    """Send capture trigger command with frame ID and return immediately"""
    global pending_frame_ids
    
    try:
        command = {'action': 'capture_buffered', 'frame_id': frame_id}
        await send_command_with_retry(websocket, command)
        
        # Wait for acknowledgment that capture was triggered
        response = await websocket.recv()
        result = json.loads(response)
        
        if result.get('status') == 'capture_triggered':
            pending_frame_ids.add(frame_id)
            logger.debug(f"Capture triggered for frame {frame_id}")
            return True
        else:
            logger.warning(f"Capture trigger failed: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error triggering remote capture: {e}")
        raise

async def get_frame_from_buffer(frame_id, timeout=10.0):
    """Retrieve a specific frame from the buffer queue"""
    start_time = time.time()
    
    # First check if frame is already in buffer
    temp_frames = []
    
    while time.time() - start_time < timeout:
        try:
            # Get frame from buffer with short timeout
            frame_obj = await asyncio.wait_for(frame_buffer_queue.get(), timeout=0.1)
            
            if frame_obj.frame_id == frame_id:
                # Found our frame! Put back any others we took out
                for temp_frame in temp_frames:
                    await frame_buffer_queue.put(temp_frame)
                return frame_obj.data
            else:
                # Not our frame, keep it for later
                temp_frames.append(frame_obj)
                
        except asyncio.TimeoutError:
            # No frame available right now, continue waiting
            continue
    
    # Timeout reached, put back all frames we took out
    for temp_frame in temp_frames:
        await frame_buffer_queue.put(temp_frame)
    
    # Remove from pending set since we failed to get it
    pending_frame_ids.discard(frame_id)
    
    raise TimeoutError(f"Frame {frame_id} not received within {timeout} seconds")

async def capture_with_buffer(websocket, frame_id):
    """Trigger capture and retrieve frame using buffer system"""
    # Trigger the capture
    success = await trigger_remote_capture(websocket, frame_id)
    if not success:
        raise RuntimeError(f"Failed to trigger capture for frame {frame_id}")
    
    # Retrieve the frame from buffer
    return await get_frame_from_buffer(frame_id)

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
    """Perform homography calibration between local and remote cameras using buffered capture"""
    global CALIBRATION_NEEDED, HomographyMatrix, frame_id_counter
    
    if not CALIBRATION_NEEDED:
        return True
        
    print("Performing homography calibration")
    local_frames = []
    remote_frames = []
    
    try:
        # Start the frame receiver task
        await clear_frame_buffer()  # Clear any stale frames
        await start_frame_receiver(websocket)
        
        for i in range(NUMBER_OF_CALIBRATION_FRAMES):
            # Generate unique frame ID
            frame_id = f"cal_frame_{frame_id_counter}_{i}"
            frame_id_counter += 1
            
            # Capture frames
            local_frame = localCamera.capture_array()
            
            try:
                remote_frame = await capture_with_buffer(websocket, frame_id)
            except (TimeoutError, RuntimeError) as e:
                logger.warning(f"Buffered capture failed for calibration frame {i}, using direct method: {e}")
                remote_frame = await send_command_and_receive_data(websocket, {'action': 'capture'})
            
            print(f"Frame {i} of {NUMBER_OF_CALIBRATION_FRAMES} captured")
            cv2.imwrite(f'remoteCalImg{i}.jpg', remote_frame)
            cv2.imwrite(f'localCalImg{i}.jpg', local_frame)
            
            if i >= FIRST_CALIBRATION_FRAME:
                local_frames.append(local_frame)
                remote_frames.append(remote_frame)
    
    finally:
        # Stop frame receiver
        await stop_frame_receiver()
    
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
    """Main detection sequence with LED flashing and error handling using buffered capture"""
    global frame_id_counter
    logger.info("Starting detection sequence")
    
    try:
        # Start the frame receiver task if not already running
        await clear_frame_buffer()  # Clear any stale frames
        await start_frame_receiver(websocket)
        
        for i in range(NUMBER_OF_FRAMES):
            logger.info(f"Processing frame {i+1}/{NUMBER_OF_FRAMES}")
            
            # Turn on LED
            await send_command_with_retry(websocket, {'action': 'LED_ON'})
            time.sleep(0.5)
            
            # Generate unique frame ID
            frame_id = f"frame_{frame_id_counter}_{i}"
            frame_id_counter += 1
            
            # Capture local frame immediately
            local_frame = localCamera.capture_array()
            
            # Trigger remote capture (non-blocking) and get frame from buffer
            try:
                remote_frame = await capture_with_buffer(websocket, frame_id)
            except (TimeoutError, RuntimeError) as e:
                logger.error(f"Failed to capture remote frame {i}: {e}")
                # Fallback to old method if buffered capture fails
                logger.info("Falling back to direct capture method")
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
    finally:
        # Stop the frame receiver when done
        await stop_frame_receiver()

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
            # Stop frame receiver task
            await stop_frame_receiver()
            
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