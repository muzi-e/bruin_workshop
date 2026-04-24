"""@bruin
name: ingestion.trips
type: python
image: python:3.11
connection: duckdb-default

materialization:
  type: table
  strategy: append

columns:
  - name: pickup_datetime
    type: timestamp
    description: "When the meter was engaged"
  - name: dropoff_datetime
    type: timestamp
    description: "When the meter was disengaged"
@bruin"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta

def materialize():
    """
    Main function that Bruin calls to materialize data for the trips ingestion asset.

    This function:
    1. Gets date range and taxi types from Bruin environment variables
    2. Generates list of months to process
    3. Downloads and processes NYC taxi trip data from parquet files
    4. Returns a pandas DataFrame that gets loaded into the database
    """

    # Get environment variables set by Bruin pipeline execution
    # BRUIN_START_DATE and BRUIN_END_DATE define the date range for this run
    start_date = os.environ["BRUIN_START_DATE"]  # e.g., "2022-01-01"
    end_date = os.environ["BRUIN_END_DATE"]      # e.g., "2022-01-31"

    # Get pipeline variables - taxi_types is defined in pipeline.yml
    # BRUIN_VARS contains all variables from pipeline.yml as JSON
    pipeline_vars = json.loads(os.environ["BRUIN_VARS"])
    taxi_types = pipeline_vars.get("taxi_types", ["yellow"])  # Default to yellow cabs

    print(f"Processing taxi data from {start_date} to {end_date} for types: {taxi_types}")

    # Generate list of months between start and end dates
    # This creates a list of (year, month) tuples for each month in the range
    months_to_process = generate_months_list(start_date, end_date)

    # Initialize empty list to collect all trip data
    all_trips_data = []

    # Process each taxi type (yellow, green, fhv, etc.)
    for taxi_type in taxi_types:
        print(f"Processing {taxi_type} taxi data...")

        # Process each month for this taxi type
        for year, month in months_to_process:
            try:
                # Construct the URL for the parquet file
                # Format: https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2022-01.parquet
                url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/{taxi_type}_tripdata_{year}-{month:02d}.parquet"

                print(f"Downloading {taxi_type} data for {year}-{month:02d}...")

                # Read parquet file directly from URL into pandas DataFrame
                df = pd.read_parquet(url)

                # Basic data cleaning and filtering
                # Only keep records with valid pickup/dropoff times
                df = df.dropna(subset=['tpep_pickup_datetime', 'tpep_dropoff_datetime'])

                # Convert datetime columns (they come as strings in some formats)
                df['tpep_pickup_datetime'] = pd.to_datetime(df['tpep_pickup_datetime'])
                df['tpep_dropoff_datetime'] = pd.to_datetime(df['tpep_dropoff_datetime'])

                # Filter to only records within our date range
                df = df[
                    (df['tpep_pickup_datetime'].dt.date >= pd.to_datetime(start_date).date()) &
                    (df['tpep_pickup_datetime'].dt.date <= pd.to_datetime(end_date).date())
                ]

                # Select only the columns we defined in the asset metadata
                df_selected = df[['tpep_pickup_datetime', 'tpep_dropoff_datetime']].copy()

                # Rename columns to match our schema
                df_selected = df_selected.rename(columns={
                    'tpep_pickup_datetime': 'pickup_datetime',
                    'tpep_dropoff_datetime': 'dropoff_datetime'
                })

                all_trips_data.append(df_selected)
                print(f"Processed {len(df_selected)} trips for {taxi_type} {year}-{month:02d}")

            except Exception as e:
                print(f"Error processing {taxi_type} data for {year}-{month:02d}: {e}")
                continue

    # Combine all dataframes into one
    if all_trips_data:
        final_dataframe = pd.concat(all_trips_data, ignore_index=True)
        print(f"Total trips processed: {len(final_dataframe)}")
    else:
        # Return empty dataframe with correct schema if no data
        final_dataframe = pd.DataFrame(columns=['pickup_datetime', 'dropoff_datetime'])
        print("No data processed")

    return final_dataframe


def generate_months_list(start_date_str, end_date_str):
    """
    Generate a list of (year, month) tuples for all months between start and end dates.

    Args:
        start_date_str: Start date as string (YYYY-MM-DD)
        end_date_str: End date as string (YYYY-MM-DD)

    Returns:
        List of tuples: [(2022, 1), (2022, 2), ...]
    """
    # Parse date strings into datetime objects
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    months_list = []

    # Start from the first day of the start month
    current_date = start_date.replace(day=1)

    # Loop through each month until we reach the end month
    while current_date <= end_date:
        months_list.append((current_date.year, current_date.month))
        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    return months_list