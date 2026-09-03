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
UPDATE_INTERVAL = 1000  # milliseconds

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
# Shared live data buffer
# ------------------------------------------------------------

# Each item has this format:
# (timestamp, value1, value2, ...)
# For example: (timestamp, x, y, z)

data_buffer = deque(maxlen=BUFFER_SIZE)
buffer_lock = Lock()


def add_data_to_buffer(timestamp, *values):
    """
    Add one complete sensor data item to the shared buffer.
    """
    with buffer_lock:
        data_buffer.append((timestamp, *values))

    return len(data_buffer)


# ------------------------------------------------------------
# The wrapper 
# ------------------------------------------------------------

def create_smooth_live_graph(
    app,
    data_buffer,
    buffer_lock,
    variable_names,
    graph_id="live-sensor-graph",
    buffer_size=100,
    update_interval=000,
    title="Live Sensor Data",
    y_axis_title="Value"
):
    """
    Create a smooth real-time Plotly Dash graph for continuous data.

    Expected buffer item format:
        (timestamp, value1, value2, ...)

    Parameters:
        app:
            Dash application.
        data_buffer:
            Shared deque containing new sensor data.
        buffer_lock:
            Lock used to protect the shared buffer.
        variable_names:
            Names of the sensor variables.
            Example: ["X", "Y", "Z"]
        graph_id:
            ID used by the Dash graph.
        buffer_size:
            Maximum number of visible points.
        update_interval:
            How often Dash checks for new data, in milliseconds.
        title:
            Graph title.
        y_axis_title:
            Label for the y-axis.
    Returns:
        A Dash html.Div containing the graph and timer.
    """

    interval_id = f"{graph_id}-interval"

    # Create the graph only once.
    figure = go.Figure()

    for variable in variable_names:
        figure.add_trace(
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name=variable
            )
        )

    figure.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=y_axis_title
    )

    @app.callback(
        Output(graph_id, "extendData"),
        Input(interval_id, "n_intervals")
    )
    def update_graph(n_intervals):

        # Copy all fresh items, then clear the waiting buffer.
        with buffer_lock:
            new_data = list(data_buffer)
            data_buffer.clear()

        if not new_data:
            raise PreventUpdate

        timestamps = [sample[0] for sample in new_data]

        # Build one list of values for each sensor variable.
        values = []

        for index in range(len(variable_names)):
            variable_values = [
                sample[index + 1]
                for sample in new_data
            ]
            values.append(variable_values)

        update_data = {
            "x": [
                timestamps
                for variable in variable_names
            ],
            "y": values
        }

        trace_indices = list(range(len(variable_names)))

        # extendData adds only new points.
        # buffer_size keeps the visible graph window limited.
        return update_data, trace_indices, buffer_size

    return html.Div(
        [
            dcc.Graph(
                id=graph_id,
                figure=figure
            ),

            dcc.Interval(
                id=interval_id,
                interval=update_interval,
                n_intervals=0
            )
        ]
    )


# ------------------------------------------------------------
# Synchronise accelerometer X, Y and Z
# ------------------------------------------------------------

def save_data_if_ready():
    """
    Process data only after a new X, Y and Z value have all arrived.
    """
    global x_received, y_received, z_received

    if x_received and y_received and z_received:

        timestamp = datetime.now().isoformat(timespec="seconds")

        buffer_size = add_data_to_buffer(
            timestamp,
            latest_x,
            latest_y,
            latest_z
        )

        # Save the same complete data item to CSV.
        csv_line = (
            f"{timestamp},"
            f"{latest_x},"
            f"{latest_y},"
            f"{latest_z}\n"
        )

        if data_file is not None:
            data_file.write(csv_line)
            data_file.flush()

        print(
            f"Saved: {timestamp}, "
            f"X={latest_x}, "
            f"Y={latest_y}, "
            f"Z={latest_z} "
            f"| Waiting in buffer: {buffer_size}"
        )

        # Wait for another complete XYZ set.
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
# Dash application
# ------------------------------------------------------------

app = Dash(__name__)

app.layout = html.Div(
    [
        html.H2("Live Smartphone Accelerometer"),

        create_smooth_live_graph(
            app=app,
            data_buffer=data_buffer,
            buffer_lock=buffer_lock,
            variable_names=["X", "Y", "Z"],
            graph_id="accelerometer-graph",
            buffer_size=BUFFER_SIZE,
            update_interval=UPDATE_INTERVAL,
            title="Live Accelerometer Data",
            y_axis_title="Acceleration"
        )
    ]
)


# ------------------------------------------------------------
# Main program
# ------------------------------------------------------------

def main():
    global data_file

    data_file = open(
        DATA_FILENAME,
        "a",
        newline=""
    )

    # Write CSV header only if the file is empty.
    if data_file.tell() == 0:
        data_file.write(
            "timestamp,x,y,z\n"
        )
        data_file.flush()

    # Arduino IoT Cloud runs in the background.
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
