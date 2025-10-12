#!/usr/bin/env python3
"""
Calibration File Manager Module

This module handles all calibration file operations including loading and saving
homography matrices and sensitivity maps for the bee monitoring camera system.

Author: Matthew Boillat
Date: October 2025
"""

import os
import pickle
import numpy as np
import logging
from typing import Optional, Tuple, Any

# Configure logging
logger = logging.getLogger(__name__)

class CalibrationFileManager:
    """
    Manages calibration file operations for camera synchronization system
    """
    
    def __init__(self, 
                 homography_filename: str = 'wallCalibration_image_1080.pickle',
                 sensitivity_filename: str = 'sensitivityMap_1080.pickle'):
        """
        Initialize the calibration file manager
        
        Args:
            homography_filename: Name of the homography calibration file
            sensitivity_filename: Name of the sensitivity map file
        """
        self.homography_filename = homography_filename
        self.sensitivity_filename = sensitivity_filename
    
    def homography_file_exists(self) -> bool:
        """
        Check if homography calibration file exists
        
        Returns:
            bool: True if file exists, False otherwise
        """
        return os.path.exists(self.homography_filename)
    
    def sensitivity_file_exists(self) -> bool:
        """
        Check if sensitivity map file exists
        
        Returns:
            bool: True if file exists, False otherwise
        """
        return os.path.exists(self.sensitivity_filename)
    
    def load_homography_matrix(self) -> Optional[np.ndarray]:
        """
        Load homography matrix from file
        
        Returns:
            np.ndarray: Homography matrix if successful, None if failed
        """
        try:
            if not self.homography_file_exists():
                logger.warning(f"Homography file {self.homography_filename} does not exist")
                return None
            
            with open(self.homography_filename, 'rb') as f:
                homography_matrix = pickle.load(f)
            
            logger.info(f"Successfully loaded homography matrix from {self.homography_filename}")
            return homography_matrix
            
        except Exception as e:
            logger.error(f"Error loading homography matrix: {e}")
            return None
    
    def save_homography_matrix(self, homography_matrix: np.ndarray) -> bool:
        """
        Save homography matrix to file
        
        Args:
            homography_matrix: The homography matrix to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.homography_filename, 'wb') as f:
                pickle.dump(homography_matrix, f)
            
            logger.info(f"Successfully saved homography matrix to {self.homography_filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving homography matrix: {e}")
            return False
    
    def load_sensitivity_map(self) -> Optional[np.ndarray]:
        """
        Load sensitivity map from file
        
        Returns:
            np.ndarray: Sensitivity map if successful, None if failed
        """
        try:
            if not self.sensitivity_file_exists():
                logger.warning(f"Sensitivity map file {self.sensitivity_filename} does not exist")
                return None
            
            with open(self.sensitivity_filename, 'rb') as f:
                sensitivity_map = pickle.load(f)
            
            logger.info(f"Successfully loaded sensitivity map from {self.sensitivity_filename}")
            return sensitivity_map
            
        except Exception as e:
            logger.error(f"Error loading sensitivity map: {e}")
            return None
    
    def save_sensitivity_map(self, sensitivity_map: np.ndarray) -> bool:
        """
        Save sensitivity map to file
        
        Args:
            sensitivity_map: The sensitivity map to save
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.sensitivity_filename, 'wb') as f:
                pickle.dump(sensitivity_map, f)
            
            logger.info(f"Successfully saved sensitivity map to {self.sensitivity_filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving sensitivity map: {e}")
            return False
    
    def get_calibration_status(self) -> dict:
        """
        Get the current calibration status
        
        Returns:
            dict: Status of both calibration files
        """
        return {
            'homography_exists': self.homography_file_exists(),
            'sensitivity_exists': self.sensitivity_file_exists(),
            'homography_filename': self.homography_filename,
            'sensitivity_filename': self.sensitivity_filename,
            'fully_calibrated': self.homography_file_exists() and self.sensitivity_file_exists()
        }
    
    def load_both_calibrations(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Load both homography matrix and sensitivity map
        
        Returns:
            tuple: (homography_matrix, sensitivity_map) - either can be None if not found
        """
        homography_matrix = self.load_homography_matrix()
        sensitivity_map = self.load_sensitivity_map()
        
        return homography_matrix, sensitivity_map
    
    def save_both_calibrations(self, 
                              homography_matrix: np.ndarray, 
                              sensitivity_map: np.ndarray) -> Tuple[bool, bool]:
        """
        Save both homography matrix and sensitivity map
        
        Args:
            homography_matrix: The homography matrix to save
            sensitivity_map: The sensitivity map to save
            
        Returns:
            tuple: (homography_success, sensitivity_success)
        """
        homography_success = self.save_homography_matrix(homography_matrix)
        sensitivity_success = self.save_sensitivity_map(sensitivity_map)
        
        return homography_success, sensitivity_success
    
    def backup_calibration_files(self, backup_suffix: str = '_backup') -> bool:
        """
        Create backup copies of existing calibration files
        
        Args:
            backup_suffix: Suffix to add to backup files
            
        Returns:
            bool: True if backup was successful
        """
        try:
            backup_success = True
            
            if self.homography_file_exists():
                backup_name = self.homography_filename.replace('.pickle', f'{backup_suffix}.pickle')
                homography_matrix = self.load_homography_matrix()
                if homography_matrix is not None:
                    with open(backup_name, 'wb') as f:
                        pickle.dump(homography_matrix, f)
                    logger.info(f"Backed up homography to {backup_name}")
                else:
                    backup_success = False
            
            if self.sensitivity_file_exists():
                backup_name = self.sensitivity_filename.replace('.pickle', f'{backup_suffix}.pickle')
                sensitivity_map = self.load_sensitivity_map()
                if sensitivity_map is not None:
                    with open(backup_name, 'wb') as f:
                        pickle.dump(sensitivity_map, f)
                    logger.info(f"Backed up sensitivity map to {backup_name}")
                else:
                    backup_success = False
            
            return backup_success
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False
    
    def delete_calibration_files(self) -> bool:
        """
        Delete existing calibration files (useful for forcing recalibration)
        
        Returns:
            bool: True if deletion was successful
        """
        try:
            deleted_files = []
            
            if self.homography_file_exists():
                os.remove(self.homography_filename)
                deleted_files.append(self.homography_filename)
                logger.info(f"Deleted {self.homography_filename}")
            
            if self.sensitivity_file_exists():
                os.remove(self.sensitivity_filename)
                deleted_files.append(self.sensitivity_filename)
                logger.info(f"Deleted {self.sensitivity_filename}")
            
            if deleted_files:
                logger.info(f"Successfully deleted calibration files: {deleted_files}")
            else:
                logger.info("No calibration files to delete")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting calibration files: {e}")
            return False
    
    def validate_calibration_files(self) -> dict:
        """
        Validate that calibration files can be loaded and contain valid data
        
        Returns:
            dict: Validation results for both files
        """
        validation_results = {
            'homography_valid': False,
            'sensitivity_valid': False,
            'homography_shape': None,
            'sensitivity_shape': None,
            'errors': []
        }
        
        # Validate homography matrix
        try:
            homography_matrix = self.load_homography_matrix()
            if homography_matrix is not None:
                if isinstance(homography_matrix, np.ndarray) and homography_matrix.shape == (3, 3):
                    validation_results['homography_valid'] = True
                    validation_results['homography_shape'] = homography_matrix.shape
                else:
                    validation_results['errors'].append("Homography matrix has invalid shape")
            else:
                validation_results['errors'].append("Could not load homography matrix")
        except Exception as e:
            validation_results['errors'].append(f"Homography validation error: {e}")
        
        # Validate sensitivity map
        try:
            sensitivity_map = self.load_sensitivity_map()
            if sensitivity_map is not None:
                if isinstance(sensitivity_map, np.ndarray) and len(sensitivity_map.shape) == 3:
                    validation_results['sensitivity_valid'] = True
                    validation_results['sensitivity_shape'] = sensitivity_map.shape
                else:
                    validation_results['errors'].append("Sensitivity map has invalid shape")
            else:
                validation_results['errors'].append("Could not load sensitivity map")
        except Exception as e:
            validation_results['errors'].append(f"Sensitivity validation error: {e}")
        
        return validation_results


# Global instance for backward compatibility
# This allows existing code to use the module functions directly
_default_manager = CalibrationFileManager()

# Module-level convenience functions for backward compatibility
def load_homography_matrix() -> Optional[np.ndarray]:
    """Load homography matrix using default manager"""
    return _default_manager.load_homography_matrix()

def save_homography_matrix(homography_matrix: np.ndarray) -> bool:
    """Save homography matrix using default manager"""
    return _default_manager.save_homography_matrix(homography_matrix)

def load_sensitivity_map() -> Optional[np.ndarray]:
    """Load sensitivity map using default manager"""
    return _default_manager.load_sensitivity_map()

def save_sensitivity_map(sensitivity_map: np.ndarray) -> bool:
    """Save sensitivity map using default manager"""
    return _default_manager.save_sensitivity_map(sensitivity_map)

def homography_file_exists() -> bool:
    """Check if homography file exists using default manager"""
    return _default_manager.homography_file_exists()

def sensitivity_file_exists() -> bool:
    """Check if sensitivity file exists using default manager"""
    return _default_manager.sensitivity_file_exists()

def get_calibration_status() -> dict:
    """Get calibration status using default manager"""
    return _default_manager.get_calibration_status()


if __name__ == "__main__":
    # Example usage and testing
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create a calibration file manager
    manager = CalibrationFileManager()
    
    # Check current status
    status = manager.get_calibration_status()
    print("Current calibration status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    # Validate existing files if they exist
    if status['homography_exists'] or status['sensitivity_exists']:
        validation = manager.validate_calibration_files()
        print("\nValidation results:")
        for key, value in validation.items():
            print(f"  {key}: {value}")