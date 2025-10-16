import asyncio
import logging

# Pymodbus imports organized by module
from pymodbus.server import ModbusTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusDeviceContext
from pymodbus import ModbusDeviceIdentification

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("modbus-server")

# Constants
NUM_REGS = 50
HOST = "0.0.0.0" # Use to enable external connections
PORT = 5020  # Default port is 502, but 5020 avoids the need for root privileges.

def build_datastore() -> ModbusDeviceContext:
    """
    Creates and returns the data context for a single device.
    """
    discrete_inputs = [False] * NUM_REGS
    coils = [False] * NUM_REGS
    holding_registers = [i for i in range(NUM_REGS)]
    input_registers = [1000 + i for i in range(NUM_REGS)]

    store = ModbusDeviceContext(
        di=ModbusSequentialDataBlock(0, discrete_inputs),
        co=ModbusSequentialDataBlock(0, coils),
        hr=ModbusSequentialDataBlock(0, holding_registers),
        ir=ModbusSequentialDataBlock(0, input_registers),
    )
    return store

def build_identity():
    """Builds the Modbus device identification metadata."""
    identity = ModbusDeviceIdentification()
    identity.VendorName = "ExampleCorp"
    identity.ProductCode = "PMDB"
    identity.VendorUrl = "https://example.com"
    identity.ProductName = "Async Modbus Server"
    identity.ModelName = "pymodbus-async-3.x"
    identity.MajorMinorRevision = "3.x"
    return identity

async def coils_task(context: ModbusDeviceContext, period: float = 1.0):
    """
    Asynchronous task that toggles the state of the coils.
    """
    toggle_index = 0

    while True:
        try:
            address = 0
            count = 10
            
            rr = context.getValues(1, address, count)
            logger.info(f"Coils (0..9) before: {rr}")

            new_coils = list(rr)
            idx = toggle_index % count
            new_coils[idx] = not new_coils[idx]

            context.setValues(15, address, new_coils)

            rr_after = context.getValues(1, address, count)
            logger.info(f"Coils (0..9) after: {rr_after} (toggled idx={idx})")

            toggle_index += 1
        except Exception as e:
            logger.exception(f"Error in coils task: {e}")

        await asyncio.sleep(period)

async def holding_registers_task(context: ModbusDeviceContext, period: float = 2.0):
    """
    Asynchronous task that increments the holding registers.
    """
    while True:
        try:
            address = 0
            count = 10
            
            hr_vals = context.getValues(3, address, count)
            logger.info(f"HR (0..9) before: {hr_vals}")

            if hr_vals:
                new_vals = list(hr_vals)
                new_vals[0] = (new_vals[0] + 1) & 0xFFFF
                
                context.setValues(16, address, new_vals)

            hr_after = context.getValues(3, address, count)
            logger.info(f"HR (0..9) after: {hr_after}")
        except Exception as e:
            logger.exception(f"Error in holding registers task: {e}")

        await asyncio.sleep(period)

async def main():
    context = build_datastore()
    identity = build_identity()

    server = ModbusTcpServer(
        context=context,
        identity=identity,
        address=(HOST, PORT)
    )

    logger.info(f"Modbus TCP server started on {HOST}:{PORT}")

    task1 = asyncio.create_task(coils_task(context, period=1.0))
    task2 = asyncio.create_task(holding_registers_task(context, period=2.0))

    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        logger.info("Server cancelled, shutting down...")
    finally:
        task1.cancel()
        task2.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)
        await server.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Terminated by user (Ctrl+C)")