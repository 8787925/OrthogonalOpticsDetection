#!/usr/bin/env python3
"""
Test script for WebSocket connection recovery
This script tests the robustness of the camera synchronization system
"""

import asyncio
import websockets
import json
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SERVER_URI = "ws://localhost:18873"

async def test_basic_connection():
    """Test basic connection and commands"""
    logger.info("Testing basic connection...")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Test ping
            await ws.send(json.dumps({"action": "ping"}))
            response = await ws.recv()
            print(f"Ping response: {response}")
            
            # Test reset
            await ws.send(json.dumps({"action": "reset"}))
            response = await ws.recv()
            print(f"Reset response: {response}")
            
            # Test camera start
            await ws.send(json.dumps({"action": "start_camera"}))
            response = await ws.recv()
            print(f"Start camera response: {response}")
            
            # Test LED control
            await ws.send(json.dumps({"action": "SET_LED_COLOR", "color": [100, 20, 50]}))
            response = await ws.recv()
            print(f"Set LED color response: {response}")
            
            await ws.send(json.dumps({"action": "LED_ON"}))
            print("LED turned on")
            
            await asyncio.sleep(2)
            
            await ws.send(json.dumps({"action": "LED_OFF"}))
            print("LED turned off")
            
            # Test camera off
            await ws.send(json.dumps({"action": "CAMERA_OFF"}))
            print("Camera turned off")
            
        logger.info("Basic connection test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Basic connection test failed: {e}")
        return False

async def test_connection_recovery():
    """Test connection recovery after disconnection"""
    logger.info("Testing connection recovery...")
    
    try:
        # First connection
        async with websockets.connect(SERVER_URI) as ws1:
            await ws1.send(json.dumps({"action": "start_camera"}))
            response = await ws1.recv()
            print(f"First connection - start camera: {response}")
            
            # Simulate disconnection by closing connection
            await ws1.close()
            logger.info("First connection closed")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Second connection (should work cleanly)
        async with websockets.connect(SERVER_URI) as ws2:
            await ws2.send(json.dumps({"action": "reset"}))
            response = await ws2.recv()
            print(f"Second connection - reset: {response}")
            
            await ws2.send(json.dumps({"action": "start_camera"}))
            response = await ws2.recv()
            print(f"Second connection - start camera: {response}")
            
        logger.info("Connection recovery test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Connection recovery test failed: {e}")
        return False

async def test_invalid_commands():
    """Test handling of invalid commands"""
    logger.info("Testing invalid command handling...")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Test invalid JSON
            await ws.send("invalid json")
            response = await ws.recv()
            print(f"Invalid JSON response: {response}")
            
            # Test unknown action
            await ws.send(json.dumps({"action": "unknown_action"}))
            response = await ws.recv()
            print(f"Unknown action response: {response}")
            
            # Test missing action
            await ws.send(json.dumps({"data": "no action"}))
            response = await ws.recv()
            print(f"Missing action response: {response}")
            
        logger.info("Invalid command test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Invalid command test failed: {e}")
        return False

async def main():
    """Run all tests"""
    logger.info("Starting WebSocket connection recovery tests")
    
    tests = [
        ("Basic Connection", test_basic_connection),
        ("Connection Recovery", test_connection_recovery),
        ("Invalid Commands", test_invalid_commands),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} Test")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name} test PASSED")
            else:
                logger.error(f"❌ {test_name} test FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} test ERROR: {e}")
            results.append((test_name, False))
        
        # Wait between tests
        await asyncio.sleep(1)
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed!")
        return True
    else:
        logger.error("❌ Some tests failed")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        exit(1)
    except Exception as e:
        logger.error(f"Test runner error: {e}")
        exit(1)