import sys
import json
import traceback
from pathlib import Path
from datetime import datetime
from collections import deque
from threading import Lock, Thread

from arduino_iot_cloud import ArduinoCloudClient
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go

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

# The Arduino callbacks will write to this buffer and, later,
# Plotly Dash will read from it. A lock prevents both operations
# from changing/reading the buffer at exactly the same time.
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


app = Dash(__name__)

app.layout = html.Div(
    [
        html.H2("Live Smartphone Accelerometer"),

        html.P(
            f"Showing the latest {BUFFER_SIZE} synchronized X, Y and Z samples."
        ),

        dcc.Graph(
            id="live-accelerometer-graph",
            figure=go.Figure()
        ),

        # Ask Dash to check the rolling buffer regularly.
        # Stage 3 uses 250 ms. Stage 4 can improve how the
        # graph itself is updated.
        dcc.Interval(
            id="graph-update-interval",
            interval=250,       # milliseconds
            n_intervals=0
        )
    ]
)


@app.callback(
    Output("live-accelerometer-graph", "figure"),
    Input("graph-update-interval", "n_intervals")
)
def update_accelerometer_graph(n_intervals):
    """
    Read a snapshot of the rolling buffer and update the Dash graph.

    Arduino IoT Cloud writes data to live_buffer.
    Dash only reads a copy returned by get_buffer_snapshot().
    This keeps data collection separate from visualisation.
    """

    data = get_buffer_snapshot()

    figure = go.Figure()

    if data:
        timestamps = [sample[0] for sample in data]
        x_values = [sample[1] for sample in data]
        y_values = [sample[2] for sample in data]
        z_values = [sample[3] for sample in data]

        figure.add_trace(
            go.Scatter(
                x=timestamps,
                y=x_values,
                mode="lines",
                name="X"
            )
        )

        figure.add_trace(
            go.Scatter(
                x=timestamps,
                y=y_values,
                mode="lines",
                name="Y"
            )
        )

        figure.add_trace(
            go.Scatter(
                x=timestamps,
                y=z_values,
                mode="lines",
                name="Z"
            )
        )

    figure.update_layout(
        title="Live Accelerometer Data",
        xaxis_title="Time",
        yaxis_title="Acceleration",
        uirevision="keep-view"
    )

    return figure


def run_arduino_cloud():
    """
    Run Arduino IoT Cloud in a background thread.

    The Arduino callbacks receive X, Y and Z values and write
    complete synchronized samples into live_buffer.
    """
    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        username=DEVICE_ID,
        password=SECRET_KEY
    )

    client.register(
        "Accelerometer_X",
        value=None,
        on_write=on_accelerometer_x_changed
    )

    client.register(
        "Accelerometer_Y",
        value=None,
        on_write=on_accelerometer_y_changed
    )

    client.register(
        "Accelerometer_Z",
        value=None,
        on_write=on_accelerometer_z_changed
    )

    print("Starting Arduino IoT Cloud connection...")
    client.start()


def main():
    global data_file

    print("main() function")
    print(f"Live buffer size: {BUFFER_SIZE} samples")
    print("Dash refresh interval: 250 ms")

    # Open CSV file once for the complete program execution.
    data_file = open(DATA_FILENAME, mode="a", newline="")

    # Write the header only if the CSV file is empty.
    if data_file.tell() == 0:
        data_file.write("timestamp,x,y,z\n")
        data_file.flush()

    # ArduinoCloudClient.start() runs continuously, so start it
    # in its own daemon thread. Dash can then run independently
    # in the main thread.
    cloud_thread = Thread(
        target=run_arduino_cloud,
        name="ArduinoCloudThread",
        daemon=True
    )
    cloud_thread.start()

    try:
        print("Starting Plotly Dash...")
        print("Open http://127.0.0.1:8050 in your browser.")

        app.run(
            host="127.0.0.1",
            port=8050,
            debug=False,
            use_reloader=False
        )

    finally:
        if data_file is not None:
            data_file.flush()
            data_file.close()
            data_file = None

            print(f"Data saved to {DATA_FILENAME}")


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nProgram stopped by user.")

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(
            exc_type,
            exc_value,
            exc_traceback
        )
