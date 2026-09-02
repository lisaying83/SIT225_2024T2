import traceback
from datetime import datetime
from arduino_iot_cloud import ArduinoCloudClient

DEVICE_ID = "YOUR_DEVICE_ID"
SECRET_KEY = "YOUR_SECRET_KEY"

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


def save_data_if_ready():
    """
    Save data only when new X, Y and Z values
    have all been received.
    """
    global x_received, y_received, z_received

    if x_received and y_received and z_received:

        # Create one timestamp for the complete set
        timestamp = datetime.now().isoformat(timespec="seconds")

        # Create CSV line:
        # <timestamp>,<x>,<y>,<z>
        csv_line = f"{timestamp},{latest_x},{latest_y},{latest_z}\n"

        if data_file is not None:
            data_file.write(csv_line)
            data_file.flush()

        print(
            f"Saved: {timestamp}, "
            f"X={latest_x}, Y={latest_y}, Z={latest_z}"
        )

        # Reset flags
        # Wait for another complete X, Y and Z set
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

    # Open one CSV file in append mode
    data_file = open(DATA_FILENAME, mode="a", newline="")

    # Write header
    data_file.write("timestamp,x,y,z\n")
    data_file.flush()

    # Instantiate Arduino Cloud client
    client = ArduinoCloudClient(
        device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY)

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
        main()  # main function which runs in an internal infinite loop
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_type, file=print)