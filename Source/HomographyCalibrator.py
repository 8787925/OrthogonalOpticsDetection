#!/usr/bin/env python3
"""
Homography Calibration Module

This module handles homography matrix calculation between two camera views
for the bee monitoring camera synchronization system.

Author: Matthew Boillat
Date: October 2025
"""

import numpy as np
import cv2
import logging
from typing import List, Optional, Tuple
from alignImages import align_images

# Configure logging
logger = logging.getLogger(__name__)

class HomographyCalibrator:
    """
    Handles homography matrix calculation between camera pairs
    """
    
    def __init__(self, 
                 calibration_frames: int = 15,
                 first_calibration_frame: int = 1,
                 debug_output: bool = True):
        """
        Initialize the homography calibrator
        
        Args:
            calibration_frames: Total number of calibration frames to capture
            first_calibration_frame: Index of first frame to use for calibration
            debug_output: Whether to save debug images
        """
        self.calibration_frames = calibration_frames
        self.first_calibration_frame = first_calibration_frame
        self.debug_output = debug_output
    
    def save_debug_frames(self, local_frames: List[np.ndarray], remote_frames: List[np.ndarray]) -> None:
        """
        Save calibration frames for debugging purposes
        
        Args:
            local_frames: List of local camera frames
            remote_frames: List of remote camera frames
        """
        if not self.debug_output:
            return
            
        try:
            # Save local frames
            for i, local_frame in enumerate(local_frames):
                cv2.imwrite(f'localCalImg{i}.jpg', local_frame)
            
            # Save remote frames
            for i, remote_frame in enumerate(remote_frames):
                cv2.imwrite(f'remoteCalImg{i}.jpg', remote_frame)
                
            logger.info(f"Saved {len(local_frames)} local and {len(remote_frames)} remote debug frames")
            
        except Exception as e:
            logger.error(f"Error saving debug frames: {e}")
    
    def calculate_homography_matrix(self, 
                                   local_frames: List[np.ndarray], 
                                   remote_frames: List[np.ndarray]) -> Optional[np.ndarray]:
        """
        Calculate homography matrix from frame pairs
        
        Args:
            local_frames: List of local camera frames
            remote_frames: List of remote camera frames
            
        Returns:
            np.ndarray: Average homography matrix, or None if calculation failed
        """
        try:
            if len(local_frames) != len(remote_frames):
                logger.error(f"Frame count mismatch: local={len(local_frames)}, remote={len(remote_frames)}")
                return None
            
            if len(local_frames) < self.calibration_frames:
                logger.error(f"Insufficient frames: got {len(local_frames)}, need {self.calibration_frames}")
                return None
            
            # Save debug frames if enabled
            self.save_debug_frames(local_frames, remote_frames)
            
            print("Calculating Homography")
            
            # Use frames starting from FIRST_CALIBRATION_FRAME for homography calculation
            calibration_local_frames = local_frames[self.first_calibration_frame:]
            calibration_remote_frames = remote_frames[self.first_calibration_frame:]
            
            # Calculate homography matrices for each frame pair
            homography_matrices = []
            for j, (local_frame, remote_frame) in enumerate(zip(calibration_local_frames, calibration_remote_frames)):
                homography_matrix = align_images(local_frame, remote_frame)
                
                if homography_matrix is not None:
                    homography_matrices.append(homography_matrix)
                    print(f'Frame comparison {j} completed out of {len(calibration_local_frames)}')
                else:
                    logger.warning(f"Failed to calculate homography for frame pair {j}")
            
            if not homography_matrices:
                logger.error("No valid homography matrices calculated")
                return None
            
            if len(homography_matrices) < len(calibration_local_frames) / 2:
                logger.warning(f"Only {len(homography_matrices)} out of {len(calibration_local_frames)} frame pairs produced valid homographies")
            
            # Calculate average homography matrix
            average_homography = np.mean(homography_matrices, axis=0)
            
            logger.info(f"Homography calculation complete. Used {len(homography_matrices)} frame pairs.")
            logger.info(f"Average homography matrix shape: {average_homography.shape}")
            
            return average_homography
            
        except Exception as e:
            logger.error(f"Error calculating homography matrix: {e}")
            return None
    
    def validate_homography_matrix(self, homography_matrix: np.ndarray) -> bool:
        """
        Validate that the homography matrix is reasonable
        
        Args:
            homography_matrix: The homography matrix to validate
            
        Returns:
            bool: True if matrix appears valid, False otherwise
        """
        try:
            if homography_matrix is None:
                return False
            
            if not isinstance(homography_matrix, np.ndarray):
                logger.error("Homography matrix is not a numpy array")
                return False
            
            if homography_matrix.shape != (3, 3):
                logger.error(f"Invalid homography matrix shape: {homography_matrix.shape}")
                return False
            
            # Check for NaN or infinite values
            if np.isnan(homography_matrix).any():
                logger.error("Homography matrix contains NaN values")
                return False
            
            if np.isinf(homography_matrix).any():
                logger.error("Homography matrix contains infinite values")
                return False
            
            # Check determinant (should not be zero for invertible matrix)
            det = np.linalg.det(homography_matrix)
            if abs(det) < 1e-10:
                logger.error(f"Homography matrix is nearly singular (det={det})")
                return False
            
            # Check that bottom-right element is reasonable (typically should be close to 1)
            if abs(homography_matrix[2, 2]) < 1e-6:
                logger.error(f"Invalid homography normalization: bottom-right element = {homography_matrix[2, 2]}")
                return False
            
            logger.info("Homography matrix validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Error validating homography matrix: {e}")
            return False
    
    def apply_homography_to_frame(self, 
                                  frame: np.ndarray, 
                                  homography_matrix: np.ndarray,
                                  output_shape: Optional[Tuple[int, int]] = None) -> Optional[np.ndarray]:
        """
        Apply homography transformation to a single frame
        
        Args:
            frame: Input frame to transform
            homography_matrix: Homography matrix to apply
            output_shape: Output image size (width, height). If None, uses input frame size
            
        Returns:
            np.ndarray: Transformed frame, or None if transformation failed
        """
        try:
            if not self.validate_homography_matrix(homography_matrix):
                return None
            
            if output_shape is None:
                if len(frame.shape) == 3:
                    height, width = frame.shape[:2]
                else:
                    height, width = frame.shape
                output_shape = (width, height)
            
            # Apply perspective transformation
            transformed_frame = cv2.warpPerspective(frame, homography_matrix, output_shape)
            
            return transformed_frame
            
        except Exception as e:
            logger.error(f"Error applying homography to frame: {e}")
            return None
    
    def get_calibration_info(self) -> dict:
        """
        Get information about calibration parameters
        
        Returns:
            dict: Calibration configuration information
        """
        return {
            'calibration_frames': self.calibration_frames,
            'first_calibration_frame': self.first_calibration_frame,
            'frames_used_for_calculation': self.calibration_frames - self.first_calibration_frame,
            'debug_output_enabled': self.debug_output
        }


# Module-level convenience functions for backward compatibility
def calculate_homography_from_frames(local_frames: List[np.ndarray], 
                                   remote_frames: List[np.ndarray],
                                   calibration_frames: int = 15,
                                   first_calibration_frame: int = 7) -> Optional[np.ndarray]:
    """
    Calculate homography matrix using default calibrator settings
    
    Args:
        local_frames: List of local camera frames
        remote_frames: List of remote camera frames
        calibration_frames: Total number of calibration frames
        first_calibration_frame: Index of first frame to use
        
    Returns:
        np.ndarray: Homography matrix, or None if calculation failed
    """
    calibrator = HomographyCalibrator(calibration_frames, first_calibration_frame)
    return calibrator.calculate_homography_matrix(local_frames, remote_frames)


def apply_homography_transformation(frame: np.ndarray, 
                                  homography_matrix: np.ndarray) -> Optional[np.ndarray]:
    """
    Apply homography transformation to a frame using default settings
    
    Args:
        frame: Input frame to transform
        homography_matrix: Homography matrix to apply
        
    Returns:
        np.ndarray: Transformed frame, or None if transformation failed
    """
    calibrator = HomographyCalibrator()
    return calibrator.apply_homography_to_frame(frame, homography_matrix)


if __name__ == "__main__":
    # Example usage and testing
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create a homography calibrator
    calibrator = HomographyCalibrator(calibration_frames=10, first_calibration_frame=3)
    
    # Display configuration
    config = calibrator.get_calibration_info()
    print("Homography Calibrator Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # Test with dummy data
    print("\nTesting with synthetic data...")
    
    # Create test frames (this would normally be real camera data)
    test_local_frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(10)]
    test_remote_frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(10)]
    
    print(f"Created {len(test_local_frames)} test frame pairs")
    
    # In real usage, you would use actual camera frames:
    # result_matrix = calibrator.calculate_homography_matrix(test_local_frames, test_remote_frames)
    
    print("Module loaded successfully!")