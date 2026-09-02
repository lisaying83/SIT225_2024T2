import sys
import json
import traceback
from pathlib import Path
from datetime import datetime
from collections import deque
from threading import Lock

from arduino_iot_cloud import ArduinoCloudClient

# ============================================================
# Load Arduino IoT Cloud credentials from settings.json
# ============================================================

SETTINGS_FILE = Path(__file__).with_name("settings.json")


def load_settings():
    """
    Load Arduino IoT Cloud credentials from settings.json.

    Expected format:
    {
        "device_id": "...",
        "secret_key": "..."
    }
    """
    if not SETTINGS_FILE.exists():
        raise FileNotFoundError(
            f"Settings file not found: {SETTINGS_FILE}\n"
            "Create settings.json in the same folder as this script."
        )

    with SETTINGS_FILE.open("r", encoding="utf-8") as file:
        settings = json.load(file)

    device_id = settings.get("device_id")
    secret_key = settings.get("secret_key")

    if not device_id or not secret_key:
        raise ValueError(
            "settings.json must contain both "
            "'device_id' and 'secret_key'."
        )

    return device_id, secret_key


DEVICE_ID, SECRET_KEY = load_settings()

# Store all three variables in one CSV file
DATA_FILENAME = "accelerometer_xyz.csv"
data_file = None

# Latest sensor values
latest_x = None
latest_y = None
latest_z = None

# Check whether a new value has been received
x_received = False
y_received = False
z_received = False

# Maximum number of complete accelerometer samples kept in memory.
# When the buffer becomes full, deque automatically removes
# the oldest sample before adding the newest one.
BUFFER_SIZE = 100

# Each item is stored as:
# (timestamp, x, y, z)
live_buffer = deque(maxlen=BUFFER_SIZE)

# Prevents operations from changing/reading the buffer at exactly the same time.
buffer_lock = Lock()


def add_to_live_buffer(timestamp, x, y, z):
    """
    Add one synchronized accelerometer sample to the live buffer.

    Parameters:
        timestamp (str): Time when the complete XYZ sample is created.
        x (float): Accelerometer X value.
        y (float): Accelerometer Y value.
        z (float): Accelerometer Z value.
    """
    with buffer_lock:
        live_buffer.append((timestamp, x, y, z))


def get_buffer_snapshot():
    """
    Return a safe copy of the current live buffer.

    This function will be useful in Stage 3 when Plotly Dash
    needs to read the latest sensor samples.
    """
    with buffer_lock:
        return list(live_buffer)


def save_data_if_ready():
    """
    Save and buffer data only when new X, Y and Z values
    have all been received.
    """
    global x_received, y_received, z_received

    if x_received and y_received and z_received:

        # Create one timestamp for the complete XYZ set
        timestamp = datetime.now().isoformat(timespec="seconds")

        # Add complete XYZ sample to rolling buffer
        add_to_live_buffer(
            timestamp,
            latest_x,
            latest_y,
            latest_z
        )

        # Create CSV line:
        # <timestamp>,<x>,<y>,<z>
        csv_line = f"{timestamp},{latest_x},{latest_y},{latest_z}\n"

        if data_file is not None:
            data_file.write(csv_line)
            data_file.flush()

        # Show current buffer size for testing
        with buffer_lock:
            current_buffer_size = len(live_buffer)

        print(
            f"Saved: {timestamp}, "
            f"X={latest_x}, Y={latest_y}, Z={latest_z} "
            f"| Buffer: {current_buffer_size}/{BUFFER_SIZE}"
        )

        # Reset flags.
        # Wait for another complete X, Y and Z set.
        x_received = False
        y_received = False
        z_received = False


def on_accelerometer_x_changed(client, value):
    """Run when a new Accelerometer_X value is received."""
    global latest_x, x_received

    latest_x = value
    x_received = True

    print(f"New Accelerometer_X: {value}")

    save_data_if_ready()


def on_accelerometer_y_changed(client, value):
    """Run when a new Accelerometer_Y value is received."""
    global latest_y, y_received

    latest_y = value
    y_received = True

    print(f"New Accelerometer_Y: {value}")

    save_data_if_ready()


def on_accelerometer_z_changed(client, value):
    """Run when a new Accelerometer_Z value is received."""
    global latest_z, z_received

    latest_z = value
    z_received = True

    print(f"New Accelerometer_Z: {value}")

    save_data_if_ready()


def main():
    global data_file

    print("main() function")
    print(f"Live buffer size: {BUFFER_SIZE} samples")

    # Open one CSV file in append mode
    data_file = open(DATA_FILENAME, mode="a", newline="")

    # Write header only when the file is empty
    if data_file.tell() == 0:
        data_file.write("timestamp,x,y,z\n")
        data_file.flush()

    # Instantiate Arduino Cloud client
    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        username=DEVICE_ID,
        password=SECRET_KEY
    )

    # Register Accelerometer X
    client.register(
        "Accelerometer_X",
        value=None,
        on_write=on_accelerometer_x_changed
    )

    # Register Accelerometer Y
    client.register(
        "Accelerometer_Y",
        value=None,
        on_write=on_accelerometer_y_changed
    )

    # Register Accelerometer Z
    client.register(
        "Accelerometer_Z",
        value=None,
        on_write=on_accelerometer_z_changed
    )

    try:
        # Start Arduino Cloud client
        client.start()

    finally:
        # Close CSV file when program stops
        if data_file is not None:
            data_file.flush()
            data_file.close()
            data_file = None

            print(f"Data saved to {DATA_FILENAME}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(
            exc_type,
            exc_value,
            exc_traceback
        )
