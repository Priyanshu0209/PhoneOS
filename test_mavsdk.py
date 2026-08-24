import asyncio
import mavsdk
s = mavsdk.System(mavsdk_server_address="127.0.0.1", port=50051)
async def run():
    print("trying to connect")
    try:
        await s.connect(system_address="serial:///dev/ttyUSB0:115200")
        print("connect didn't throw an error about arguments")
    except Exception as e:
        print("Error:", e)
asyncio.run(run())
