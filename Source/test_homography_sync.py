#!/usr/bin/env python3
"""
Hardware Sync with Homography Test Script

This script demonstrates the hardware synchronized dual camera capture
with homography correction and alignment applied to both cameras.

Author: Matthew Boillat
Date: October 2025
"""

import cv2
import numpy as np
import time
from hardwareSyncCapture import HardwareSyncDualCamera

def save_comparison_images(frame_pair, frame_count):
    """Save comparison images showing before/after homography correction"""
    
    # Save individual frames
    cv2.imwrite(f'frame_{frame_count:04d}_camera0_corrected.jpg', frame_pair['frame0'])
    cv2.imwrite(f'frame_{frame_count:04d}_camera1_corrected.jpg', frame_pair['frame1'])
    
    # Create side-by-side comparison
    combined = np.hstack((frame_pair['frame0'], frame_pair['frame1']))
    cv2.imwrite(f'frame_{frame_count:04d}_combined_corrected.jpg', combined)
    
    # Create difference image
    gray0 = cv2.cvtColor(frame_pair['frame0'], cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(frame_pair['frame1'], cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray0, gray1)
    
    # Enhance difference for visibility
    diff_enhanced = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
    cv2.imwrite(f'frame_{frame_count:04d}_difference.jpg', diff_enhanced)

def analyze_frame_alignment(frame_pair):
    """Analyze how well the frames are aligned after homography correction"""
    
    # Convert to grayscale
    gray0 = cv2.cvtColor(frame_pair['frame0'], cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(frame_pair['frame1'], cv2.COLOR_BGR2GRAY)
    
    # Calculate structural similarity
    diff = cv2.absdiff(gray0, gray1)
    mean_diff = np.mean(diff)
    std_diff = np.std(diff)
    max_diff = np.max(diff)
    
    # Calculate alignment quality score (lower is better)
    alignment_score = mean_diff + (std_diff * 0.5)
    
    return {
        'mean_difference': mean_diff,
        'std_difference': std_diff, 
        'max_difference': max_diff,
        'alignment_score': alignment_score,
        'alignment_quality': 'Excellent' if alignment_score < 10 else 
                           'Good' if alignment_score < 25 else
                           'Fair' if alignment_score < 50 else 'Poor'
    }

def main():
    """Test hardware sync with homography correction"""
    
    print("🔧 Testing Hardware Sync with Homography Correction")
    print("="*60)
    
    # Create capture instance with homography enabled
    capture = HardwareSyncDualCamera(
        width=1920,
        height=1080,
        framerate=10,  # Lower framerate for testing
        bitrate=5000000,  # 5 Mbps
        flip_camera1=True,
        enable_homography=True,
        homography_file="wallCalibration_image_1080.pickle",
        correct_camera1_to_camera0=True,  # Correct camera 1 to match camera 0
        auto_calibrate=True,  # Enable auto-calibration
        calibration_frames=12,  # Frames for auto-calibration
        calibration_first_frame=5  # First frame to use for calculation
    )
    
    try:
        # Check homography status
        homography_status = capture.get_homography_status()
        print("\n🔍 Homography Status:")
        for key, value in homography_status.items():
            icon = "✅" if value is True else "❌" if value is False else "📊"
            print(f"   {icon} {key}: {value}")
        
        if homography_status['homography_loaded']:
            corrected_cam = homography_status['corrected_camera']
            reference_cam = homography_status['reference_camera']
            print(f"\n🎯 Camera {corrected_cam} will be aligned to match Camera {reference_cam} (reference)")
        elif homography_status['calibration_needed'] and homography_status['auto_calibrate_enabled']:
            print(f"\n🔧 Auto-calibration will be performed using {homography_status['calibration_frames']} frames")
            print(f"   Starting from frame {homography_status['calibration_first_frame']} for calculation")
        
        if not homography_status['homography_loaded'] and not homography_status['auto_calibrate_enabled']:
            print("\n⚠️  WARNING: No homography correction available and auto-calibration disabled!")
            response = input("   Continue without homography correction? (y/N): ")
            if response.lower() != 'y':
                return
        
        # Start capture
        if not capture.start_capture():
            print("❌ Failed to start capture")
            return
        
        print("\n✅ Capture started successfully!")
        print("📸 Capturing test frames with homography correction...")
        print("Press Ctrl+C to stop\n")
        
        frame_count = 0
        test_frames = 20  # Capture 20 test frames
        alignment_scores = []
        
        while frame_count < test_frames:
            # Get synchronized and corrected frame pair
            frame_pair = capture.get_synchronized_frames(timeout=3.0)
            
            if frame_pair is None:
                print("⚠️  Timeout waiting for frames")
                continue
            
            frame_count += 1
            
            # Analyze alignment quality
            alignment = analyze_frame_alignment(frame_pair)
            alignment_scores.append(alignment['alignment_score'])
            
            # Save sample frames
            if frame_count <= 5 or frame_count % 5 == 0:
                save_comparison_images(frame_pair, frame_count)
                print(f"💾 Saved frame set {frame_count}")
            
            # Display progress
            corrected = "🎯" if frame_pair.get('homography_corrected', False) else "❌"
            quality = alignment['alignment_quality']
            
            print(f"📊 Frame {frame_count:2d}: {corrected} {quality:>9s} "
                  f"(score: {alignment['alignment_score']:5.1f}, "
                  f"mean_diff: {alignment['mean_difference']:5.1f})")
        
        # Calculate summary statistics
        avg_score = np.mean(alignment_scores)
        min_score = np.min(alignment_scores)
        max_score = np.max(alignment_scores)
        
        print("\n" + "="*60)
        print("📈 ALIGNMENT ANALYSIS SUMMARY")
        print("="*60)
        print(f"🎯 Frames captured: {frame_count}")
        print(f"📊 Average alignment score: {avg_score:.2f}")
        print(f"🥇 Best alignment score: {min_score:.2f}")
        print(f"🥉 Worst alignment score: {max_score:.2f}")
        
        # Get final statistics
        stats = capture.get_stats()
        print(f"\n📈 CAPTURE STATISTICS")
        print(f"   🎥 Total frame pairs: {stats['synchronized_pairs']}")
        print(f"   🎯 Homography corrections: {stats['homography_corrections']}")
        print(f"   ⚠️  Homography failures: {stats['homography_failures']}")
        print(f"   ❌ Dropped frames: {stats['dropped_frames']}")
        
        success_rate = (stats['homography_corrections'] / 
                       max(1, stats['homography_corrections'] + stats['homography_failures'])) * 100
        print(f"   ✅ Correction success rate: {success_rate:.1f}%")
        
        print(f"\n💾 Sample images saved with single-camera homography correction applied")
        print(f"   • frame_XXXX_camera0_corrected.jpg - Camera 0 (reference)")
        print(f"   • frame_XXXX_camera1_corrected.jpg - Camera 1 (corrected to match Camera 0 + flipped)")
        print(f"   • frame_XXXX_combined_corrected.jpg - Side-by-side comparison")
        print(f"   • frame_XXXX_difference.jpg - Difference visualization")
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"❌ Error during test: {e}")
    finally:
        capture.stop_capture()
        print("✅ Test completed")

if __name__ == "__main__":
    main()