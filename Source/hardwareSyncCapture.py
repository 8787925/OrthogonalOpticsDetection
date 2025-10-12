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
from CalibrationFileManager import CalibrationFileManager
from alignImages import align_fromHomography

class HardwareSyncDualCamera:
    """
    Hardware-synchronized dual camera capture using rpicam-vid --sync feature
    """
    
    def __init__(self, 
                 width: int = 1920,
                 height: int = 1080,
                 framerate: int = 30,
                 bitrate: int = 10000000,
                 buffer_size: int = 10,
                 flip_camera1: bool = True,
                 enable_homography: bool = True,
                 homography_file: str = "wallCalibration_image_1080.pickle",
                 correct_camera1_to_camera0: bool = True):
        """
        Initialize hardware synchronized capture
        
        Args:
            width: Video width (default 1920 for 1080p)
            height: Video height (default 1080 for 1080p)
            framerate: Frames per second
            bitrate: Video bitrate for H.264 encoding
            buffer_size: Frame buffer size
            flip_camera1: Flip camera 1 frames horizontally (left/right)
            enable_homography: Enable homography correction
            homography_file: Homography matrix file
            correct_camera1_to_camera0: If True, correct camera 1 to match camera 0 (typical)
                                      If False, correct camera 0 to match camera 1
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.bitrate = bitrate
        self.buffer_size = buffer_size
        self.flip_camera1 = flip_camera1
        self.enable_homography = enable_homography
        self.correct_camera1_to_camera0 = correct_camera1_to_camera0
        
        # Homography support
        self.homography_matrix: Optional[np.ndarray] = None
        self.calibration_manager: Optional[CalibrationFileManager] = None
        self.homography_loaded = False
        
        # Initialize homography if enabled
        if self.enable_homography:
            self._initialize_homography(homography_file)
        
        # Temporary files for H.264 streams
        self.temp_dir = tempfile.mkdtemp(prefix="sync_cameras_")
        self.server_fifo = os.path.join(self.temp_dir, "server_stream")
        self.client_fifo = os.path.join(self.temp_dir, "client_stream")
        
        # Create named pipes
        os.mkfifo(self.server_fifo)
        os.mkfifo(self.client_fifo)
        
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
            'homography_failures': 0
        }
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Register cleanup
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info("Shutting down...")
        self.stop_capture()
        sys.exit(0)
    
    def _initialize_homography(self, homography_file: str):
        """
        Initialize homography correction by loading calibration matrices
        
        Args:
            homography_file: Path to the homography calibration file
        """
        try:
            self.calibration_manager = CalibrationFileManager(homography_file)
            self.homography_matrix = self.calibration_manager.load_homography_matrix()
            
            if self.homography_matrix is not None:
                self.homography_loaded = True
                self.logger.info("✅ Homography matrix loaded successfully")
                self.logger.info(f"   Matrix shape: {self.homography_matrix.shape}")
                
                # Validate homography matrix
                if self.homography_matrix.shape != (3, 3):
                    self.logger.error("❌ Invalid homography matrix shape")
                    self.homography_loaded = False
                    return
                
                # Check for reasonable values
                det = np.linalg.det(self.homography_matrix)
                if abs(det) < 1e-10:
                    self.logger.error("❌ Homography matrix appears to be singular")
                    self.homography_loaded = False
                    return
                    
                self.logger.info(f"   Matrix determinant: {det:.6f}")
                
            else:
                self.logger.warning("⚠️  No homography matrix found - alignment disabled")
                self.homography_loaded = False
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize homography: {e}")
            self.homography_loaded = False
    
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
    
    def _build_camera_command(self, camera_id: int, is_server: bool, output_path: str) -> list:
        """
        Build rpicam-vid command with hardware sync
        
        Args:
            camera_id: Camera index (0 or 1)
            is_server: True for server, False for client
            output_path: Output file path
            
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
            '-o', output_path
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
            # Start server camera (camera 0)
            server_cmd = self._build_camera_command(0, True, self.server_fifo)
            self.logger.info(f"Starting server camera: {' '.join(server_cmd)}")
            self.server_process = subprocess.Popen(
                server_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Start client camera (camera 1)
            client_cmd = self._build_camera_command(1, False, self.client_fifo)
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
        Capture synchronized frames using OpenCV VideoCapture
        """
        try:
            # Open video streams from named pipes
            self.logger.info("Opening video streams...")
            
            # Open server stream
            self.server_cap = cv2.VideoCapture(self.server_fifo)
            if not self.server_cap.isOpened():
                self.logger.error("Failed to open server video stream")
                return
            
            # Open client stream  
            self.client_cap = cv2.VideoCapture(self.client_fifo)
            if not self.client_cap.isOpened():
                self.logger.error("Failed to open client video stream")
                return
            
            self.logger.info("Video streams opened successfully")
            
            while self.running:
                # Read frames from both cameras
                # Since they're hardware synchronized, we can read them sequentially
                
                ret_server, frame_server = self.server_cap.read()
                ret_client, frame_client = self.client_cap.read()
                
                if not ret_server or not ret_client:
                    # End of stream or error
                    if self.running:
                        self.logger.warning("Failed to read from one or both cameras")
                    break
                
                # Flip camera 1 (client) frame horizontally if requested
                if self.flip_camera1:
                    frame_client = cv2.flip(frame_client, 1)  # 1 = horizontal flip
                
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
                
                # Create synchronized frame pair with one camera corrected
                timestamp = time.time() * 1000
                corrected_camera = 1 if self.correct_camera1_to_camera0 else 0
                frame_pair = {
                    'frame0': frame_server,  # Server camera (camera 0)
                    'frame1': frame_client,  # Client camera (camera 1) - flipped if enabled
                    'timestamp': timestamp,
                    'hardware_synced': True,
                    'homography_corrected': self.enable_homography and self.homography_loaded,
                    'corrected_camera': corrected_camera if (self.enable_homography and self.homography_loaded) else None
                }
                
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
        
        # Cleanup temporary files
        try:
            os.unlink(self.server_fifo)
            os.unlink(self.client_fifo)
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
            'flip_camera1_enabled': self.flip_camera1
        })
        return stats
    
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
            'correct_camera1_to_camera0': self.correct_camera1_to_camera0,
            'corrected_camera': 1 if self.correct_camera1_to_camera0 else 0,
            'reference_camera': 0 if self.correct_camera1_to_camera0 else 1,
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
        flip_camera1=True,  # Flip camera 1 frames horizontally
        enable_homography=True,  # Enable homography correction
        homography_file="wallCalibration_image_1080.pickle",
        correct_camera1_to_camera0=True  # Correct camera 1 to match camera 0
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
            frame_pair = capture.get_synchronized_frames(timeout=2.0)
            
            if frame_pair is None:
                print("⚠️  No synchronized frames available")
                continue
            
            frame_count += 1
            
            # Perform difference analysis on aligned frames
            analysis = frame_difference_analysis(
                frame_pair['frame0'],  # Camera 0 (reference or corrected)
                frame_pair['frame1']   # Camera 1 (corrected or reference) + flipped
            )
            
            # Print results
            if frame_count % 10 == 0:
                corrected_camera = frame_pair.get('corrected_camera', 'None')
                print(f"\n📊 Frame {frame_count} (Hardware Synced + Camera {corrected_camera} Corrected):")
                print(f"   📊 Mean diff: {analysis['mean_difference']:.2f}")
                print(f"   🎯 Diff area: {analysis['difference_percentage']:.2f}%")
                print(f"   📍 Regions: {analysis['num_difference_regions']}")
                print(f"   🔧 Homography: {'✅' if frame_pair.get('homography_corrected', False) else '❌'}")
                
                # Statistics including homography
                stats = capture.get_stats()
                print(f"   📈 Total pairs: {stats['synchronized_pairs']}")
                print(f"   🎯 Homography corrections: {stats['homography_corrections']}")
                print(f"   ❌ Dropped: {stats['dropped_frames']}")
                print(f"   ⚠️  Homography failures: {stats['homography_failures']}")
            
            # Status indicator
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


if __name__ == "__main__":
    main()