#!/usr/bin/env python3
"""
Dual Camera Streaming Script for Raspberry Pi
Streams video from two cameras using rpicam-vid with TCP streaming

Author: Matthew Boillat
Date: October 2025
"""

import subprocess
import time
import signal
import sys
import logging
from typing import Optional, List
import threading

class DualCameraStreamer:
    """
    Manages streaming from two cameras using rpicam-vid
    """
    
    def __init__(self, 
                 camera0_port: int = 8554, 
                 camera1_port: int = 8555,
                 width: int = 1920,
                 height: int = 1080,
                 framerate: int = 30,
                 bitrate: int = 10000000,
                 protocol: str = "udp",
                 target_ip: str = "0.0.0.0"):
        """
        Initialize the dual camera streamer
        
        Args:
            camera0_port: Port for camera 0 stream
            camera1_port: Port for camera 1 stream
            width: Video width in pixels
            height: Video height in pixels
            framerate: Frames per second
            bitrate: Video bitrate in bits per second
            protocol: Streaming protocol ("tcp" or "udp")
            target_ip: Target IP address for UDP streaming (0.0.0.0 for any)
        """
        self.camera0_port = camera0_port
        self.camera1_port = camera1_port
        self.width = width
        self.height = height
        self.framerate = framerate
        self.bitrate = bitrate
        self.protocol = protocol.lower()
        self.target_ip = target_ip
        
        # Validate protocol
        if self.protocol not in ["tcp", "udp"]:
            raise ValueError("Protocol must be 'tcp' or 'udp'")
        
        # Process handles
        self.camera0_process: Optional[subprocess.Popen] = None
        self.camera1_process: Optional[subprocess.Popen] = None
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop_streaming()
        sys.exit(0)
    
    def _build_camera_command(self, camera_id: int, port: int) -> List[str]:
        """
        Build the rpicam-vid command for a specific camera
        
        Args:
            camera_id: Camera index (0 or 1)
            port: Port for streaming
            
        Returns:
            List of command arguments
        """
        cmd = [
            'rpicam-vid',
            '--camera', str(camera_id),
            '-t', '0',  # Run indefinitely
            '-n',  # No preview window
            '--width', str(self.width),
            '--height', str(self.height),
            '--framerate', str(self.framerate),
            '--bitrate', str(self.bitrate),
            '--codec', 'libav',
            '--libav-format', 'mpegts'
        ]
        
        # Configure output based on protocol
        if self.protocol == "udp":
            # UDP streaming - no listen parameter needed
            output_url = f'udp://{self.target_ip}:{port}'
        else:  # TCP
            # TCP streaming with listen
            output_url = f'tcp://{self.target_ip}:{port}?listen=1'
        
        cmd.extend(['-o', output_url])
        return cmd
    
    def start_camera_stream(self, camera_id: int, port: int) -> Optional[subprocess.Popen]:
        """
        Start streaming from a specific camera
        
        Args:
            camera_id: Camera index (0 or 1)
            port: TCP port for streaming
            
        Returns:
            Subprocess handle or None if failed
        """
        try:
            cmd = self._build_camera_command(camera_id, port)
            self.logger.info(f"Starting camera {camera_id} stream on port {port}")
            self.logger.debug(f"Command: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Give the process a moment to start
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                self.logger.info(f"Camera {camera_id} stream started successfully")
                return process
            else:
                stdout, stderr = process.communicate()
                self.logger.error(f"Camera {camera_id} failed to start:")
                self.logger.error(f"STDOUT: {stdout}")
                self.logger.error(f"STDERR: {stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error starting camera {camera_id}: {e}")
            return None
    
    def start_streaming(self) -> bool:
        """
        Start streaming from both cameras
        
        Returns:
            True if both cameras started successfully, False otherwise
        """
        self.logger.info("Starting dual camera streaming...")
        
        # Start camera 0
        self.camera0_process = self.start_camera_stream(0, self.camera0_port)
        
        # Start camera 1
        self.camera1_process = self.start_camera_stream(1, self.camera1_port)
        
        # Check if both cameras started
        camera0_ok = self.camera0_process is not None
        camera1_ok = self.camera1_process is not None
        
        if camera0_ok and camera1_ok:
            self.logger.info("Both cameras streaming successfully!")
            self.logger.info(f"Camera 0: {self.protocol}://{self.target_ip if self.target_ip != '0.0.0.0' else 'YOUR_PI_IP'}:{self.camera0_port}")
            self.logger.info(f"Camera 1: {self.protocol}://{self.target_ip if self.target_ip != '0.0.0.0' else 'YOUR_PI_IP'}:{self.camera1_port}")
            return True
        else:
            self.logger.warning("One or more cameras failed to start")
            if not camera0_ok:
                self.logger.warning("Camera 0 failed to start")
            if not camera1_ok:
                self.logger.warning("Camera 1 failed to start")
            return False
    
    def stop_camera_stream(self, process: Optional[subprocess.Popen], camera_name: str):
        """
        Stop a specific camera stream
        
        Args:
            process: Subprocess handle
            camera_name: Name for logging
        """
        if process:
            try:
                self.logger.info(f"Stopping {camera_name} stream...")
                process.terminate()
                
                # Wait for graceful termination
                try:
                    process.wait(timeout=5)
                    self.logger.info(f"{camera_name} stream stopped gracefully")
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"{camera_name} stream didn't stop gracefully, forcing...")
                    process.kill()
                    process.wait()
                    self.logger.info(f"{camera_name} stream force stopped")
                    
            except Exception as e:
                self.logger.error(f"Error stopping {camera_name}: {e}")
    
    def stop_streaming(self):
        """Stop streaming from both cameras"""
        self.logger.info("Stopping all camera streams...")
        
        self.stop_camera_stream(self.camera0_process, "Camera 0")
        self.stop_camera_stream(self.camera1_process, "Camera 1")
        
        self.camera0_process = None
        self.camera1_process = None
        
        self.logger.info("All camera streams stopped")
    
    def is_streaming(self) -> tuple[bool, bool]:
        """
        Check if cameras are currently streaming
        
        Returns:
            Tuple of (camera0_streaming, camera1_streaming)
        """
        camera0_streaming = (self.camera0_process is not None and 
                           self.camera0_process.poll() is None)
        camera1_streaming = (self.camera1_process is not None and 
                           self.camera1_process.poll() is None)
        
        return camera0_streaming, camera1_streaming
    
    def monitor_streams(self, check_interval: int = 30):
        """
        Monitor camera streams and restart if they fail
        
        Args:
            check_interval: How often to check stream status (seconds)
        """
        self.logger.info(f"Starting stream monitoring (checking every {check_interval}s)")
        
        while True:
            try:
                camera0_ok, camera1_ok = self.is_streaming()
                
                if not camera0_ok and self.camera0_process is not None:
                    self.logger.warning("Camera 0 stream died, restarting...")
                    self.camera0_process = self.start_camera_stream(0, self.camera0_port)
                
                if not camera1_ok and self.camera1_process is not None:
                    self.logger.warning("Camera 1 stream died, restarting...")
                    self.camera1_process = self.start_camera_stream(1, self.camera1_port)
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Error in stream monitoring: {e}")
                time.sleep(check_interval)


def main():
    """Main function to demonstrate usage"""
    # Create streamer instance with UDP streaming
    streamer = DualCameraStreamer(
        camera0_port=8554,
        camera1_port=8555,
        width=1920,
        height=1080,
        framerate=30,
        bitrate=10000000,  # 10 Mbps
        protocol="tcp",     # Use UDP instead of TCP
        target_ip="0.0.0.0"  # Listen on all interfaces
    )
    
    try:
        # Start streaming
        if streamer.start_streaming():
            print("\n" + "="*50)
            print("DUAL CAMERA STREAMING ACTIVE")
            print("="*50)
            print(f"Protocol: {streamer.protocol.upper()}")
            print(f"Camera 0 stream: {streamer.protocol}://YOUR_PI_IP:{streamer.camera0_port}")
            print(f"Camera 1 stream: {streamer.protocol}://YOUR_PI_IP:{streamer.camera1_port}")
            print("\nTo view streams, use:")
            print(f"  VLC: {streamer.protocol}://YOUR_PI_IP:{streamer.camera0_port}")
            print(f"  VLC: {streamer.protocol}://YOUR_PI_IP:{streamer.camera1_port}")
            print(f"  ffplay: ffplay {streamer.protocol}://YOUR_PI_IP:{streamer.camera0_port}")
            print(f"  ffplay: ffplay {streamer.protocol}://YOUR_PI_IP:{streamer.camera1_port}")
            print("\nPress Ctrl+C to stop streaming...")
            print("="*50)
            
            # Monitor streams (this will run until interrupted)
            streamer.monitor_streams()
            
        else:
            print("Failed to start one or more camera streams")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        streamer.stop_streaming()


if __name__ == "__main__":
    main()