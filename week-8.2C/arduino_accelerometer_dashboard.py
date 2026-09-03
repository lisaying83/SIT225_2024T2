import json
from pathlib import Path
from datetime import datetime
from collections import deque
from threading import Lock, Thread

from arduino_iot_cloud import ArduinoCloudClient
from dash import Dash, dcc, html, Input, Output
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go


# ------------------------------------------------------------
# Read Arduino IoT Cloud credentials from settings.json
# ------------------------------------------------------------

SETTINGS_FILE = Path(__file__).with_name("settings.json")

with SETTINGS_FILE.open("r", encoding="utf-8") as file:
    settings = json.load(file)

DEVICE_ID = settings["device_id"]
SECRET_KEY = settings["secret_key"]


# ------------------------------------------------------------
# Basic settings
# ------------------------------------------------------------

DATA_FILENAME = "accelerometer_xyz.csv"
BUFFER_SIZE = 100
UPDATE_INTERVAL = 250  # milliseconds

data_file = None


# ------------------------------------------------------------
# Latest accelerometer values
# ------------------------------------------------------------

latest_x = None
latest_y = None
latest_z = None

x_received = False
y_received = False
z_received = False


# ------------------------------------------------------------
# Live data buffer
# ------------------------------------------------------------

# This buffer stores new samples waiting to be sent to Dash.
data_buffer = deque(maxlen=BUFFER_SIZE)

# Arduino writes to the buffer while Dash reads it.
buffer_lock = Lock()


def add_to_buffer(timestamp, x, y, z):
    """Add one complete XYZ sample to the buffer."""
    with buffer_lock:
        data_buffer.append((timestamp, x, y, z))
        return len(data_buffer)


def get_new_data():
    """
    Get all new samples currently waiting in the buffer.

    After Dash reads them, clear the buffer because these samples
    have already been sent to the graph.
    """
    with buffer_lock:
        new_data = list(data_buffer)
        data_buffer.clear()

    return new_data


# ------------------------------------------------------------
# Synchronise X, Y and Z
# ------------------------------------------------------------

def save_data_if_ready():
    """
    Process data only after a new X, Y and Z value have all arrived.
    """
    global x_received, y_received, z_received

    if x_received and y_received and z_received:

        timestamp = datetime.now().isoformat(timespec="seconds")

        # Add the complete sample to the live buffer.
        buffer_size = add_to_buffer(
            timestamp,
            latest_x,
            latest_y,
            latest_z
        )

        # Also save the sample to CSV.
        csv_line = f"{timestamp},{latest_x},{latest_y},{latest_z}\n"

        if data_file is not None:
            data_file.write(csv_line)
            data_file.flush()

        print(
            f"Saved: {timestamp}, "
            f"X={latest_x}, Y={latest_y}, Z={latest_z} "
            f"| Waiting in buffer: {buffer_size}"
        )

        # Wait for a new complete XYZ set.
        x_received = False
        y_received = False
        z_received = False


def on_accelerometer_x_changed(client, value):
    global latest_x, x_received

    latest_x = value
    x_received = True
    save_data_if_ready()


def on_accelerometer_y_changed(client, value):
    global latest_y, y_received

    latest_y = value
    y_received = True
    save_data_if_ready()


def on_accelerometer_z_changed(client, value):
    global latest_z, z_received

    latest_z = value
    z_received = True
    save_data_if_ready()


# ------------------------------------------------------------
# Plotly Dash
# ------------------------------------------------------------

def create_initial_figure():
    """Create the three empty X, Y and Z lines once."""
    figure = go.Figure()

    for axis in ["X", "Y", "Z"]:
        figure.add_trace(
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name=axis
            )
        )

    figure.update_layout(
        title="Live Accelerometer Data",
        xaxis_title="Time",
        yaxis_title="Acceleration"
    )

    return figure


app = Dash(__name__)

app.layout = html.Div(
    [
        html.H2("Live Smartphone Accelerometer"),

        dcc.Graph(
            id="live-accelerometer-graph",
            figure=create_initial_figure()
        ),

        dcc.Interval(
            id="graph-update-interval",
            interval=UPDATE_INTERVAL,
            n_intervals=0
        )
    ]
)


@app.callback(
    Output("live-accelerometer-graph", "extendData"),
    Input("graph-update-interval", "n_intervals")
)
def update_graph(n_intervals):
    """
    Send only new samples to the existing Plotly graph.
    """
    new_data = get_new_data()

    if not new_data:
        raise PreventUpdate

    timestamps = [sample[0] for sample in new_data]
    x_values = [sample[1] for sample in new_data]
    y_values = [sample[2] for sample in new_data]
    z_values = [sample[3] for sample in new_data]

    update_data = {
        "x": [
            timestamps,
            timestamps,
            timestamps
        ],
        "y": [
            x_values,
            y_values,
            z_values
        ]
    }

    # Trace 0 = X, Trace 1 = Y, Trace 2 = Z
    return update_data, [0, 1, 2], BUFFER_SIZE


# ------------------------------------------------------------
# Arduino IoT Cloud
# ------------------------------------------------------------

def run_arduino_cloud():
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

    print("Starting Arduino IoT Cloud...")
    client.start()


# ------------------------------------------------------------
# Main program
# ------------------------------------------------------------

def main():
    global data_file

    data_file = open(DATA_FILENAME, "a", newline="")

    # Write CSV header only if the file is empty.
    if data_file.tell() == 0:
        data_file.write("timestamp,x,y,z\n")
        data_file.flush()

    # Run Arduino IoT Cloud in the background.
    cloud_thread = Thread(
        target=run_arduino_cloud,
        daemon=True
    )
    cloud_thread.start()

    try:
        print("Starting Plotly Dash...")
        print("Open http://127.0.0.1:8050")

        app.run(
            host="127.0.0.1",
            port=8050,
            debug=False,
            use_reloader=False
        )

    finally:
        if data_file is not None:
            data_file.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program stopped.")
