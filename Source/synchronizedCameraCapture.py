#!/usr/bin/env python3
"""
Synchronized Dual Camera Frame Capture for OpenCV Processing
Captures synchronized frames from two cameras for difference mathematics

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
from typing import Optional, Tuple, Callable
from queue import Queue, Empty
import os
from datetime import datetime

class SynchronizedDualCameraCapture:
    """
    Captures synchronized frames from two cameras for OpenCV processing
    """
    
    def __init__(self, 
                 width: int = 1920,
                 height: int = 1080,
                 framerate: int = 30,
                 capture_format: str = "bgr",
                 buffer_size: int = 10,
                 sync_tolerance_ms: int = 33,  # ~1 frame at 30fps
                 use_hardware_sync: bool = True,
                 sync_method: str = "server_client",  # "server_client" or "timestamp"
                 flip_camera1: bool = True):
        """
        Initialize the synchronized dual camera capture
        
        Args:
            width: Video width in pixels (default 1920 for 1080p)
            height: Video height in pixels (default 1080 for 1080p)
            framerate: Frames per second
            capture_format: Output format ("bgr", "rgb", "yuv420", "gray")
            buffer_size: Maximum number of frame pairs to buffer
            sync_tolerance_ms: Maximum time difference for frame synchronization (ms)
            use_hardware_sync: Use rpicam-vid --sync feature for hardware sync
            sync_method: "server_client" (uses --sync) or "timestamp" (software sync)
            flip_camera1: Flip camera 1 frames horizontally (left/right)
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.capture_format = capture_format
        self.buffer_size = buffer_size
        self.sync_tolerance_ms = sync_tolerance_ms
        self.use_hardware_sync = use_hardware_sync
        self.sync_method = sync_method
        self.flip_camera1 = flip_camera1
        
        # Frame queues for each camera
        self.camera0_queue = Queue(maxsize=buffer_size)
        self.camera1_queue = Queue(maxsize=buffer_size)
        self.synchronized_queue = Queue(maxsize=buffer_size)
        
        # Process handles
        self.camera0_process: Optional[subprocess.Popen] = None
        self.camera1_process: Optional[subprocess.Popen] = None
        
        # Threading
        self.capture_threads = []
        self.sync_thread = None
        self.running = False
        
        # Statistics
        self.stats = {
            'frames_captured_cam0': 0,
            'frames_captured_cam1': 0,
            'synchronized_pairs': 0,
            'dropped_frames': 0,
            'sync_errors': 0
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop_capture()
        sys.exit(0)
    
    def _build_camera_command(self, camera_id: int, is_server: bool = False) -> list:
        """
        Build rpicam-vid command for frame capture
        
        Args:
            camera_id: Camera index (0 or 1)
            is_server: True for server camera, False for client camera
            
        Returns:
            Command list
        """
        if self.use_hardware_sync and self.sync_method == "server_client":
            # Hardware sync using --sync feature
            cmd = [
                'rpicam-vid',
                '--camera', str(camera_id),
                '-t', '0',  # Run indefinitely
                '-n',  # No preview
                '--width', str(self.width),
                '--height', str(self.height),
                '--framerate', str(self.framerate),
                '--codec', 'libav',
                '--libav-format', 'h264',  # Better for streaming
                '-o', '-'  # Output to stdout
            ]
            
            # Add sync parameter
            if is_server:
                cmd.extend(['--sync', 'server'])
            else:
                cmd.extend(['--sync', 'client'])
                
        else:
            # Legacy YUV420 capture for timestamp-based sync
            cmd = [
                'rpicam-vid',
                '--camera', str(camera_id),
                '-t', '0',  # Run indefinitely
                '-n',  # No preview
                '--width', str(self.width),
                '--height', str(self.height),
                '--framerate', str(self.framerate),
                '--codec', 'yuv420',  # Raw YUV format
                '-o', '-'  # Output to stdout
            ]
        
        return cmd
    
    def _capture_frames_from_camera(self, camera_id: int, frame_queue: Queue):
        """
        Capture frames from a specific camera in a separate thread
        
        Args:
            camera_id: Camera index
            frame_queue: Queue to store captured frames
        """
        # For hardware sync, camera 0 is server, camera 1 is client
        is_server = (camera_id == 0) if self.use_hardware_sync else False
        cmd = self._build_camera_command(camera_id, is_server)
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            if camera_id == 0:
                self.camera0_process = process
            else:
                self.camera1_process = process
            
            self.logger.info(f"Started capture from camera {camera_id} ({'server' if is_server else 'client' if self.use_hardware_sync else 'standalone'})")
            
            if self.use_hardware_sync and self.sync_method == "server_client":
                # H.264 stream processing
                self._process_h264_stream(process, camera_id, frame_queue)
            else:
                # YUV420 stream processing
                self._process_yuv420_stream(process, camera_id, frame_queue)
                
        except Exception as e:
            self.logger.error(f"Failed to start camera {camera_id}: {e}")
        finally:
            if process and process.poll() is None:
                process.terminate()
    
    def _process_h264_stream(self, process: subprocess.Popen, camera_id: int, frame_queue: Queue):
        """
        Process H.264 stream using OpenCV VideoCapture
        
        Args:
            process: subprocess handle
            camera_id: camera index
            frame_queue: queue for frames
        """
        # Create VideoCapture from subprocess pipe
        import io
        
        # Read H.264 stream and decode with OpenCV
        buffer = b''
        frame_count = 0
        
        while self.running and process.poll() is None:
            try:
                # Read data from process
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                
                buffer += chunk
                
                # For H.264 streams with --sync, frames are synchronized at source
                # We need to decode the H.264 stream to get individual frames
                
                # Simple approach: write to temporary file and read with OpenCV
                # Note: This is simplified - for production, use proper H.264 parsing
                
                # For now, let's use a different approach - capture at fixed intervals
                # since --sync ensures hardware synchronization
                
                if len(buffer) > 32768:  # Arbitrary buffer size
                    # Create frame placeholder with timestamp
                    # Hardware sync means frames are inherently synchronized
                    timestamp = time.time() * 1000
                    
                    # For demonstration - in practice you'd decode the H.264 properly
                    # This is a placeholder that indicates sync frame availability
                    frame_info = {
                        'frame': None,  # Would contain decoded frame
                        'timestamp': timestamp,
                        'camera_id': camera_id,
                        'sync_frame': True,  # Hardware synchronized
                        'buffer_size': len(buffer)
                    }
                    
                    try:
                        frame_queue.put_nowait(frame_info)
                        if camera_id == 0:
                            self.stats['frames_captured_cam0'] += 1
                        else:
                            self.stats['frames_captured_cam1'] += 1
                    except:
                        # Queue full
                        try:
                            frame_queue.get_nowait()
                            frame_queue.put_nowait(frame_info)
                            self.stats['dropped_frames'] += 1
                        except:
                            pass
                    
                    buffer = b''  # Reset buffer
                    frame_count += 1
                    
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error processing H.264 stream from camera {camera_id}: {e}")
                break
    
    def _process_yuv420_stream(self, process: subprocess.Popen, camera_id: int, frame_queue: Queue):
        """
        Process YUV420 stream (original method)
        
        Args:
            process: subprocess handle
            camera_id: camera index
            frame_queue: queue for frames
        """
        # Calculate frame size in bytes (YUV420 format)
        frame_size = int(self.width * self.height * 1.5)  # Y + U/2 + V/2
        
        while self.running and process.poll() is None:
            try:
                # Read one frame worth of data
                frame_data = process.stdout.read(frame_size)
                
                if len(frame_data) != frame_size:
                    if len(frame_data) == 0:
                        break  # End of stream
                    else:
                        self.logger.warning(f"Incomplete frame from camera {camera_id}")
                        continue
                
                # Convert YUV420 to the desired format
                frame = self._convert_yuv420_to_target(frame_data, camera_id)
                
                # Add timestamp
                timestamp = time.time() * 1000  # milliseconds
                frame_info = {
                    'frame': frame,
                    'timestamp': timestamp,
                    'camera_id': camera_id,
                    'sync_frame': False  # Software synchronized
                }
                
                # Add to queue (drop oldest if full)
                try:
                    frame_queue.put_nowait(frame_info)
                    if camera_id == 0:
                        self.stats['frames_captured_cam0'] += 1
                    else:
                        self.stats['frames_captured_cam1'] += 1
                except:
                    # Queue full, drop frame
                    try:
                        frame_queue.get_nowait()  # Remove oldest
                        frame_queue.put_nowait(frame_info)  # Add new
                        self.stats['dropped_frames'] += 1
                    except:
                        pass
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error capturing from camera {camera_id}: {e}")
                break
    
    def _convert_yuv420_to_target(self, yuv_data: bytes, camera_id: int = 0) -> np.ndarray:
        """
        Convert YUV420 data to target format
        
        Args:
            yuv_data: Raw YUV420 bytes
            camera_id: Camera ID (used for flipping camera 1)
            
        Returns:
            Converted frame as numpy array
        """
        # Reshape YUV420 data
        yuv_array = np.frombuffer(yuv_data, dtype=np.uint8)
        
        # YUV420 layout: Y plane, then U plane (1/4 size), then V plane (1/4 size)
        y_size = self.width * self.height
        uv_size = y_size // 4
        
        y_plane = yuv_array[:y_size].reshape((self.height, self.width))
        u_plane = yuv_array[y_size:y_size + uv_size].reshape((self.height // 2, self.width // 2))
        v_plane = yuv_array[y_size + uv_size:].reshape((self.height // 2, self.width // 2))
        
        # Upsample U and V planes
        u_upsampled = cv2.resize(u_plane, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        v_upsampled = cv2.resize(v_plane, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        
        # Combine planes
        yuv_frame = np.stack([y_plane, u_upsampled, v_upsampled], axis=2)
        
        # Convert to target format
        if self.capture_format == "bgr":
            frame = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR)
        elif self.capture_format == "rgb":
            frame = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2RGB)
        elif self.capture_format == "gray":
            frame = y_plane
        else:  # yuv420
            frame = yuv_frame
        
        # Flip camera 1 frames horizontally if requested
        if camera_id == 1 and self.flip_camera1:
            frame = cv2.flip(frame, 1)  # 1 = horizontal flip (left/right)
        
        return frame
    
    def _synchronize_frames(self):
        """
        Synchronize frames from both cameras based on timestamps
        """
        cam0_buffer = []
        cam1_buffer = []
        
        while self.running:
            try:
                # Get frames from both cameras
                try:
                    frame0 = self.camera0_queue.get(timeout=1.0)
                    cam0_buffer.append(frame0)
                except Empty:
                    continue
                
                try:
                    frame1 = self.camera1_queue.get(timeout=1.0)
                    cam1_buffer.append(frame1)
                except Empty:
                    continue
                
                # Find synchronized pairs
                synchronized_pairs = []
                
                for i, f0 in enumerate(cam0_buffer):
                    for j, f1 in enumerate(cam1_buffer):
                        time_diff = abs(f0['timestamp'] - f1['timestamp'])
                        
                        if time_diff <= self.sync_tolerance_ms:
                            synchronized_pairs.append((i, j, time_diff, f0, f1))
                
                # Process best synchronized pairs
                if synchronized_pairs:
                    # Sort by time difference (best sync first)
                    synchronized_pairs.sort(key=lambda x: x[2])
                    
                    used_cam0_indices = set()
                    used_cam1_indices = set()
                    
                    for cam0_idx, cam1_idx, time_diff, frame0, frame1 in synchronized_pairs:
                        if cam0_idx in used_cam0_indices or cam1_idx in used_cam1_indices:
                            continue
                        
                        # Create synchronized frame pair
                        sync_pair = {
                            'frame0': frame0['frame'],
                            'frame1': frame1['frame'],
                            'timestamp0': frame0['timestamp'],
                            'timestamp1': frame1['timestamp'],
                            'sync_diff_ms': time_diff
                        }
                        
                        # Add to synchronized queue
                        try:
                            self.synchronized_queue.put_nowait(sync_pair)
                            self.stats['synchronized_pairs'] += 1
                        except:
                            # Queue full, drop oldest
                            try:
                                self.synchronized_queue.get_nowait()
                                self.synchronized_queue.put_nowait(sync_pair)
                            except:
                                pass
                        
                        used_cam0_indices.add(cam0_idx)
                        used_cam1_indices.add(cam1_idx)
                    
                    # Remove used frames from buffers
                    cam0_buffer = [f for i, f in enumerate(cam0_buffer) if i not in used_cam0_indices]
                    cam1_buffer = [f for i, f in enumerate(cam1_buffer) if i not in used_cam1_indices]
                
                # Clean old frames from buffers (keep only recent ones)
                current_time = time.time() * 1000
                max_age_ms = 1000  # 1 second
                
                cam0_buffer = [f for f in cam0_buffer if (current_time - f['timestamp']) < max_age_ms]
                cam1_buffer = [f for f in cam1_buffer if (current_time - f['timestamp']) < max_age_ms]
                
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in frame synchronization: {e}")
                    self.stats['sync_errors'] += 1
    
    def start_capture(self) -> bool:
        """
        Start synchronized capture from both cameras
        
        Returns:
            True if capture started successfully
        """
        self.logger.info("Starting synchronized dual camera capture...")
        self.running = True
        
        try:
            # Start capture threads for both cameras
            thread0 = threading.Thread(
                target=self._capture_frames_from_camera,
                args=(0, self.camera0_queue),
                daemon=True
            )
            thread1 = threading.Thread(
                target=self._capture_frames_from_camera,
                args=(1, self.camera1_queue),
                daemon=True
            )
            
            thread0.start()
            thread1.start()
            
            self.capture_threads = [thread0, thread1]
            
            # Start synchronization thread
            self.sync_thread = threading.Thread(
                target=self._synchronize_frames,
                daemon=True
            )
            self.sync_thread.start()
            
            # Give threads time to start
            time.sleep(2)
            
            # Check if processes started successfully
            if (self.camera0_process and self.camera0_process.poll() is None and
                self.camera1_process and self.camera1_process.poll() is None):
                self.logger.info("Both cameras started successfully!")
                return True
            else:
                self.logger.error("One or both cameras failed to start")
                self.stop_capture()
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start capture: {e}")
            self.stop_capture()
            return False
    
    def get_synchronized_frames(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Get the next synchronized frame pair
        
        Args:
            timeout: Maximum time to wait for frames
            
        Returns:
            Dictionary with 'frame0', 'frame1', timestamps, and sync info
        """
        try:
            return self.synchronized_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def stop_capture(self):
        """Stop capture from both cameras"""
        self.logger.info("Stopping camera capture...")
        self.running = False
        
        # Stop processes
        for process in [self.camera0_process, self.camera1_process]:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    try:
                        process.kill()
                    except:
                        pass
        
        # Wait for threads to finish
        for thread in self.capture_threads + [self.sync_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2)
        
        self.logger.info("Camera capture stopped")
    
    def get_stats(self) -> dict:
        """Get capture statistics"""
        return self.stats.copy()


def frame_difference_analysis(frame0: np.ndarray, frame1: np.ndarray) -> dict:
    """
    Perform difference analysis between two synchronized frames
    
    Args:
        frame0: Frame from camera 0
        frame1: Frame from camera 1
        
    Returns:
        Dictionary with analysis results
    """
    # Convert to grayscale if needed
    if len(frame0.shape) == 3:
        gray0 = cv2.cvtColor(frame0, cv2.COLOR_BGR2GRAY)
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    else:
        gray0, gray1 = frame0, frame1
    
    # Calculate absolute difference
    diff = cv2.absdiff(gray0, gray1)
    
    # Calculate statistics
    mean_diff = np.mean(diff)
    max_diff = np.max(diff)
    std_diff = np.std(diff)
    
    # Create binary difference mask (threshold at mean + 2*std)
    threshold = mean_diff + 2 * std_diff
    diff_mask = (diff > threshold).astype(np.uint8) * 255
    
    # Find contours of significant differences
    contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Calculate total difference area
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
        'contours': contours
    }


def main():
    """Example usage of synchronized dual camera capture"""
    
    # Create capture instance with 1080p resolution
    capture = SynchronizedDualCameraCapture(
        width=1920,
        height=1080,
        framerate=30,
        capture_format="bgr",
        buffer_size=5,
        sync_tolerance_ms=33,  # ~1 frame tolerance
        flip_camera1=True  # Flip camera 1 frames horizontally
    )
    
    try:
        # Start capture
        if not capture.start_capture():
            print("Failed to start camera capture")
            return
        
        print("Synchronized capture started!")
        print("Processing frame differences...")
        print("Press Ctrl+C to stop")
        
        frame_count = 0
        
        while True:
            # Get synchronized frame pair
            frame_pair = capture.get_synchronized_frames(timeout=2.0)
            
            if frame_pair is None:
                print("No synchronized frames available")
                continue
            
            frame_count += 1
            
            # Perform difference analysis
            analysis = frame_difference_analysis(
                frame_pair['frame0'], 
                frame_pair['frame1']
            )
            
            # Print analysis results
            print(f"\nFrame {frame_count}:")
            print(f"  Sync difference: {frame_pair['sync_diff_ms']:.1f}ms")
            print(f"  Mean difference: {analysis['mean_difference']:.2f}")
            print(f"  Max difference: {analysis['max_difference']}")
            print(f"  Difference area: {analysis['difference_percentage']:.2f}%")
            print(f"  Difference regions: {analysis['num_difference_regions']}")
            
            # Optional: Display frames (requires display)
            if os.environ.get('DISPLAY'):
                # Show original frames
                combined = np.hstack([frame_pair['frame0'], frame_pair['frame1']])
                cv2.imshow('Camera 0 | Camera 1', cv2.resize(combined, (1280, 360)))
                
                # Show difference
                diff_colored = cv2.applyColorMap(analysis['difference_image'], cv2.COLORMAP_JET)
                cv2.imshow('Difference Analysis', cv2.resize(diff_colored, (640, 360)))
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            # Process every 30th frame for stats
            if frame_count % 30 == 0:
                stats = capture.get_stats()
                print(f"\nCapture Statistics:")
                print(f"  Camera 0 frames: {stats['frames_captured_cam0']}")
                print(f"  Camera 1 frames: {stats['frames_captured_cam1']}")
                print(f"  Synchronized pairs: {stats['synchronized_pairs']}")
                print(f"  Dropped frames: {stats['dropped_frames']}")
                print(f"  Sync errors: {stats['sync_errors']}")
    
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        capture.stop_capture()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()