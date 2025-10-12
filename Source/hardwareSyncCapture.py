#!/usr/bin/env python3
"""
Hardware Synchronized Dual Camera Capture using rpicam-vid --sync
Uses the server/client sync feature for precise hardware synchronization
with optional homography correction for image alignment

Author: Matthew Boillat
Date: October 2025
"""

import cv2
import numpy as np
import subprocess
import time
import signal
import sys
import logging
import threading
from typing import Optional, Tuple
from queue import Queue, Empty
import tempfile
import os
import socket
from CalibrationFileManager import CalibrationFileManager
from alignImages import align_fromHomography
from HomographyCalibrator import calculate_homography_from_frames

class HardwareSyncDualCamera:
    """
    Hardware-synchronized dual camera capture using rpicam-vid --sync feature
    """
    
    def __init__(self, 
                 width: int = 1920,
                 height: int = 1080,
                 framerate: int = 30,
                 bitrate: int = 10000000,
                 buffer_size: int = 80,
                 flip_camera0: bool = True,
                 enable_homography: bool = True,
                 homography_file: str = "wallCalibration_image_1080.pickle",
                 correct_camera1_to_camera0: bool = True,
                 auto_calibrate: bool = True,
                 calibration_frames: int = 15,
                 calibration_first_frame: int = 1,
                 debug_mode: bool = False,
                 debug_frame_limit: int = 30,
                 save_output: bool = False,
                 output_directory: str = "captured_frames",
                 simple_output: bool = True):
        """
        Initialize hardware synchronized capture
        
        Args:
            width: Video width (default 1920 for 1080p)
            height: Video height (default 1080 for 1080p)
            framerate: Frames per second
            bitrate: Video bitrate for H.264 encoding
            buffer_size: Frame buffer size
            flip_camera0: Flip camera 0 frames horizontally (left/right)
            enable_homography: Enable homography correction
            homography_file: Homography matrix file
            correct_camera1_to_camera0: If True, correct camera 1 to match camera 0 (typical)
                                      If False, correct camera 0 to match camera 1
            auto_calibrate: If True, automatically calibrate homography if file not found
            calibration_frames: Number of frames to capture for auto-calibration
            calibration_first_frame: Index of first frame to use for calibration calculation
            debug_mode: If True, limit capture to a specific number of frames for testing
            debug_frame_limit: Number of frames to capture in debug mode (default 30)
            save_output: If True, save captured frames to disk
            output_directory: Directory to save captured frames (default: "captured_frames")
            simple_output: If True, use simplified status output (frame count only on 10th interval)
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.bitrate = bitrate
        self.buffer_size = buffer_size
        self.flip_camera0 = flip_camera0
        self.enable_homography = enable_homography
        self.correct_camera1_to_camera0 = correct_camera1_to_camera0
        self.auto_calibrate = auto_calibrate
        self.calibration_frames = calibration_frames
        self.calibration_first_frame = calibration_first_frame
        self.homography_file = homography_file
        self.debug_mode = debug_mode
        self.debug_frame_limit = debug_frame_limit
        self.save_output = save_output
        self.output_directory = output_directory
        self.simple_output = simple_output
        
        # Setup logging early - needed for all subsequent operations
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Create output directory if saving is enabled
        if self.save_output:
            os.makedirs(self.output_directory, exist_ok=True)
            self.logger.info(f"Output directory created: {self.output_directory}")
        
        # Frame storage for batch saving
        self.accumulated_frames = []
        
        # Debug mode tracking
        self.debug_frames_captured = 0
        
        # Homography support
        self.homography_matrix: Optional[np.ndarray] = None
        self.calibration_manager: Optional[CalibrationFileManager] = None
        self.homography_loaded = False
        self.calibration_needed = False
        
        # Initialize homography if enabled
        if self.enable_homography:
            self._initialize_homography(homography_file)
        
        # TCP streaming configuration (replaces named pipes)
        # Find available ports automatically
        self.server_tcp_port, self.client_tcp_port = self._find_available_tcp_ports()
        self.server_tcp_url = f"tcp://127.0.0.1:{self.server_tcp_port}"
        self.client_tcp_url = f"tcp://127.0.0.1:{self.client_tcp_port}"
        
        self.logger.info(f"🌐 TCP Streaming Configuration:")
        self.logger.info(f"   Server (Camera 0): {self.server_tcp_url}")
        self.logger.info(f"   Client (Camera 1): {self.client_tcp_url}")
        
        # Keep temp_dir for potential future use, but no longer create FIFOs
        self.temp_dir = tempfile.mkdtemp(prefix="sync_cameras_")
        
        # Process handles
        self.server_process: Optional[subprocess.Popen] = None
        self.client_process: Optional[subprocess.Popen] = None
        
        # OpenCV VideoCapture objects
        self.server_cap: Optional[cv2.VideoCapture] = None
        self.client_cap: Optional[cv2.VideoCapture] = None
        
        # Frame queues
        self.synchronized_queue = Queue(maxsize=buffer_size)
        
        # Threading
        self.capture_thread = None
        self.running = False
        
        # Statistics
        self.stats = {
            'server_frames': 0,
            'client_frames': 0,
            'synchronized_pairs': 0,
            'dropped_frames': 0,
            'homography_corrections': 0,
            'homography_failures': 0,
            'loop_times': [],  # List to store individual loop execution times
            'total_loop_time': 0.0,  # Cumulative time spent in capture loop
            'avg_loop_time': 0.0,  # Average loop execution time
            'min_loop_time': float('inf'),  # Minimum loop time recorded
            'max_loop_time': 0.0,  # Maximum loop time recorded
            'loop_count': 0  # Total number of loops executed
        }
        
        # Register cleanup
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _check_tcp_port_available(self, port: int) -> bool:
        """
        Check if a TCP port is available for use
        
        Args:
            port: Port number to check
            
        Returns:
            True if port is available, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False
    
    def _find_available_tcp_ports(self, start_port: int = 8000) -> Tuple[int, int]:
        """
        Find two consecutive available TCP ports
        
        Args:
            start_port: Starting port to search from
            
        Returns:
            Tuple of (server_port, client_port)
        """
        for port in range(start_port, start_port + 100, 2):  # Check even ports
            if (self._check_tcp_port_available(port) and 
                self._check_tcp_port_available(port + 1)):
                return port, port + 1
        
        # Fallback to default if no consecutive ports found
        self.logger.warning("⚠️  Could not find consecutive TCP ports, using defaults")
        return 8000, 8001
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("Shutdown signal received...")
        self.stop_capture()
        sys.exit(0)
    
    def _initialize_homography(self, homography_file: str):
        """
        Initialize homography correction by loading calibration matrices
        or setting up for auto-calibration
        
        Args:
            homography_file: Path to the homography calibration file
        """
        try:
            self.calibration_manager = CalibrationFileManager(homography_file)
            self.homography_matrix = self.calibration_manager.load_homography_matrix()
            
            if self.homography_matrix is not None:
                self.homography_loaded = True
                self.calibration_needed = False
                self.logger.info("✅ Homography matrix loaded successfully")
                self.logger.info(f"   Matrix shape: {self.homography_matrix.shape}")
                
                # Validate homography matrix
                if self.homography_matrix.shape != (3, 3):
                    self.logger.error("❌ Invalid homography matrix shape")
                    self.homography_loaded = False
                    self.calibration_needed = self.auto_calibrate
                    return
                
                # Check for reasonable values
                det = np.linalg.det(self.homography_matrix)
                if abs(det) < 1e-10:
                    self.logger.error("❌ Homography matrix appears to be singular")
                    self.homography_loaded = False
                    self.calibration_needed = self.auto_calibrate
                    return
                    
                self.logger.info(f"   Matrix determinant: {det:.6f}")
                
            else:
                self.logger.warning("⚠️  No homography matrix found")
                self.homography_loaded = False
                self.calibration_needed = self.auto_calibrate
                
                if self.auto_calibrate:
                    self.logger.info("🔧 Auto-calibration enabled - will calibrate on first capture")
                else:
                    self.logger.warning("❌ Auto-calibration disabled - alignment will be unavailable")
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize homography: {e}")
            self.homography_loaded = False
            self.calibration_needed = self.auto_calibrate
    
    def _apply_homography_correction(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply homography correction to a frame
        
        Args:
            frame: Input frame to correct
            
        Returns:
            Corrected frame, or original frame if correction fails
        """
        if not self.homography_loaded or self.homography_matrix is None:
            return frame
            
        try:
            # Apply homography transformation
            corrected_frame = align_fromHomography(frame, self.homography_matrix)
            
            if corrected_frame is not None:
                self.stats['homography_corrections'] += 1
                return corrected_frame
            else:
                self.stats['homography_failures'] += 1
                self.logger.warning("⚠️  Homography correction failed, using original frame")
                return frame
                
        except Exception as e:
            self.stats['homography_failures'] += 1
            self.logger.error(f"❌ Error applying homography: {e}")
            return frame
    
    def _save_frame_pair(self, frame_pair: dict, frame_number: int):
        """
        Accumulate synchronized frame pair in memory for later batch saving
        
        Args:
            frame_pair: Dictionary containing frame data
            frame_number: Current frame number for naming
        """
        try:
            # Generate timestamp for unique filenames
            timestamp = int(time.time() * 1000)  # milliseconds
            
            # Store frame data in memory for batch saving later
            frame_data = {
                'frame_number': frame_number,
                'timestamp': timestamp,
                'frame0': frame_pair['frame0'].copy(),  # Make a copy to avoid reference issues
                'frame1': frame_pair['frame1'].copy(),  # Make a copy to avoid reference issues
                'metadata': {
                    'Frame Number': frame_number,
                    'Timestamp': frame_pair['timestamp'],
                    'Hardware Synced': frame_pair['hardware_synced'],
                    'Homography Corrected': frame_pair['homography_corrected'],
                    'Corrected Camera': frame_pair.get('corrected_camera', 'None'),
                    'Debug Mode': frame_pair.get('debug_mode', False),
                    'Debug Frame Number': frame_pair.get('debug_frame_number', 'N/A') if frame_pair.get('debug_mode') else 'N/A'
                }
            }
            
            self.accumulated_frames.append(frame_data)
            
            # Log every 10th frame to show progress
            if frame_number % 10 == 0:
                self.logger.info(f"📁 Accumulated frame pair {frame_number} in memory ({len(self.accumulated_frames)} total)")
                
        except Exception as e:
            self.logger.error(f"❌ Failed to accumulate frame pair {frame_number}: {e}")

    def _save_accumulated_frames_to_disk(self):
        """
        Save all accumulated frames to disk in batch
        """
        if not self.save_output or not self.accumulated_frames:
            return
            
        self.logger.info(f"💾 Saving {len(self.accumulated_frames)} accumulated frames to disk...")
        
        saved_count = 0
        failed_count = 0
        
        for frame_data in self.accumulated_frames:
            try:
                frame_number = frame_data['frame_number']
                timestamp = frame_data['timestamp']
                
                # Save camera 0 frame
                frame0_filename = f"camera0_frame_{frame_number:06d}_{timestamp}.jpg"
                frame0_path = os.path.join(self.output_directory, frame0_filename)
                cv2.imwrite(frame0_path, frame_data['frame0'])
                
                # Save camera 1 frame  
                frame1_filename = f"camera1_frame_{frame_number:06d}_{timestamp}.jpg"
                frame1_path = os.path.join(self.output_directory, frame1_filename)
                cv2.imwrite(frame1_path, frame_data['frame1'])
                
                # Save metadata as text file
                metadata_filename = f"metadata_frame_{frame_number:06d}_{timestamp}.txt"
                metadata_path = os.path.join(self.output_directory, metadata_filename)
                
                with open(metadata_path, 'w') as f:
                    for key, value in frame_data['metadata'].items():
                        f.write(f"{key}: {value}\n")
                    f.write(f"Camera 0 File: {frame0_filename}\n")
                    f.write(f"Camera 1 File: {frame1_filename}\n")
                
                saved_count += 1
                
                # Show progress every 50 saves
                if saved_count % 50 == 0:
                    self.logger.info(f"� Saved {saved_count}/{len(self.accumulated_frames)} frames...")
                    
            except Exception as e:
                failed_count += 1
                self.logger.error(f"❌ Failed to save frame {frame_data['frame_number']}: {e}")
        
        self.logger.info(f"✅ Batch save completed: {saved_count} saved, {failed_count} failed")
        
        # Clear accumulated frames to free memory
        self.accumulated_frames.clear()

    def save_frames_now(self):
        """
        Manually trigger saving of accumulated frames to disk
        Useful for periodic saves during long captures
        """
        if self.save_output and self.accumulated_frames:
            self.logger.info(f"🔄 Manual save triggered for {len(self.accumulated_frames)} frames")
            self._save_accumulated_frames_to_disk()

    def _perform_auto_calibration(self) -> bool:
        """
        Perform automatic homography calibration by capturing frames
        
        Returns:
            True if calibration successful, False otherwise
        """
        if not self.calibration_needed:
            return True
            
        self.logger.info("🔧 Starting automatic homography calibration...")
        self.logger.info(f"   Capturing {self.calibration_frames} frames for calibration")
        
        try:
            # Temporarily start capture without homography correction
            original_homography_loaded = self.homography_loaded
            self.homography_loaded = False  # Disable correction during calibration
            
            # Open video streams from TCP URLs for calibration
            server_cap = cv2.VideoCapture(self.server_tcp_url)
            client_cap = cv2.VideoCapture(self.client_tcp_url)
            
            if not server_cap.isOpened() or not client_cap.isOpened():
                self.logger.error("❌ Failed to open TCP video streams for calibration")
                return False
            
            camera0_frames = []
            camera1_frames = []
            
            # Capture calibration frames
            for i in range(self.calibration_frames):
                ret_server, frame_server = server_cap.read()
                ret_client, frame_client = client_cap.read()
                
                if not ret_server or not ret_client:
                    self.logger.error(f"❌ Failed to capture calibration frame {i+1}")
                    server_cap.release()
                    client_cap.release()
                    return False
                
                # Apply horizontal flip to camera 0 if enabled (before calibration)
                if self.flip_camera0:
                    frame_server = cv2.flip(frame_server, 1)
                
                camera0_frames.append(frame_server)
                camera1_frames.append(frame_client)
                
                self.logger.info(f"   📸 Captured calibration frame {i+1}/{self.calibration_frames}")
                
                # Small delay between captures
                time.sleep(0.1)
            
            server_cap.release()
            client_cap.release()
            
            self.logger.info("🔧 Calculating homography matrix...")
            
            # Calculate homography using the module function
            if self.correct_camera1_to_camera0:
                # Calculate homography to transform camera 1 to camera 0
                homography_matrix = calculate_homography_from_frames(
                    camera1_frames,  # Source frames (to be transformed)
                    camera0_frames,  # Target frames (reference)
                    calibration_frames=self.calibration_frames,
                    first_calibration_frame=self.calibration_first_frame
                )
            else:
                # Calculate homography to transform camera 0 to camera 1
                homography_matrix = calculate_homography_from_frames(
                    camera0_frames,  # Source frames (to be transformed)
                    camera1_frames,  # Target frames (reference)
                    calibration_frames=self.calibration_frames,
                    first_calibration_frame=self.calibration_first_frame
                )
            
            if homography_matrix is not None:
                # Save the calculated homography
                if self.calibration_manager.save_homography_matrix(homography_matrix):
                    self.homography_matrix = homography_matrix
                    self.homography_loaded = True
                    self.calibration_needed = False
                    
                    self.logger.info("✅ Auto-calibration successful!")
                    self.logger.info(f"   Homography matrix saved to: {self.homography_file}")
                    self.logger.info(f"   Matrix determinant: {np.linalg.det(homography_matrix):.6f}")
                    return True
                else:
                    self.logger.error("❌ Failed to save calibrated homography matrix")
                    return False
            else:
                self.logger.error("❌ Auto-calibration failed - could not calculate homography")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error during auto-calibration: {e}")
            return False
        finally:
            # Restore original homography state
            self.homography_loaded = original_homography_loaded
    
    def _build_camera_command(self, camera_id: int, is_server: bool, tcp_url: str) -> list:
        """
        Build rpicam-vid command with hardware sync using TCP streaming
        
        Args:
            camera_id: Camera index (0 or 1)
            is_server: True for server, False for client
            tcp_url: TCP URL for streaming output
            
        Returns:
            Command list
        """
        cmd = [
            'rpicam-vid',
            '--camera', str(camera_id),
            '-t', '0',  # Run indefinitely
            '-n',  # No preview
            '--width', str(self.width),
            '--height', str(self.height),
            '--framerate', str(self.framerate),
            '--bitrate', str(self.bitrate),
            '--codec', 'libav',
            '--libav-format', 'h264',
            '--libav-audio', '0',  # Disable audio for TCP streaming
            '-o', tcp_url
        ]
        
        # Add sync parameter
        if is_server:
            cmd.extend(['--sync', 'server'])
        else:
            cmd.extend(['--sync', 'client'])
            
        return cmd
    
    def start_capture(self) -> bool:
        """
        Start hardware synchronized capture
        
        Returns:
            True if successful
        """
        self.logger.info("Starting hardware synchronized dual camera capture...")
        self.running = True
        
        try:
            # Start server camera (camera 0) - TCP streaming
            server_cmd = self._build_camera_command(0, True, self.server_tcp_url)
            self.logger.info(f"Starting server camera: {' '.join(server_cmd)}")
            self.server_process = subprocess.Popen(
                server_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Start client camera (camera 1) - TCP streaming
            client_cmd = self._build_camera_command(1, False, self.client_tcp_url)
            self.logger.info(f"Starting client camera: {' '.join(client_cmd)}")
            self.client_process = subprocess.Popen(
                client_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Give processes time to start
            time.sleep(3)
            
            # Check if processes are running
            if (self.server_process.poll() is not None or 
                self.client_process.poll() is not None):
                self.logger.error("One or both camera processes failed to start")
                return False
            
            # Perform auto-calibration if needed
            if self.calibration_needed:
                self.logger.info("🔧 Performing automatic homography calibration...")
                if not self._perform_auto_calibration():
                    self.logger.error("❌ Auto-calibration failed")
                    if not self.auto_calibrate:
                        return False
                    else:
                        self.logger.warning("⚠️  Continuing without homography correction")
            
            # Start capture thread
            self.capture_thread = threading.Thread(target=self._capture_synchronized_frames, daemon=True)
            self.capture_thread.start()
            
            self.logger.info("Hardware synchronized capture started successfully!")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start capture: {e}")
            self.stop_capture()
            return False
    
    def _capture_synchronized_frames(self):
        """
        Capture synchronized frames using OpenCV VideoCapture with TCP streaming
        """
        try:
            # Wait for TCP streams to be available
            self.logger.info("Waiting for TCP streams to be available...")
            time.sleep(5)  # Give more time for TCP streams to establish
            
            # Open video streams from TCP URLs with retry logic
            self.logger.info("Opening TCP video streams...")
            
            # Retry opening streams up to 3 times
            max_retries = 3
            for attempt in range(max_retries):
                # Open server stream with TCP
                self.server_cap = cv2.VideoCapture(self.server_tcp_url)
                if self.server_cap.isOpened():
                    self.logger.info(f"✅ Server TCP stream opened: {self.server_tcp_url}")
                    break
                else:
                    self.logger.warning(f"⚠️  Attempt {attempt + 1}/{max_retries}: Failed to open server TCP stream")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        self.logger.error(f"❌ Failed to open server TCP stream after {max_retries} attempts: {self.server_tcp_url}")
                        return
            
            # Open client stream with TCP
            for attempt in range(max_retries):
                self.client_cap = cv2.VideoCapture(self.client_tcp_url)
                if self.client_cap.isOpened():
                    self.logger.info(f"✅ Client TCP stream opened: {self.client_tcp_url}")
                    break
                else:
                    self.logger.warning(f"⚠️  Attempt {attempt + 1}/{max_retries}: Failed to open client TCP stream")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        self.logger.error(f"❌ Failed to open client TCP stream after {max_retries} attempts: {self.client_tcp_url}")
                        return
            
            # Configure minimal buffering for better synchronization
            self.server_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.client_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Additional TCP-specific optimizations
            # Set timeout for read operations (in milliseconds)
            self.server_cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            self.client_cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            
            self.logger.info("🌐 TCP video streams configured successfully")
            
            while self.running:
                # Start timing the loop iteration
                loop_start_time = time.time()
                
                # Read frames from both cameras
                # Since they're hardware synchronized, we can read them sequentially
                
                ret_server, frame_server = self.server_cap.read()
                ret_client, frame_client = self.client_cap.read()
                
                if not ret_server or not ret_client:
                    # End of stream or error
                    if self.running:
                        self.logger.warning("Failed to read from one or both cameras")
                    break
                
                # Flip camera 0 (server) frame horizontally if requested
                if self.flip_camera0:
                    frame_server = cv2.flip(frame_server, 1)  # 1 = horizontal flip
                
                # Apply homography correction to only one camera if enabled
                if self.enable_homography and self.homography_loaded:
                    if self.correct_camera1_to_camera0:
                        # Correct camera 1 to match camera 0's perspective (typical case)
                        frame_client_corrected = self._apply_homography_correction(frame_client)
                        frame_client = frame_client_corrected
                        # Camera 0 remains as reference (uncorrected)
                    else:
                        # Correct camera 0 to match camera 1's perspective (less common)
                        frame_server_corrected = self._apply_homography_correction(frame_server)
                        frame_server = frame_server_corrected
                        # Camera 1 remains as reference (uncorrected)
                
                # Update statistics
                self.stats['server_frames'] += 1
                self.stats['client_frames'] += 1
                
                # Update debug mode counter
                self.debug_frames_captured += 1
                
                # Create synchronized frame pair with one camera corrected
                timestamp = time.time() * 1000
                corrected_camera = 1 if self.correct_camera1_to_camera0 else 0
                frame_pair = {
                    'frame0': frame_server,  # Server camera (camera 0) - flipped if enabled
                    'frame1': frame_client,  # Client camera (camera 1)
                    'timestamp': timestamp,
                    'hardware_synced': True,
                    'homography_corrected': self.enable_homography and self.homography_loaded,
                    'corrected_camera': corrected_camera if (self.enable_homography and self.homography_loaded) else None,
                    'debug_mode': self.debug_mode,
                    'debug_frame_number': self.debug_frames_captured if self.debug_mode else None
                }
                
                # Save frames to disk if enabled
                if self.save_output:
                    self._save_frame_pair(frame_pair, self.debug_frames_captured)
                
                # Add to queue
                try:
                    self.synchronized_queue.put_nowait(frame_pair)
                    self.stats['synchronized_pairs'] += 1
                except:
                    # Queue full, drop oldest frame
                    try:
                        self.synchronized_queue.get_nowait()
                        self.synchronized_queue.put_nowait(frame_pair)
                        self.stats['dropped_frames'] += 1
                    except:
                        pass
                
                # Calculate and record loop timing statistics
                loop_end_time = time.time()
                loop_duration = loop_end_time - loop_start_time
                
                # Update timing statistics
                self.stats['loop_times'].append(loop_duration)
                self.stats['total_loop_time'] += loop_duration
                self.stats['loop_count'] += 1
                self.stats['avg_loop_time'] = self.stats['total_loop_time'] / self.stats['loop_count']
                self.stats['min_loop_time'] = min(self.stats['min_loop_time'], loop_duration)
                self.stats['max_loop_time'] = max(self.stats['max_loop_time'], loop_duration)
                
                # Keep only the last 1000 loop times to prevent memory growth
                if len(self.stats['loop_times']) > 1000:
                    self.stats['loop_times'].pop(0)
                
                # Check for debug mode completion
                if self.debug_mode and self.debug_frames_captured >= self.debug_frame_limit:
                    self.logger.info(f"🔍 Debug mode: Captured {self.debug_frames_captured} frames, stopping capture")
                    self.running = False
                    break
        
        except Exception as e:
            if self.running:
                self.logger.error(f"Error in synchronized capture: {e}")
        finally:
            # Cleanup video captures
            if self.server_cap:
                self.server_cap.release()
            if self.client_cap:
                self.client_cap.release()
    
    def get_synchronized_frames(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Get the next synchronized frame pair
        
        Args:
            timeout: Maximum wait time
            
        Returns:
            Dictionary with synchronized frames
        """
        try:
            return self.synchronized_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def stop_capture(self):
        """Stop synchronized capture"""
        self.logger.info("Stopping capture...")
        self.running = False
        
        # Save accumulated frames to disk before cleanup
        if self.save_output and self.accumulated_frames:
            self.logger.info("💾 Saving accumulated frames before shutdown...")
            self._save_accumulated_frames_to_disk()
        
        # Stop processes
        for process in [self.server_process, self.client_process]:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    try:
                        process.kill()
                    except:
                        pass
        
        # Wait for capture thread
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5)
        
        # Cleanup temporary directory (no longer contains FIFOs)
        try:
            os.rmdir(self.temp_dir)
        except:
            pass
        
        self.logger.info("Capture stopped")
    
    def get_stats(self) -> dict:
        """Get capture statistics"""
        stats = self.stats.copy()
        stats.update({
            'homography_enabled': self.enable_homography,
            'homography_loaded': self.homography_loaded,
            'auto_calibrate_enabled': self.auto_calibrate,
            'calibration_needed': self.calibration_needed,
            'flip_camera0_enabled': self.flip_camera0,
            'debug_mode': self.debug_mode,
            'debug_frames_captured': self.debug_frames_captured if self.debug_mode else None,
            'debug_frame_limit': self.debug_frame_limit if self.debug_mode else None,
            'accumulated_frames_count': len(self.accumulated_frames) if self.save_output else None,
            'simple_output': self.simple_output,
            'avg_loop_time_ms': self.stats['avg_loop_time'] * 1000 if self.stats['loop_count'] > 0 else 0.0,
            'loop_count': self.stats['loop_count']
        })
        return stats
    
    def get_timing_stats(self) -> dict:
        """
        Get detailed timing statistics for capture loop performance
        
        Returns:
            Dictionary with timing analysis including averages, min/max, and recent performance
        """
        if self.stats['loop_count'] == 0:
            return {
                'loop_count': 0,
                'avg_loop_time_ms': 0.0,
                'min_loop_time_ms': 0.0,
                'max_loop_time_ms': 0.0,
                'total_loop_time_s': 0.0,
                'recent_avg_loop_time_ms': 0.0,
                'theoretical_max_fps': 0.0,
                'actual_fps_estimate': 0.0
            }
        
        # Calculate recent average (last 100 loops or all if fewer)
        recent_times = self.stats['loop_times'][-100:] if len(self.stats['loop_times']) > 100 else self.stats['loop_times']
        recent_avg = sum(recent_times) / len(recent_times) if recent_times else 0.0
        
        # Estimate actual FPS based on average loop time
        avg_time = self.stats['avg_loop_time']
        actual_fps = 1.0 / avg_time if avg_time > 0 else 0.0
        theoretical_max_fps = 1.0 / self.stats['min_loop_time'] if self.stats['min_loop_time'] != float('inf') else 0.0
        
        return {
            'loop_count': self.stats['loop_count'],
            'avg_loop_time_ms': self.stats['avg_loop_time'] * 1000,
            'min_loop_time_ms': self.stats['min_loop_time'] * 1000 if self.stats['min_loop_time'] != float('inf') else 0.0,
            'max_loop_time_ms': self.stats['max_loop_time'] * 1000,
            'total_loop_time_s': self.stats['total_loop_time'],
            'recent_avg_loop_time_ms': recent_avg * 1000,
            'theoretical_max_fps': theoretical_max_fps,
            'actual_fps_estimate': actual_fps
        }
    
    def get_homography_status(self) -> dict:
        """
        Get detailed homography status information
        
        Returns:
            Dictionary with homography configuration and status
        """
        status = {
            'homography_enabled': self.enable_homography,
            'homography_loaded': self.homography_loaded,
            'homography_matrix_available': self.homography_matrix is not None,
            'auto_calibrate_enabled': self.auto_calibrate,
            'calibration_needed': self.calibration_needed,
            'correct_camera1_to_camera0': self.correct_camera1_to_camera0,
            'corrected_camera': 1 if self.correct_camera1_to_camera0 else 0,
            'reference_camera': 0 if self.correct_camera1_to_camera0 else 1,
            'calibration_frames': self.calibration_frames,
            'calibration_first_frame': self.calibration_first_frame,
            'corrections_applied': self.stats.get('homography_corrections', 0),
            'correction_failures': self.stats.get('homography_failures', 0)
        }
        
        if self.homography_matrix is not None:
            status.update({
                'matrix_shape': self.homography_matrix.shape,
                'matrix_determinant': float(np.linalg.det(self.homography_matrix))
            })
        
        return status


def frame_difference_analysis(frame0: np.ndarray, frame1: np.ndarray) -> dict:
    """
    Analyze differences between hardware-synchronized frames
    """
    # Convert to grayscale
    gray0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    
    # Calculate difference
    diff = cv2.absdiff(gray0, gray1)
    
    # Statistics
    mean_diff = np.mean(diff)
    max_diff = np.max(diff)
    std_diff = np.std(diff)
    
    # Create binary mask
    threshold = mean_diff + 2 * std_diff
    diff_mask = (diff > threshold).astype(np.uint8) * 255
    
    # Find contours
    contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Calculate difference percentage
    diff_area = np.sum(diff_mask > 0)
    total_area = diff_mask.shape[0] * diff_mask.shape[1]
    diff_percentage = (diff_area / total_area) * 100
    
    return {
        'difference_image': diff,
        'difference_mask': diff_mask,
        'mean_difference': mean_diff,
        'max_difference': max_diff,
        'std_difference': std_diff,
        'difference_percentage': diff_percentage,
        'num_difference_regions': len(contours),
        'contours': contours,
        'hardware_synced': True
    }


def main():
    """Example usage of hardware synchronized capture with homography correction"""
    
    # Create hardware sync capture with 1080p resolution and homography correction
    capture = HardwareSyncDualCamera(
        width=1920,
        height=1080,
        framerate=15,  # Start with lower framerate
        bitrate=8000000,  # 8 Mbps for 1080p
        flip_camera0=False,  # Flip camera 0 frames horizontally
        enable_homography=False,  # Enable homography correction
        homography_file="wallCalibration_image_1080.pickle",
        correct_camera1_to_camera0=True,  # Correct camera 1 to match camera 0
        auto_calibrate=True,  # Enable auto-calibration if no homography file
        calibration_frames=15,  # Number of frames for calibration
        calibration_first_frame=1,  # First frame to use for calculation
        save_output=True,
        simple_output=True  # Set to True for simplified status output
    )
    
    try:
        # Display homography status
        homography_status = capture.get_homography_status()
        print("🔧 Homography Configuration:")
        for key, value in homography_status.items():
            status_icon = "✅" if value else "❌" if isinstance(value, bool) else "📊"
            print(f"   {status_icon} {key}: {value}")
        
        if homography_status['homography_loaded']:
            corrected_cam = homography_status['corrected_camera']
            reference_cam = homography_status['reference_camera']
            print(f"   🎯 Camera {corrected_cam} will be corrected to match Camera {reference_cam}")
        elif homography_status['auto_calibrate_enabled'] and homography_status['calibration_needed']:
            print(f"   🔧 Auto-calibration will be performed using {homography_status['calibration_frames']} frames")
        else:
            print(f"   ⚠️  No homography correction will be applied")
        
        if not capture.start_capture():
            print("❌ Failed to start hardware synchronized capture")
            return
        
        print("\n✅ Hardware synchronized capture started!")
        if homography_status['homography_loaded']:
            print("🎯 Homography correction ENABLED - one camera will be aligned")
        else:
            print("⚠️  Homography correction DISABLED - frames may not be aligned")
        print("🔄 Processing synchronized frames...")
        print("Press Ctrl+C to stop")
        
        frame_count = 0
        
        while True:
            # Get hardware synchronized frames (now with single-camera homography correction)
            frame_pair = capture.get_synchronized_frames(timeout=0.1)
            
            if frame_pair is None:
                print("⚠️  No synchronized frames available")
                continue
            
            frame_count += 1
            
            # Perform difference analysis on aligned frames
            #analysis = frame_difference_analysis(
            #    frame_pair['frame0'],  # Camera 0 (reference or corrected) + flipped
            #    frame_pair['frame1']   # Camera 1 (corrected or reference)
            #)
            
            # Print results
            if frame_count % 10 == 0:
                if capture.simple_output:
                    # Simplified output: just frame count
                    print(f"Frame {frame_count}")
                else:
                    # Detailed output: full status information
                    corrected_camera = frame_pair.get('corrected_camera', 'None')
                    print(f"\n📊 Frame {frame_count} (Hardware Synced + Camera {corrected_camera} Corrected):")
                    print(f"   📊 Mean diff: {analysis['mean_difference']:.2f}")
                    print(f"   🎯 Diff area: {analysis['difference_percentage']:.2f}%")
                    print(f"   📍 Regions: {analysis['num_difference_regions']}")
                    print(f"   🔧 Homography: {'✅' if frame_pair.get('homography_corrected', False) else '❌'}")
                    
                    # Statistics including homography and timing
                    stats = capture.get_stats()
                    timing_stats = capture.get_timing_stats()
                    print(f"   📈 Total pairs: {stats['synchronized_pairs']}")
                    print(f"   🎯 Homography corrections: {stats['homography_corrections']}")
                    print(f"   ❌ Dropped: {stats['dropped_frames']}")
                    print(f"   ⚠️  Homography failures: {stats['homography_failures']}")
                    print(f"   ⏱️  Avg loop time: {timing_stats['avg_loop_time_ms']:.2f}ms")
                    print(f"   ⚡ Est. FPS: {timing_stats['actual_fps_estimate']:.1f}")
            
            # Status indicator (only for detailed output)
            if not capture.simple_output:
                status = "🔴" if analysis['difference_percentage'] > 1.0 else "🟢"
                print(f"{status}", end="", flush=True)
                
                if frame_count % 50 == 0:
                    print()  # New line
    
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        capture.stop_capture()


def debug_mode_example():
    """Example usage of debug mode with limited frame capture"""
    
    print("🔍 Debug Mode Example - Capturing only 30 frames")
    
    # Create hardware sync capture in debug mode
    capture = HardwareSyncDualCamera(
        width=1280,
        height=720,
        framerate=10,  # Lower framerate for testing
        bitrate=4000000,  # 4 Mbps for 720p
        flip_camera0=True,
        enable_homography=True,
        homography_file="wallCalibration_image_720.pickle",
        correct_camera1_to_camera0=True,
        auto_calibrate=True,
        calibration_frames=15,
        calibration_first_frame=1,
        debug_mode=True,  # Enable debug mode
        debug_frame_limit=30,  # Capture only 30 frames
        save_output=True,  # Save frames to disk
        output_directory="debug_capture_frames",  # Save to this directory
        simple_output=True  # Use simplified output for debug mode
    )
    
    try:
        # Display configuration
        print("🔧 Debug Configuration:")
        stats = capture.get_stats()
        print(f"   🔍 Debug Mode: {'✅' if stats['debug_mode'] else '❌'}")
        print(f"   📊 Frame Limit: {stats['debug_frame_limit']}")
        print(f"   🎥 Resolution: {capture.width}x{capture.height}")
        print(f"   📸 Framerate: {capture.framerate} fps")
        print(f"   💾 Save Output: {'✅' if capture.save_output else '❌'}")
        print(f"   📄 Simple Output: {'✅' if capture.simple_output else '❌'}")
        if capture.save_output:
            print(f"   📁 Output Directory: {capture.output_directory}")
        
        if not capture.start_capture():
            print("❌ Failed to start debug capture")
            return
        
        print("\n🎬 Starting debug capture...")
        frame_count = 0
        
        while capture.running:
            frame_pair = capture.get_synchronized_frames(timeout=2.0)
            
            if frame_pair is None:
                print(".", end="", flush=True)
                continue
            
            frame_count += 1
            debug_frame_num = frame_pair.get('debug_frame_number', '?')
            
            # Display progress
            print(f"\r📹 Frame {frame_count} (Debug #{debug_frame_num})", end="", flush=True)
            
            # Check if debug mode completed
            if frame_pair.get('debug_mode') and not capture.running:
                print(f"\n✅ Debug capture completed!")
                break
        
        # Final statistics
        final_stats = capture.get_stats()
        print(f"\n📊 Debug Results:")
        print(f"   🎯 Frames captured: {final_stats['debug_frames_captured']}")
        print(f"   📊 Synchronized pairs: {final_stats['synchronized_pairs']}")
        print(f"   🔧 Homography applied: {'✅' if final_stats['homography_loaded'] else '❌'}")
        
        if capture.save_output:
            accumulated_count = final_stats.get('accumulated_frames_count', 0)
            total_files = final_stats['debug_frames_captured'] * 3  # 2 images + 1 metadata per frame
            print(f"   💾 Frames in memory: {accumulated_count}")
            print(f"   💾 Total files to save: {total_files} ({final_stats['debug_frames_captured']} frame pairs)")
            print(f"   📁 Will be saved to: {capture.output_directory}")
            print(f"   ⏳ Files will be written to disk during shutdown...")
        
    except KeyboardInterrupt:
        print("\n🛑 Debug stopped by user")
    except Exception as e:
        print(f"❌ Debug error: {e}")
    finally:
        capture.stop_capture()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        debug_mode_example()
    elif len(sys.argv) > 1 and sys.argv[1] == "--timing":
        # Timing statistics demo
        print("⏱️  Timing Statistics Demo - Monitor capture loop performance")
        
        capture = HardwareSyncDualCamera(
            width=1920,
            height=1080,
            framerate=15,
            bitrate=4000000,
            flip_camera0=False,
            enable_homography=False,
            homography_file="wallCalibration_image_1080.pickle",
            correct_camera1_to_camera0=False,
            auto_calibrate=False,
            save_output=True,
            output_directory="timing_capture_frames",
            simple_output=False  # Show detailed timing info
        )
        
        try:
            if not capture.start_capture():
                print("❌ Failed to start capture")
                sys.exit(1)
            
            print("✅ Capture started - Collecting timing statistics...")
            print("Press Ctrl+C to stop and see detailed timing analysis\n")
            
            frame_count = 0
            while True:
                frame_pair = capture.get_synchronized_frames(timeout=2.0)
                if frame_pair is None:
                    continue
                    
                frame_count += 1
                
                # Show timing stats every 50 frames
                if frame_count % 50 == 0:
                    timing_stats = capture.get_timing_stats()
                    print(f"\n⏱️  Timing Statistics (Frame {frame_count}):")
                    print(f"   🔄 Loop count: {timing_stats['loop_count']}")
                    print(f"   📊 Avg loop time: {timing_stats['avg_loop_time_ms']:.2f}ms")
                    print(f"   🚀 Min loop time: {timing_stats['min_loop_time_ms']:.2f}ms")
                    print(f"   🐌 Max loop time: {timing_stats['max_loop_time_ms']:.2f}ms")
                    print(f"   ⚡ Recent avg: {timing_stats['recent_avg_loop_time_ms']:.2f}ms")
                    print(f"   🎯 Est. FPS: {timing_stats['actual_fps_estimate']:.1f}")
                    print(f"   🏆 Max possible FPS: {timing_stats['theoretical_max_fps']:.1f}")
                    
        except KeyboardInterrupt:
            print("\n🛑 Final Timing Analysis:")
            final_timing = capture.get_timing_stats()
            print(f"   📈 Total loops executed: {final_timing['loop_count']}")
            print(f"   ⏱️  Total capture time: {final_timing['total_loop_time_s']:.2f}s")
            print(f"   📊 Average loop time: {final_timing['avg_loop_time_ms']:.2f}ms")
            print(f"   🚀 Fastest loop: {final_timing['min_loop_time_ms']:.2f}ms")
            print(f"   🐌 Slowest loop: {final_timing['max_loop_time_ms']:.2f}ms")
            print(f"   ⚡ Estimated FPS: {final_timing['actual_fps_estimate']:.1f}")
        finally:
            capture.stop_capture()
    elif len(sys.argv) > 1 and sys.argv[1] == "--simple":
        # Simple output mode example
        print("🔄 Simple Output Mode - Minimal status display")
        
        # Create capture with simple output enabled
        capture = HardwareSyncDualCamera(
            width=1920,
            height=1080,
            framerate=15,
            bitrate=8000000,
            flip_camera0=True,
            enable_homography=True,
            homography_file="wallCalibration_image_1080.pickle",
            correct_camera1_to_camera0=True,
            auto_calibrate=True,
            calibration_frames=15,
            calibration_first_frame=1,
            save_output=False,
            simple_output=True  # Enable simple output
        )
        
        try:
            print("Starting simple capture...")
            if not capture.start_capture():
                print("❌ Failed to start capture")
                sys.exit(1)
            
            print("✅ Capture started - Simple mode (frame count every 10 frames)")
            print("Press Ctrl+C to stop\n")
            
            frame_count = 0
            while True:
                frame_pair = capture.get_synchronized_frames(timeout=2.0)
                if frame_pair is None:
                    continue
                frame_count += 1
                
                # Simple output will show just "Frame X" every 10 frames
                if frame_count % 10 == 0:
                    if capture.simple_output:
                        print(f"Frame {frame_count}")
                        
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
        finally:
            capture.stop_capture()
    else:
        main()