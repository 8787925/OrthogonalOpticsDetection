import asyncio
import websockets
import json
import numpy as np

async def client():
    async with websockets.connect("ws://localhost:8765") as websocket:
        # Send command to execute function
        command = {'action': 'execute_function'}
        await websocket.send(json.dumps(command))

        # Receive and print the result
        result = await websocket.recv()
        result_array = np.array(json.loads(result))
        print("Received numpy array:", result_array)

if __name__ == "__main__":
    asyncio.run(client())