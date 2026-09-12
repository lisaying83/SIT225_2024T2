import base64
import csv
import json
import time
from pathlib import Path
from datetime import datetime
from collections import deque
from threading import Lock, Thread, Event

import cv2
from arduino_iot_cloud import ArduinoCloudClient
from dash import Dash, dcc, html, Input, Output, no_update
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

WINDOW_SECONDS = 10
BUFFER_SIZE = 100
UPDATE_INTERVAL = 1000  # Dash checks once per second
WEBCAM_INDEX = 0

# Arduino IoT Cloud low-latency settings.
# The client is driven manually so MQTT messages are processed quickly.
CLIENT_POLL = 0.01          # seconds between client.update() calls
REGISTER_INTERVAL = 0.1     # cloud variable task interval

OUTPUT_FOLDER = Path(__file__).with_name("activity_data")

webcam = None
sample_sequence = 1
stop_event = Event()


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
# Shared 10-second activity-window buffer
# ------------------------------------------------------------

# Each item has this format:
# (timestamp, x, y, z)

data_buffer = deque()
buffer_lock = Lock()

# This starts when the first complete XYZ sample arrives.
window_start_time = None


def add_data_to_buffer(timestamp, *values):
    """
    Add one complete accelerometer sample to the current
    10-second data window.
    """
    global window_start_time

    with buffer_lock:
        if window_start_time is None:
            window_start_time = time.monotonic()

        data_buffer.append((timestamp, *values))

        return len(data_buffer)


# ------------------------------------------------------------
# Webcam
# ------------------------------------------------------------

def capture_webcam_image():
    """
    Capture one image from the laptop webcam.

    Returns:
        frame:
            OpenCV image used for saving to JPG.
        image_src:
            Base64 image used for displaying in Dash.
    """
    if webcam is None:
        return None, None

    success, frame = webcam.read()

    if not success:
        print("Could not capture webcam image.")
        return None, None

    success, encoded_image = cv2.imencode(".jpg", frame)

    if not success:
        print("Could not encode webcam image.")
        return None, None

    image_base64 = base64.b64encode(
        encoded_image
    ).decode("utf-8")

    image_src = (
        f"data:image/jpeg;base64,{image_base64}"
    )

    return frame, image_src


# ------------------------------------------------------------
# Save one 10-second activity sample
# ------------------------------------------------------------

def save_activity_sample(samples, frame):
    """
    Save one 10-second accelerometer data window and its
    matching webcam image.

    Example:
        1_20260906224530.csv
        1_20260906224530.jpg
    """
    global sample_sequence

    OUTPUT_FOLDER.mkdir(exist_ok=True)

    file_timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    base_filename = (
        f"{sample_sequence}_{file_timestamp}"
    )

    csv_path = OUTPUT_FOLDER / (
        f"{base_filename}.csv"
    )

    image_path = OUTPUT_FOLDER / (
        f"{base_filename}.jpg"
    )

    # Save the webcam image first.
    image_saved = cv2.imwrite(
        str(image_path),
        frame
    )

    if not image_saved:
        print("Could not save webcam image.")
        return

    try:
        with csv_path.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.writer(file)

            writer.writerow(
                ["timestamp", "x", "y", "z"]
            )

            writer.writerows(samples)

    except Exception:
        # Do not leave an unmatched image if CSV saving fails.
        image_path.unlink(missing_ok=True)
        raise

    print(
        f"Saved activity sample: "
        f"{base_filename}.csv + "
        f"{base_filename}.jpg "
        f"({len(samples)} readings)"
    )

    sample_sequence += 1


# ------------------------------------------------------------
# Live graph and activity image
# ------------------------------------------------------------

def create_smooth_live_graph(
    app,
    data_buffer,
    buffer_lock,
    variable_names,
    graph_id="live-sensor-graph",
    image_id="activity-image",
    buffer_size=100,
    update_interval=1000,
    title="Live Sensor Data",
    y_axis_title="Value"
):
    """
    Update the dashboard after approximately 10 seconds of
    fresh accelerometer data have been collected.

    The same 10-second data window is:
        1. added to the Plotly graph,
        2. saved to a CSV file.

    At the same time, one webcam image is:
        1. displayed in the dashboard,
        2. saved as a matching JPG file.
    """

    interval_id = f"{graph_id}-interval"

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
        Output(image_id, "src"),
        Input(interval_id, "n_intervals")
    )
    def update_dashboard(n_intervals):
        global window_start_time

        # Dash checks every second, but only processes data
        # when a complete 10-second window is ready.
        with buffer_lock:
            if (
                not data_buffer
                or window_start_time is None
                or time.monotonic() - window_start_time
                < WINDOW_SECONDS
            ):
                new_data = None
            else:
                new_data = list(data_buffer)
                data_buffer.clear()
                window_start_time = None

        if not new_data:
            raise PreventUpdate

        timestamps = [
            sample[0]
            for sample in new_data
        ]

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

        trace_indices = list(
            range(len(variable_names))
        )

        # Capture one image for this 10-second window.
        frame, image_src = capture_webcam_image()

        if frame is not None:
            save_activity_sample(
                new_data,
                frame
            )
        else:
            image_src = no_update
            print(
                "10-second data window received, "
                "but no image was captured, so the "
                "CSV/JPG pair was not saved."
            )

        graph_update = (
            update_data,
            trace_indices,
            buffer_size
        )

        return graph_update, image_src

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Graph(
                                id=graph_id,
                                figure=figure
                            )
                        ],
                        style={
                            "width": "65%"
                        }
                    ),

                    html.Div(
                        [
                            html.H4("Current Activity Image"),

                            html.Img(
                                id=image_id,
                                style={
                                    "width": "100%",
                                    "maxWidth": "480px"
                                }
                            )
                        ],
                        style={
                            "width": "35%",
                            "padding": "20px"
                        }
                    )
                ],
                style={
                    "display": "flex",
                    "alignItems": "center"
                }
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
    Add data only after a new X, Y and Z value have all arrived.
    """
    global x_received, y_received, z_received

    if x_received and y_received and z_received:

        timestamp = datetime.now().isoformat(
            timespec="milliseconds"
        )

        buffer_size = add_data_to_buffer(
            timestamp,
            latest_x,
            latest_y,
            latest_z
        )

        print(
            f"Received: {timestamp}, "
            f"X={latest_x}, "
            f"Y={latest_y}, "
            f"Z={latest_z} "
            f"| Current window: "
            f"{buffer_size} readings"
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
    """
    Connect to Arduino IoT Cloud in synchronous mode and
    manually process incoming MQTT messages.
    """

    client = ArduinoCloudClient(
        device_id=DEVICE_ID,
        username=DEVICE_ID,
        password=SECRET_KEY,
        sync_mode=True
    )

    client.register(
        "Accelerometer_X",
        value=None,
        on_write=on_accelerometer_x_changed,
        interval=REGISTER_INTERVAL
    )

    client.register(
        "Accelerometer_Y",
        value=None,
        on_write=on_accelerometer_y_changed,
        interval=REGISTER_INTERVAL
    )

    client.register(
        "Accelerometer_Z",
        value=None,
        on_write=on_accelerometer_z_changed,
        interval=REGISTER_INTERVAL
    )

    print("Starting Arduino IoT Cloud in low-latency sync mode...")

    # In sync mode, start() establishes the connection and returns.
    client.start()

    # Process MQTT/cloud messages continuously instead of depending
    # on the library's default asynchronous scheduling.
    while not stop_event.is_set():
        client.update()

        if stop_event.wait(CLIENT_POLL):
            break


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
            image_id="activity-image",
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
    global webcam

    # Open the laptop webcam once and keep it available.
    webcam = cv2.VideoCapture(
        WEBCAM_INDEX
    )

    if not webcam.isOpened():
        print("Warning: Could not open the webcam.")

        webcam.release()
        webcam = None
    else:
        print("Webcam opened.")

    # Arduino IoT Cloud runs in the background.
    cloud_thread = Thread(
        target=run_arduino_cloud,
        daemon=True
    )

    cloud_thread.start()

    try:
        print("Starting Plotly Dash...")
        print("Open http://127.0.0.1:8050")
        print("A CSV/JPG pair will be saved every 10 seconds.")

        app.run(
            host="127.0.0.1",
            port=8050,
            debug=False,
            use_reloader=False
        )

    finally:
        stop_event.set()

        if webcam is not None:
            webcam.release()


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        stop_event.set()
        print("Program stopped.")
