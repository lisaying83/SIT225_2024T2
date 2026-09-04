import traceback
from datetime import datetime
from arduino_iot_cloud import ArduinoCloudClient

DEVICE_ID = "YOUR_DEVICE_ID"
SECRET_KEY = "YOUR_SECRET_KEY"

X_FILENAME = "accelerometer_x.csv"
Y_FILENAME = "accelerometer_y.csv"
Z_FILENAME = "accelerometer_z.csv"
data_file_x = None
data_file_y = None
data_file_z = None


def on_accelerometer_x_changed(client, value):
    """Run when a new accelerometer_x value is received from Arduino Cloud."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    csv_line = f"{timestamp},{value}\n"

    print(f"New Accelerometer_X: {value}")

    if data_file_x is not None:
        data_file_x.write(csv_line)
        data_file_x.flush()

def on_accelerometer_y_changed(client, value):
    """Run when a new accelerometer_y value is received from Arduino Cloud."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    csv_line = f"{timestamp},{value}\n"

    print(f"New Accelerometer_Y: {value}")

    if data_file_y is not None:
        data_file_y.write(csv_line)
        data_file_y.flush()

def on_accelerometer_z_changed(client, value):
    """Run when a new accelerometer_z value is received from Arduino Cloud."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    csv_line = f"{timestamp},{value}\n"

    print(f"New Accelerometer_Z: {value}")

    if data_file_z is not None:
        data_file_z.write(csv_line)
        data_file_z.flush()

def main():
    global data_file_x
    global data_file_y
    global data_file_z

    print("main() function")

    # Open 3 csv files
    # Open once in append mode and keep it open while the program runs.
    data_file_x = open(X_FILENAME, mode="a", newline="")
    data_file_y = open(Y_FILENAME, mode="a", newline="")
    data_file_z = open(Z_FILENAME, mode="a", newline="")

    # Write header
    data_file_x.write("timestamp,data-value\n")
    data_file_x.flush()
    data_file_y.write("timestamp,data-value\n")
    data_file_y.flush()
    data_file_z.write("timestamp,data-value\n")
    data_file_z.flush()
    
     # Instantiate Arduino cloud client
    client = ArduinoCloudClient(
        device_id=DEVICE_ID, username=DEVICE_ID, password=SECRET_KEY
    )

    # Register with 'Accelerometer_X' cloud variable
    # and listen on its value changes in 'on_accelerometer_x_changed'
    # callback function.
    # 
    client.register(
        "Accelerometer_X", value=None, 
        on_write=on_accelerometer_x_changed)
    
    # Register with 'Accelerometer_Y' cloud variable
    # and listen on its value changes in 'on_accelerometer_y_changed'
    # callback function.
    # 
    client.register(
        "Accelerometer_Y", value=None, 
        on_write=on_accelerometer_y_changed)
    
    # Register with 'Accelerometer_Z' cloud variable
    # and listen on its value changes in 'on_accelerometer_z_changed'
    # callback function.
    # 
    client.register(
        "Accelerometer_Z", value=None, 
        on_write=on_accelerometer_z_changed)

    try:
        # start cloud client
        client.start()
    finally:
        # Close the file when the program stops.
        if data_file_x is not None:
            data_file_x.flush()
            data_file_x.close()
            data_file_x = None
            print(f"Data saved to {X_FILENAME}")
        
        if data_file_y is not None:
            data_file_y.flush()
            data_file_y.close()
            data_file_y = None
            print(f"Data saved to {Y_FILENAME}")

        if data_file_z is not None:
            data_file_z.flush()
            data_file_z.close()
            data_file_z = None
            print(f"Data saved to {Z_FILENAME}")


if __name__ == "__main__":
    try:
        main()  # main function which runs in an internal infinite loop
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_type, file=print)