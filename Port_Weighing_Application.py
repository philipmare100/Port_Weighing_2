import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import openpyxl

# Streamlit app title
st.title("Port Weighing Supervision - Data Extraction and Combined DataFrame")

# South Africa timezone setup
sa_timezone = pytz.timezone('Africa/Johannesburg')

# File uploader widget
uploaded_file = st.file_uploader("Choose a file", type=['xlsx'])

# If a file is uploaded
if uploaded_file is not None:
    try:
        # Load the data from the "RawData" sheet without skipping any rows (headers are on the first row)
        df = pd.read_excel(uploaded_file, sheet_name="RawData", header=0)

        # Ensure "Added Time" is in datetime format and localize to South Africa timezone
        if "Added Time" in df.columns:
            df['Added Time'] = pd.to_datetime(df['Added Time'], errors='coerce')
            localized_added_time = df['Added Time'].dt.tz_localize('UTC').dt.tz_convert(sa_timezone)
        else:
            st.error("The 'RawData' sheet does not contain an 'Added Time' column.")
            st.stop()

        # Identify important columns based on available headers
        bag_id_column = "BAG ID." if "BAG ID." in df.columns else None
        kico_seal_column = "AHK SEAL NO." if "AHK SEAL NO." in df.columns else None

        # Check if required columns are present
        if bag_id_column and kico_seal_column:
            # Extract components from the Bag ID column and create new columns
            def extract_bag_info(bag_id):
                bag_id = str(bag_id)
                parts = {}
                for item in bag_id.split(','):
                    if '=' in item:
                        split_item = item.split('=', 1)  # Split only on the first '='
                    elif ': ' in item:
                        split_item = item.split(': ', 1)  # Split only on the first ': '
                    else:
                        continue

                    if len(split_item) == 2:
                        parts[split_item[0].strip()] = split_item[1].strip()
                return parts


            # Apply extraction to create new columns from Bag ID details
            bag_info_df = df[bag_id_column].dropna().apply(extract_bag_info).apply(pd.Series)

            # Concatenate original and extracted dataframes
            combined_df = pd.concat([df, bag_info_df], axis=1)

            # Create "Bag Scanned & Manual" column with specific conditions
            combined_df["Bag Scanned & Manual"] = combined_df.apply(
                lambda row: row["Bag"] if len(str(row[bag_id_column])) > 20 else row[bag_id_column],
                axis=1
            )

            # Sort combined_df by Added Time in descending order
            combined_df = combined_df.sort_values(by="Added Time", ascending=False)

            # Display combined_df with total count
            st.write(f"Total Combined DataFrame Entries: {len(combined_df)}")
            st.write("Combined DataFrame with extracted components (Sorted by Added Time):")
            st.dataframe(combined_df)

            # 1. Exception Table: Duplicates in "Bag Scanned & Manual" column
            duplicates_df = combined_df[combined_df.duplicated(subset=["Bag Scanned & Manual"], keep=False)]
            grouped_duplicates = duplicates_df.groupby("Bag Scanned & Manual").apply(
                lambda group: pd.Series({
                    "Added Time": ', '.join(group["Added Time"].astype(str).unique()),
                    "Bag Scanned & Manual": group["Bag Scanned & Manual"].iloc[0],
                    "AHK SEAL NO.": ', '.join(group["AHK SEAL NO."].dropna().astype(str).unique()),
                    "Seal": ', '.join(group["Seal"].dropna().astype(str).unique()),
                    "Lot": ', '.join(group["Lot"].dropna().unique())
                })
            ).reset_index(drop=True)
            st.write(f"Total Duplicates in 'Bag Scanned & Manual': {len(grouped_duplicates)}")
            st.write("Duplicates Exception Table (Based on 'Bag Scanned & Manual'):")
            st.dataframe(grouped_duplicates)

            # 2. Exception Table: "BAG ID." entries with length between 16 and 25 characters
            length_exception_df = combined_df[combined_df[bag_id_column].str.len().between(16, 25)]
            st.write(f"Total 'BAG ID.' Entries with Length Between 16 and 25 Characters: {len(length_exception_df)}")
            st.write("Length Exception Table (Based on 'BAG ID.' Length 16-25):")
            st.dataframe(length_exception_df)

            # Date and Time Picker for filtering
            st.write("Select a date-time range to filter the Combined DataFrame:")
            start_date = st.date_input("Start Date", value=localized_added_time.min().date())
            start_time = st.time_input("Start Time", value=pd.to_datetime("00:00").time())

            # Default end date and time to the current date and time in SA timezone
            end_date = st.date_input("End Date", value=datetime.now(sa_timezone).date())
            end_time = st.time_input("End Time", value=datetime.now(sa_timezone).time())

            # Combine selected date and time into timezone-aware datetime objects
            start_datetime = sa_timezone.localize(pd.to_datetime(f"{start_date} {start_time}"))
            end_datetime = sa_timezone.localize(pd.to_datetime(f"{end_date} {end_time}"))

            # Filter combined_df based on the selected datetime range using localized_added_time for filtering
            combined_df_for_download = combined_df[
                (localized_added_time >= start_datetime) & (localized_added_time <= end_datetime)]

            # Mapping for column names in the download CSV
            column_mappings = {
                "Bag Scanned & Manual": "name",
                "AHK SEAL NO.": "PRN_AHK_SEAL",
                "WAREHOUSE PLATFORM SCALE GROSS WEIGHT (KG)": "PRN_WH_GROSS_WEIGHT",
                "SAMPLING TIME": "BAG_AHK_LP_SAMPLING_TS"
            }

            # Ensure only the specified columns are included in the download
            mapped_df_for_download = pd.DataFrame()
            for original_col, new_col in column_mappings.items():
                if original_col in combined_df_for_download.columns:
                    mapped_df_for_download[new_col] = combined_df_for_download[original_col]
                else:
                    mapped_df_for_download[new_col] = None  # Add empty column if missing

            # Add "+02:00" to all time columns in mapped_df_for_download
            for col in ["BAG_AHK_LP_SAMPLING_TS"]:  # Specify all columns with time information
                if col in mapped_df_for_download.columns:
                    mapped_df_for_download[col] = mapped_df_for_download[col].astype(str) + "+02:00"

            # Display the mapped DataFrame view and total entries count for reference
            st.write(f"Total Mapped DataFrame Entries for Download: {len(mapped_df_for_download)}")
            st.write("Mapped DataFrame for Download:")
            st.dataframe(mapped_df_for_download)

            # Define the filename based on start and end date-time selections
            file_name = f"From_{start_date.strftime('%Y%m%d')}_{start_time.strftime('%H%M')}_to_{end_date.strftime('%Y%m%d')}_{end_time.strftime('%H%M')}_Sampling_Recieval.csv"

            # Convert filtered data to CSV for download
            csv_data = mapped_df_for_download.to_csv(index=False)
            st.download_button(
                label="Download Filtered Combined Data as CSV",
                data=csv_data,
                file_name=file_name,
                mime="text/csv"
            )

        else:
            st.error("The file does not contain the required column: 'BAG ID.'")
    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Awaiting file upload...")
