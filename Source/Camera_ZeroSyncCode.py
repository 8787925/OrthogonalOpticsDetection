import asyncio
import websockets
import numpy as np
import json

# Define the function to be executed
def my_function():
    # Example function that returns a numpy array
    return np.array([[1, 2, 3, 4, 5],[6, 7, 8, 9, 10]])

# WebSocket server handler
async def handler(websocket, path):
    async for message in websocket:
        command = json.loads(message)
        if command['action'] == 'execute_function':
            # Execute the function and get the numpy array
            result_array = my_function()
            # Convert the numpy array to a list for JSON serialization
            result_list = result_array.tolist()
            # Send the result back to the client
            await websocket.send(json.dumps(result_list))

# Start the WebSocket server
async def main():
    async with websockets.serve(handler, "localhost", 8765):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())