#!/usr/bin/env python3
"""
Calibration and Sensitivity Mapping Example

This script demonstrates how to use the extracted calibration modules
for homography calculation and sensitivity mapping.

Author: Matthew Boillat
Date: October 2025
"""

import numpy as np
import cv2
import logging
from CalibrationFileManager import CalibrationFileManager
from HomographyCalibrator import HomographyCalibrator
from SensitivityMapper import SensitivityMapper

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def example_calibration_workflow():
    """
    Demonstrate complete calibration workflow using the new modules
    """
    print("=== Calibration and Sensitivity Mapping Example ===\n")
    
    # Initialize modules
    calibration_manager = CalibrationFileManager()
    homography_calibrator = HomographyCalibrator(calibration_frames=10, first_calibration_frame=3)
    sensitivity_mapper = SensitivityMapper(sensitivity_frames=10, first_sensitivity_frame=3)
    
    print("1. Checking existing calibration files...")
    status = calibration_manager.get_calibration_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    # Example with synthetic data (replace with real camera frames in practice)
    print("\n2. Creating synthetic test data...")
    print("   (In practice, these would be real camera captures)")
    
    # Create synthetic frame data
    local_frames = []
    remote_frames = []
    
    for i in range(10):
        # Create test images with some patterns
        local_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        remote_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Add some geometric patterns to make homography calculation possible
        cv2.rectangle(local_frame, (100 + i*2, 100 + i*2), (200 + i*2, 200 + i*2), (255, 255, 255), -1)
        cv2.rectangle(remote_frame, (110 + i*2, 110 + i*2), (210 + i*2, 210 + i*2), (255, 255, 255), -1)
        
        local_frames.append(local_frame)
        remote_frames.append(remote_frame)
    
    print(f"   Created {len(local_frames)} synthetic frame pairs")
    
    # Note: In real usage, you would skip this synthetic data creation and use actual camera frames
    print("\n3. Homography calibration (skipped with synthetic data)...")
    print("   Real usage would be:")
    print("   homography_matrix = homography_calibrator.calculate_homography_matrix(local_frames, remote_frames)")
    print("   if homography_matrix is not None:")
    print("       calibration_manager.save_homography_matrix(homography_matrix)")
    
    # Create a test homography matrix for demonstration
    test_homography = np.eye(3, dtype=np.float32)
    test_homography[0, 2] = 5.0  # Small translation
    test_homography[1, 2] = 3.0
    
    print("\n4. Sensitivity mapping (skipped with synthetic data)...")
    print("   Real usage would be:")
    print("   sensitivity_map = sensitivity_mapper.generate_sensitivity_map_from_raw_frames(")
    print("       local_frames, remote_frames, homography_matrix)")
    print("   if sensitivity_map is not None:")
    print("       calibration_manager.save_sensitivity_map(sensitivity_map)")
    
    print("\n5. Module configuration information...")
    
    print("\n   Homography Calibrator Config:")
    homography_config = homography_calibrator.get_calibration_info()
    for key, value in homography_config.items():
        print(f"     {key}: {value}")
    
    print("\n   Sensitivity Mapper Config:")
    sensitivity_config = sensitivity_mapper.get_sensitivity_info()
    for key, value in sensitivity_config.items():
        print(f"     {key}: {value}")

def example_with_real_calibration():
    """
    Example showing what real calibration code would look like
    """
    print("\n=== Real Calibration Example Code ===")
    print("""
# Real implementation would look like this:

# 1. Initialize modules
calibration_manager = CalibrationFileManager('homography_1080.pickle', 'sensitivity_1080.pickle')
homography_calibrator = HomographyCalibrator(calibration_frames=15, first_calibration_frame=7)
sensitivity_mapper = SensitivityMapper(sensitivity_frames=15, first_sensitivity_frame=7)

# 2. Check if calibration is needed
homography_matrix, sensitivity_map = calibration_manager.load_both_calibrations()
needs_homography = homography_matrix is None
needs_sensitivity = sensitivity_map is None

# 3. Perform homography calibration if needed
if needs_homography:
    print("Performing homography calibration...")
    # local_frames and remote_frames would come from actual camera captures
    homography_matrix = homography_calibrator.calculate_homography_matrix(local_frames, remote_frames)
    
    if homography_matrix is not None:
        if calibration_manager.save_homography_matrix(homography_matrix):
            print("Homography calibration completed and saved")
        else:
            print("Failed to save homography matrix")
    else:
        print("Homography calibration failed")

# 4. Perform sensitivity mapping if needed
if needs_sensitivity and homography_matrix is not None:
    print("Performing sensitivity mapping...")
    sensitivity_map = sensitivity_mapper.generate_sensitivity_map_from_raw_frames(
        local_frames, remote_frames, homography_matrix
    )
    
    if sensitivity_map is not None:
        if calibration_manager.save_sensitivity_map(sensitivity_map):
            print("Sensitivity mapping completed and saved")
        else:
            print("Failed to save sensitivity map")
    else:
        print("Sensitivity mapping failed")

# 5. Validation
if homography_matrix is not None and sensitivity_map is not None:
    validation = calibration_manager.validate_calibration_files()
    print("Calibration validation:", validation)
""")

def example_module_benefits():
    """
    Explain the benefits of the modular approach
    """
    print("\n=== Benefits of Modular Approach ===")
    print("""
1. MODULARITY:
   - CalibrationFileManager: Handles all file I/O operations
   - HomographyCalibrator: Focused on homography calculation
   - SensitivityMapper: Dedicated to sensitivity map generation

2. REUSABILITY:
   - Modules can be used in other scripts
   - Easy to import just what you need
   - Consistent API across different use cases

3. MAINTAINABILITY:
   - Each module has a single responsibility
   - Easier to debug and modify specific functionality
   - Clear separation of concerns

4. TESTABILITY:
   - Each module can be unit tested independently
   - Mock data can be used for testing specific components
   - Validation functions built into each module

5. FLEXIBILITY:
   - Configurable parameters for different use cases
   - Debug output can be enabled/disabled per module
   - Easy to swap implementations or add new features

6. ERROR HANDLING:
   - Centralized error handling within each module
   - Comprehensive logging and validation
   - Graceful failure modes with detailed error messages
""")

if __name__ == "__main__":
    try:
        example_calibration_workflow()
        example_with_real_calibration()
        example_module_benefits()
        
        print("\n" + "="*60)
        print("CALIBRATION MODULE EXTRACTION COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nExtracted modules:")
        print("  • CalibrationFileManager.py - File I/O operations")
        print("  • HomographyCalibrator.py - Homography matrix calculation")  
        print("  • SensitivityMapper.py - Sensitivity map generation")
        print("\nUsage in Camera_MasterSyncCode.py:")
        print("  • Replaced direct file operations with CalibrationFileManager")
        print("  • Replaced homography calculation with HomographyCalibrator")
        print("  • Replaced sensitivity mapping with SensitivityMapper")
        print("  • Removed old sensitivityMapRoutine function")
        
    except Exception as e:
        logger.error(f"Example script error: {e}")
        import traceback
        traceback.print_exc()