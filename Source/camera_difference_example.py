#!/usr/bin/env python3
"""
Simple Frame Difference Example
Demonstrates basic usage of synchronized camera capture for difference analysis

Author: Matthew Boillat
Date: October 2025
"""

import sys
import os
import cv2
import numpy as np
from synchronizedCameraCapture import SynchronizedDualCameraCapture, frame_difference_analysis

def simple_difference_monitor():
    """
    Simple example showing continuous difference monitoring between two cameras
    """
    print("Starting simple dual camera difference monitoring...")
    
    # Create capture with lower resolution for faster processing
    capture = SynchronizedDualCameraCapture(
        width=640,
        height=480,
        framerate=15,  # Lower framerate for easier processing
        capture_format="bgr",
        buffer_size=3,
        sync_tolerance_ms=66  # ~1 frame tolerance at 15fps
    )
    
    try:
        if not capture.start_capture():
            print("❌ Failed to start cameras")
            return
        
        print("✅ Cameras started successfully!")
        print("📊 Monitoring frame differences...")
        print("🔄 Press Ctrl+C to stop")
        
        # Difference tracking
        frame_count = 0
        significant_differences = 0
        difference_threshold = 2.0  # Adjust based on your needs
        
        while True:
            # Get synchronized frames
            frame_pair = capture.get_synchronized_frames(timeout=2.0)
            
            if frame_pair is None:
                print("⚠️  No frames available")
                continue
            
            frame_count += 1
            
            # Analyze differences
            analysis = frame_difference_analysis(
                frame_pair['frame0'],
                frame_pair['frame1']
            )
            
            # Check for significant differences
            is_significant = analysis['difference_percentage'] > difference_threshold
            if is_significant:
                significant_differences += 1
            
            # Print summary every 10 frames
            if frame_count % 10 == 0:
                print(f"\n📈 Frame {frame_count} Summary:")
                print(f"   🕐 Sync offset: {frame_pair['sync_diff_ms']:.1f}ms")
                print(f"   📊 Mean diff: {analysis['mean_difference']:.2f}")
                print(f"   🎯 Diff area: {analysis['difference_percentage']:.2f}%")
                print(f"   📍 Regions: {analysis['num_difference_regions']}")
                print(f"   🚨 Significant: {'YES' if is_significant else 'no'}")
                print(f"   📈 Total significant: {significant_differences}/{frame_count}")
            
            # Quick status indicator
            status_char = "🔴" if is_significant else "🟢"
            print(f"{status_char}", end="", flush=True)
            
            if frame_count % 50 == 0:
                print()  # New line every 50 frames
    
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        capture.stop_capture()
        
        # Final statistics
        stats = capture.get_stats()
        print(f"\n📊 Final Statistics:")
        print(f"   📷 Camera 0 frames: {stats['frames_captured_cam0']}")
        print(f"   📷 Camera 1 frames: {stats['frames_captured_cam1']}")
        print(f"   🔗 Synchronized pairs: {stats['synchronized_pairs']}")
        print(f"   ❌ Dropped frames: {stats['dropped_frames']}")
        print(f"   🚨 Significant differences: {significant_differences}/{frame_count}")
        print("✅ Monitoring complete!")


def save_difference_images():
    """
    Example that saves difference images when significant changes are detected
    """
    print("Starting difference detection with image saving...")
    
    capture = SynchronizedDualCameraCapture(
        width=1280,
        height=720,
        framerate=10,
        capture_format="bgr"
    )
    
    # Create output directory
    output_dir = "difference_captures"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        if not capture.start_capture():
            print("Failed to start cameras")
            return
        
        print(f"Saving significant differences to: {output_dir}/")
        frame_count = 0
        saved_count = 0
        
        while frame_count < 100:  # Capture 100 frame pairs
            frame_pair = capture.get_synchronized_frames(timeout=5.0)
            
            if frame_pair is None:
                continue
            
            frame_count += 1
            analysis = frame_difference_analysis(
                frame_pair['frame0'],
                frame_pair['frame1']
            )
            
            # Save if significant difference detected
            if analysis['difference_percentage'] > 1.0:  # Adjust threshold
                saved_count += 1
                
                # Create comparison image
                combined = np.hstack([
                    frame_pair['frame0'],
                    frame_pair['frame1'],
                    cv2.cvtColor(analysis['difference_image'], cv2.COLOR_GRAY2BGR)
                ])
                
                filename = f"{output_dir}/diff_{frame_count:04d}_{analysis['difference_percentage']:.1f}pct.jpg"
                cv2.imwrite(filename, combined)
                
                print(f"💾 Saved: {filename} ({analysis['difference_percentage']:.1f}% diff)")
            
            if frame_count % 10 == 0:
                print(f"📊 Processed {frame_count}/100 frames, saved {saved_count} differences")
    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        capture.stop_capture()
        print(f"✅ Complete! Saved {saved_count} difference images to {output_dir}/")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "save":
        save_difference_images()
    else:
        simple_difference_monitor()