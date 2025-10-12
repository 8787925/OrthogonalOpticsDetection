#!/usr/bin/env python3
"""
Simple example script for dual camera streaming
Usage: python3 stream_cameras_example.py
"""

import sys
import os

# Add the Source directory to the path so we can import our module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dualCameraStreaming import DualCameraStreamer

def main():
    """Simple example of how to use the DualCameraStreamer with UDP"""
    
    print("Starting dual camera streaming example...")
    print("This will stream from two cameras using UDP on ports 8554 and 8555")
    print("Press Ctrl+C to stop\n")
    
    # Create streamer with UDP protocol
    streamer = DualCameraStreamer(
        camera0_port=8554,
        camera1_port=8555,
        width=1280,        # Lower resolution for testing
        height=720,
        framerate=30,
        protocol="udp",    # Use UDP instead of TCP
        target_ip="0.0.0.0"
    )
    
    try:
        # Start streaming
        success = streamer.start_streaming()
        
        if success:
            print("✓ Both cameras started successfully!")
            print("\nStream URLs:")
            print(f"  Camera 0: udp://YOUR_PI_IP:8554")
            print(f"  Camera 1: udp://YOUR_PI_IP:8555")
            print("\nTo view streams from another device:")
            print("  VLC: udp://PI_IP_ADDRESS:8554")
            print("  VLC: udp://PI_IP_ADDRESS:8555")
            print("  ffplay: ffplay udp://PI_IP_ADDRESS:8554")
            print("  ffplay: ffplay udp://PI_IP_ADDRESS:8555")
            print("\nStreaming... Press Ctrl+C to stop")
            
            # Keep running until interrupted
            while True:
                import time
                time.sleep(1)
                
        else:
            print("✗ Failed to start camera streams")
            print("Check that:")
            print("  - Two cameras are connected")
            print("  - rpicam-vid is installed")
            print("  - Cameras are not being used by other processes")
            
    except KeyboardInterrupt:
        print("\n\nStopping streams...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        streamer.stop_streaming()
        print("Streams stopped.")

if __name__ == "__main__":
    main()