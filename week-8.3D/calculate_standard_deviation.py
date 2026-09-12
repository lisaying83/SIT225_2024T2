import pandas as pd
from pathlib import Path

# Folder that contains all activity CSV files
data_folder = Path("activity_data")

# Annotation file
annotation_file = "annotation.csv"

# Load annotation file
annotation = pd.read_csv(annotation_file)

# Activity names
activity_names = {
    0: "No activity",
    1: "Waving",
    2: "Shaking"
}

# Keep only confirmed recordings
# This automatically excludes 0?, 1?, 2? because they are not integers
confirmed = annotation[
    annotation["activity"].isin([0, 1, 2])
].copy()

print("Number of confirmed recordings:", len(confirmed))

# Store standard deviation results
results = []

# Process each confirmed recording
for _, row in confirmed.iterrows():

    filename = row["filename"]
    activity = row["activity"]

    # Build path to the activity CSV file
    file_path = data_folder / filename

    # Load activity data
    df = pd.read_csv(file_path)

    # Calculate population standard deviation
    x_sd = df["x"].std(ddof=0)
    y_sd = df["y"].std(ddof=0)
    z_sd = df["z"].std(ddof=0)

    # Store the result
    results.append({
        "filename": filename,
        "activity": activity,
        "activity_name": activity_names[activity],
        "x_sd": x_sd,
        "y_sd": y_sd,
        "z_sd": z_sd
    })

# Convert results to DataFrame
sd_results = pd.DataFrame(results)

# Display all results
print("\nStandard deviation for each recording:")
print(sd_results)

# Save results
sd_results.to_csv(
    "standard_deviation_results.csv",
    index=False
)

# Calculate median standard deviation for each activity
median_summary = (
    sd_results
    .groupby("activity_name")[["x_sd", "y_sd", "z_sd"]]
    .median()
)

print("\nMedian standard deviation for each activity:")
print(median_summary)

# Save summary
median_summary.to_csv(
    "standard_deviation_median_summary.csv"
)