#!/usr/bin/env python3
"""
Sensitivity Map Generator Module

This module handles sensitivity map creation between two camera views
for enhanced difference detection in the bee monitoring system.

Author: Matthew Boillat
Date: October 2025
"""

import numpy as np
import cv2
import logging
from typing import List, Optional, Tuple
from alignImages import align_fromHomography

# Configure logging
logger = logging.getLogger(__name__)

class SensitivityMapper:
    """
    Handles sensitivity map generation between camera pairs
    """
    
    def __init__(self, 
                 sensitivity_frames: int = 15,
                 first_sensitivity_frame: int = 7,
                 debug_output: bool = True,
                 camera_resolution: Tuple[int, int] = (1920, 1080)):
        """
        Initialize the sensitivity mapper
        
        Args:
            sensitivity_frames: Total number of sensitivity frames to capture
            first_sensitivity_frame: Index of first frame to use for sensitivity calculation
            debug_output: Whether to save debug images
            camera_resolution: Camera resolution (width, height)
        """
        self.sensitivity_frames = sensitivity_frames
        self.first_sensitivity_frame = first_sensitivity_frame
        self.debug_output = debug_output
        self.camera_resolution = camera_resolution
    
    def save_debug_frames(self, 
                         local_frames: List[np.ndarray], 
                         remote_frames: List[np.ndarray],
                         difference_frames: List[np.ndarray]) -> None:
        """
        Save sensitivity calculation frames for debugging
        
        Args:
            local_frames: List of local camera frames
            remote_frames: List of remote camera frames
            difference_frames: List of calculated difference frames
        """
        if not self.debug_output:
            return
            
        try:
            # Save individual frame pairs and their differences
            for i, (local_frame, remote_frame, diff_frame) in enumerate(zip(local_frames, remote_frames, difference_frames)):
                cv2.imwrite(f'sensitivity_Local{i}.jpg', np.abs(local_frame))
                cv2.imwrite(f'sensitivity_Remote{i}.jpg', np.abs(remote_frame))
                cv2.imwrite(f'sensitivity_Diff{i}.jpg', np.uint8(np.abs(diff_frame)))
                
            logger.info(f"Saved {len(local_frames)} sensitivity debug frame sets")
            
        except Exception as e:
            logger.error(f"Error saving sensitivity debug frames: {e}")
    
    def create_sensitivity_visualizations(self, sensitivity_map: np.ndarray) -> bool:
        """
        Create and save sensitivity map visualization images
        
        Args:
            sensitivity_map: The calculated sensitivity map
            
        Returns:
            bool: True if visualizations were created successfully
        """
        try:
            # Create visualization images for each color channel
            height, width = self.camera_resolution[1], self.camera_resolution[0]
            sensitivity_image = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Blue channel visualization
            sensitivity_image[:,:,0] = np.uint8(sensitivity_map[:,:,0] * 255)
            cv2.imwrite('./sensitivityMatrixBlue.png', sensitivity_image)
            sensitivity_image[:,:,0] = 0
            
            # Green channel visualization
            sensitivity_image[:,:,1] = np.uint8(sensitivity_map[:,:,1] * 255)
            cv2.imwrite('./sensitivityMatrixGreen.png', sensitivity_image)
            sensitivity_image[:,:,1] = 0

            # Red channel visualization
            sensitivity_image[:,:,2] = np.uint8(sensitivity_map[:,:,2] * 255)
            cv2.imwrite('./sensitivityMatrixRed.png', sensitivity_image)
            
            logger.info("Sensitivity map visualizations created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating sensitivity visualizations: {e}")
            return False
    
    def align_frames_with_homography(self, 
                                   local_frames: List[np.ndarray], 
                                   remote_frames: List[np.ndarray],
                                   homography_matrix: np.ndarray) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Align local frames using homography matrix and prepare for sensitivity calculation
        
        Args:
            local_frames: List of local camera frames
            remote_frames: List of remote camera frames
            homography_matrix: Homography matrix for alignment
            
        Returns:
            tuple: (aligned_local_frames, processed_remote_frames)
        """
        try:
            processed_local_frames = []
            processed_remote_frames = []
            
            for i, (local_frame, remote_frame) in enumerate(zip(local_frames, remote_frames)):
                # Only process frames starting from FIRST_SENSITIVITY_FRAME
                if i >= self.first_sensitivity_frame:
                    # Align local frame using homography
                    aligned_local = align_fromHomography(local_frame, homography_matrix)
                    
                    if aligned_local is not None:
                        processed_local_frames.append(aligned_local)
                        processed_remote_frames.append(remote_frame)
                    else:
                        logger.warning(f"Failed to align local frame {i}")
            
            logger.info(f"Aligned {len(processed_local_frames)} frame pairs for sensitivity calculation")
            return processed_local_frames, processed_remote_frames
            
        except Exception as e:
            logger.error(f"Error aligning frames with homography: {e}")
            return [], []
    
    def calculate_sensitivity_map(self, 
                                local_frames: List[np.ndarray], 
                                remote_frames: List[np.ndarray]) -> Optional[np.ndarray]:
        """
        Calculate sensitivity map from aligned frame pairs
        
        Args:
            local_frames: List of aligned local camera frames
            remote_frames: List of remote camera frames
            
        Returns:
            np.ndarray: Calculated sensitivity map, or None if calculation failed
        """
        try:
            if not local_frames or not remote_frames:
                logger.error("No frames provided for sensitivity calculation")
                return None
            
            if len(local_frames) != len(remote_frames):
                logger.error(f"Frame count mismatch: local={len(local_frames)}, remote={len(remote_frames)}")
                return None
            
            print("Calculating sensitivity map from frame differences")
            
            # Calculate difference frames
            difference_frames = []
            for i, (local_frame, remote_frame) in enumerate(zip(local_frames, remote_frames)):
                difference_frame = np.float32(local_frame) - np.float32(remote_frame)
                difference_frames.append(difference_frame)
            
            # Save debug frames if enabled
            if self.debug_output:
                self.save_debug_frames(local_frames, remote_frames, difference_frames)
            
            # Calculate mean sensitivity map
            stacked_sensitivity = np.stack(difference_frames, axis=0)
            float_map = np.float32(np.mean(stacked_sensitivity, axis=0))
            float_map = np.abs(float_map)
            
            # Calculate reciprocal sensitivity map
            # +1 accounts for perfect match approaching 0, preventing division by zero
            sensitivity_map = np.reciprocal(float_map + 1)
            
            logger.info(f"Sensitivity map calculated from {len(difference_frames)} frame pairs")
            logger.info(f"Sensitivity map shape: {sensitivity_map.shape}")
            logger.info(f"Sensitivity map range: {np.min(sensitivity_map):.4f} to {np.max(sensitivity_map):.4f}")
            
            # Create visualization images
            self.create_sensitivity_visualizations(sensitivity_map)
            
            return sensitivity_map
            
        except Exception as e:
            logger.error(f"Error calculating sensitivity map: {e}")
            return None
    
    def generate_sensitivity_map_from_raw_frames(self, 
                                               local_frames: List[np.ndarray], 
                                               remote_frames: List[np.ndarray],
                                               homography_matrix: np.ndarray) -> Optional[np.ndarray]:
        """
        Complete sensitivity map generation pipeline from raw frames
        
        Args:
            local_frames: List of raw local camera frames
            remote_frames: List of raw remote camera frames
            homography_matrix: Homography matrix for alignment
            
        Returns:
            np.ndarray: Calculated sensitivity map, or None if generation failed
        """
        try:
            # Align frames using homography
            aligned_local_frames, processed_remote_frames = self.align_frames_with_homography(
                local_frames, remote_frames, homography_matrix
            )
            
            if not aligned_local_frames or not processed_remote_frames:
                logger.error("Failed to align frames for sensitivity calculation")
                return None
            
            # Calculate sensitivity map
            sensitivity_map = self.calculate_sensitivity_map(aligned_local_frames, processed_remote_frames)
            
            if sensitivity_map is not None:
                print("Sensitivity mapping complete")
            
            return sensitivity_map
            
        except Exception as e:
            logger.error(f"Error in sensitivity map generation pipeline: {e}")
            return None
    
    def validate_sensitivity_map(self, sensitivity_map: np.ndarray) -> bool:
        """
        Validate that the sensitivity map is reasonable
        
        Args:
            sensitivity_map: The sensitivity map to validate
            
        Returns:
            bool: True if map appears valid, False otherwise
        """
        try:
            if sensitivity_map is None:
                return False
            
            if not isinstance(sensitivity_map, np.ndarray):
                logger.error("Sensitivity map is not a numpy array")
                return False
            
            if len(sensitivity_map.shape) != 3:
                logger.error(f"Invalid sensitivity map shape: {sensitivity_map.shape}")
                return False
            
            # Check for NaN or infinite values
            if np.isnan(sensitivity_map).any():
                logger.error("Sensitivity map contains NaN values")
                return False
            
            if np.isinf(sensitivity_map).any():
                logger.error("Sensitivity map contains infinite values")
                return False
            
            # Check that values are in reasonable range (0 to 1 typically)
            if np.min(sensitivity_map) < 0:
                logger.warning(f"Sensitivity map contains negative values: min = {np.min(sensitivity_map)}")
            
            if np.max(sensitivity_map) > 10:  # Allow some flexibility but warn if extremely high
                logger.warning(f"Sensitivity map contains very high values: max = {np.max(sensitivity_map)}")
            
            logger.info("Sensitivity map validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Error validating sensitivity map: {e}")
            return False
    
    def get_sensitivity_info(self) -> dict:
        """
        Get information about sensitivity mapping parameters
        
        Returns:
            dict: Sensitivity mapping configuration information
        """
        return {
            'sensitivity_frames': self.sensitivity_frames,
            'first_sensitivity_frame': self.first_sensitivity_frame,
            'frames_used_for_calculation': self.sensitivity_frames - self.first_sensitivity_frame,
            'debug_output_enabled': self.debug_output,
            'camera_resolution': self.camera_resolution
        }


# Module-level convenience function for backward compatibility
def generate_sensitivity_map(local_frames: List[np.ndarray], 
                           remote_frames: List[np.ndarray],
                           homography_matrix: np.ndarray,
                           sensitivity_frames: int = 15,
                           first_sensitivity_frame: int = 7) -> Optional[np.ndarray]:
    """
    Generate sensitivity map using default mapper settings
    
    Args:
        local_frames: List of local camera frames
        remote_frames: List of remote camera frames
        homography_matrix: Homography matrix for alignment
        sensitivity_frames: Total number of sensitivity frames
        first_sensitivity_frame: Index of first frame to use
        
    Returns:
        np.ndarray: Sensitivity map, or None if generation failed
    """
    mapper = SensitivityMapper(sensitivity_frames, first_sensitivity_frame)
    return mapper.generate_sensitivity_map_from_raw_frames(
        local_frames, remote_frames, homography_matrix
    )


if __name__ == "__main__":
    # Example usage and testing
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create a sensitivity mapper
    mapper = SensitivityMapper(sensitivity_frames=10, first_sensitivity_frame=3)
    
    # Display configuration
    config = mapper.get_sensitivity_info()
    print("Sensitivity Mapper Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # Test with dummy data
    print("\nTesting with synthetic data...")
    
    # Create test frames (this would normally be real camera data)
    test_local_frames = [np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8) for _ in range(10)]
    test_remote_frames = [np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8) for _ in range(10)]
    test_homography = np.eye(3, dtype=np.float32)  # Identity matrix for testing
    
    print(f"Created {len(test_local_frames)} test frame pairs")
    
    # In real usage, you would use actual camera frames:
    # sensitivity_map = mapper.generate_sensitivity_map_from_raw_frames(
    #     test_local_frames, test_remote_frames, test_homography
    # )
    
    print("Module loaded successfully!")