# test_camera_slave_sync.py
import asyncio
import websockets
import json

SERVER_URI = "ws://localhost:18873"  # Change if running on a different host

async def test_sequence():
    async with websockets.connect(SERVER_URI) as ws:
        # Start camera
        await ws.send(json.dumps({"action": "start_camera"}))
        print("start_camera:", await ws.recv())

        # Set LED color
        await ws.send(json.dumps({"action": "SET_LED_COLOR", "color": [100, 20, 50]}))
        print("SET_LED_COLOR:", await ws.recv())

        # Turn LED on
        await ws.send(json.dumps({"action": "LED_ON"}))
        # No response expected

        # Capture frame
        await ws.send(json.dumps({"action": "capture"}))
        # Receive frame data in chunks until "END"
        while True:
            chunk = await ws.recv()
            if chunk == b"END":
                print("Received END of frame data")
                break
            print(f"Received chunk of size {len(chunk)}")

        # Turn LED off
        await ws.send(json.dumps({"action": "LED_OFF"}))
        # No response expected

        # Stop camera
        await ws.send(json.dumps({"action": "CAMERA_OFF"}))
        # No response expected

asyncio.run(test_sequence())