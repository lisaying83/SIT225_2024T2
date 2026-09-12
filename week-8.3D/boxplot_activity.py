import pandas as pd
import matplotlib.pyplot as plt

# Load standard deviation results
df = pd.read_csv("standard_deviation_results.csv")

activity_order = [
    "No activity",
    "Waving",
    "Shaking"
]

axes = {
    "X": "x_sd",
    "Y": "y_sd",
    "Z": "z_sd"
}

for axis_name, column_name in axes.items():

    data = [
        df[df["activity_name"] == activity][column_name]
        for activity in activity_order
    ]

    plt.figure(figsize=(8, 5))

    plt.boxplot(
        data,
        tick_labels=activity_order
    )

    plt.title(
        f"{axis_name} Variation Within Each 10-Second Window"
    )

    plt.xlabel("Activity")
    plt.ylabel("Standard Deviation")

    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    # Save graph
    plt.savefig(
        f"activity_graphs/{axis_name.lower()}_variation_boxplot.png",
        dpi=300
    )

    plt.show()