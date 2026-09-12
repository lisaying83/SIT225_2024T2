import pandas as pd
import matplotlib.pyplot as plt

# Change this to the activity file you want to check
filename = "activity_data/150_20260910232926.csv"

# Load CSV file
df = pd.read_csv(filename)

# Convert timestamp to datetime
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Plot accelerometer data
plt.figure(figsize=(10, 5))

plt.plot(df["timestamp"], df["x"], marker="o", label="X")
plt.plot(df["timestamp"], df["y"], marker="o", label="Y")
plt.plot(df["timestamp"], df["z"], marker="o", label="Z")

plt.title(f"Accelerometer Data - {filename}")
plt.xlabel("Time")
plt.ylabel("Acceleration")
plt.legend()
plt.grid(True)

plt.xticks(rotation=45)
plt.tight_layout()

plt.show()