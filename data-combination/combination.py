"""_summary_
Docstring for combination.py
Anish Chowdary Pendurti
Uses open tree of life to resolve species names
"""

import os

import pandas as pd

# from opentree import OpenTree as ot

# Define the paths to the files
csv_file_path = os.path.join("data", "BodyMass.csv")
# Path to your CSV data file

# Load the CSV data file
df_csv = pd.read_csv(csv_file_path)


# Function to resolve species names to OTT IDs using the Open Tree of Life TNRS
def resolve_to_ott(names):
    """
    Docstring for resolve_to_ott
    Resolve species names to OTT IDs using Open Tree of Life TNRS
    :param names: list of species names from BodyMass.csv
    """
    # response = ot.tnrs_match_names(names=names)
    # missing tnrs_match_names from ot
    response = [names]
    ids = {species["submitted_name"]: species["ott_id"] for species in response}  # noqa
    return ids


# Resolve species names in the CSV file to OTT IDs
species_names = df_csv["species_name"].tolist()
# Replace 'species_name' with the actual column name in your CSV
ott_ids = resolve_to_ott(species_names)

# Add OTT IDs to the original CSV data
df_csv["ott_id"] = df_csv["species_name"].map(ott_ids)

# Save the merged data to a new CSV file in the 'data-combination' folder
merged_file_path = os.path.join("data-combination", "merged_data.csv")  # Output file path
df_csv.to_csv(merged_file_path, index=False)

# Output a success message
print(f"Merged data saved to {merged_file_path}")
