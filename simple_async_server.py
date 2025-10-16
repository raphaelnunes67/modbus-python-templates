import asyncio
import logging
from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.transaction import ModbusSocketFramer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("modbus-server")

# Constants
NUM_REGS = 50
HOST = "0.0.0.0" # Use to enable external connections
PORT = 5020  # The default port is 502, but you can use 5020 to avoid root privileges.

def build_datastore():
    """
    Creates a datastore with 50 registers of each type.
    - di: Discrete Inputs (read-only, 0/1)
    - co: Coils (read/write, 0/1)
    - hr: Holding Registers (read/write, 16-bit)
    - ir: Input Registers (read-only, 16-bit)
    """
    # Initialize with some values for visibility
    discrete_inputs = [0] * NUM_REGS
    coils = [0] * NUM_REGS
    holding_registers = [i for i in range(NUM_REGS)]
    input_registers = [1000 + i for i in range(NUM_REGS)]

    store = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, discrete_inputs),
        co=ModbusSequentialDataBlock(0, coils),
        hr=ModbusSequentialDataBlock(0, holding_registers),
        ir=ModbusSequentialDataBlock(0, input_registers),
        zero_mode=True,  # addressing starts at 0
    )
    context = ModbusServerContext(slaves=store, single=True)
    return context

def build_identity():
    """Builds Modbus device identification metadata."""
    identity = ModbusDeviceIdentification()
    identity.VendorName = "ExampleCorp"
    identity.ProductCode = "PMDB"
    identity.VendorUrl = "https://example.com"
    identity.ProductName = "Async Modbus Server"
    identity.ModelName = "pymodbus-async-3.x"
    identity.MajorMinorRevision = "3.x"
    return identity

async def coils_task(context: ModbusServerContext, period: float = 1.0):
    """
    Async task that:
    - Reads the first 10 coils.
    - Toggles one coil per iteration (round-robin).
    - Writes back the updated values.
    - Logs the state periodically.
    """
    slave_id = 0x00  # when single=True, the identifier is ignored internally
    toggle_index = 0

    while True:
        try:
            # Read 10 coils starting at address 0
            rr = context[slave_id].getValues(function=1, address=0, count=10)  # 1 = Read Coils
            logger.info(f"Coils (0..9) before: {rr}")

            # Toggle one coil at a time (cyclic)
            new_coils = list(rr)
            idx = toggle_index % 10
            new_coils[idx] = 0 if new_coils[idx] else 1

            # Write back the 10 coils
            context[slave_id].setValues(function=5, address=0, values=new_coils)  # 5 = Write Single Coil / block

            # Verify write
            rr_after = context[slave_id].getValues(function=1, address=0, count=10)
            logger.info(f"Coils (0..9) after: {rr_after} (toggled idx={idx})")

            toggle_index += 1
        except Exception as e:
            logger.exception(f"Error in coils task: {e}")

        await asyncio.sleep(period)

async def holding_registers_task(context: ModbusServerContext, period: float = 2.0):
    """
    Async task that:
    - Reads 10 holding registers.
    - Increments the first register and writes back the block.
    """
    slave_id = 0x00

    while True:
        try:
            # Read 10 holding registers starting at 0
            hr_vals = context[slave_id].getValues(function=3, address=0, count=10)  # 3 = Read Holding Registers
            logger.info(f"HR (0..9) before: {hr_vals}")

            # Increment the first value and write back the block
            if hr_vals:
                hr_vals[0] = (hr_vals[0] + 1) & 0xFFFF  # 16-bit wrap
                context[slave_id].setValues(function=6, address=0, values=hr_vals)  # 6 = Write Single Register / block

            hr_after = context[slave_id].getValues(function=3, address=0, count=10)
            logger.info(f"HR (0..9) after: {hr_after}")
        except Exception as e:
            logger.exception(f"Error in holding registers task: {e}")

        await asyncio.sleep(period)

async def main():
    context = build_datastore()
    identity = build_identity()

    # Start the Async TCP server
    server = await StartAsyncTcpServer(
        context=context,
        identity=identity,
        host=HOST,
        port=PORT,
        framer=ModbusSocketFramer,
        allow_reuse_address=True,
        defer_start=True,  # gives us lifecycle control
    )

    logger.info(f"Modbus TCP server started at {HOST}:{PORT}")

    # Create periodic read/write tasks
    task1 = asyncio.create_task(coils_task(context, period=1.0))
    task2 = asyncio.create_task(holding_registers_task(context, period=2.0))

    try:
        # Run the server; this call blocks until canceled
        await server.serve_forever()
    except asyncio.CancelledError:
        logger.info("Server canceled, shutting down...")
    finally:
        task1.cancel()
        task2.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Terminated by user (Ctrl+C)")