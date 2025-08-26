import pandas as pd
import numpy as np
import os

script_dir = os.path.dirname(os.path.abspath(__file__)) 

def pre_processing_data() -> pd.DataFrame:
    file_path = os.path.join(script_dir, "..", "data", "at-dataset", "Scats_Data.csv")

    df = pd.read_csv(file_path, sep="\t")

    df[["Detector_ID", "Lane"]] = df["Detector"].str.split("-", expand=True)
    df = df.drop(columns=["Detector"])
    df["Detector_ID"] = pd.to_numeric(df["Detector_ID"], errors="coerce")
    df["Lane"] = pd.to_numeric(df["Lane"], errors="coerce")
    df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"], format="%Y-%m-%d %H:%M")

    df = df.drop_duplicates(subset=["Detector_ID", "Lane", "DateTime"])
    # df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d')
    # df['Time'] = pd.to_datetime(df['Time'], format='%H:%M').dt.time
    
    return df

def interpolate_data(df: pd.DataFrame) -> pd.DataFrame:
    site_list = df['Detector_ID'].unique()
    full_time_index = pd.date_range(df["DateTime"].min(), df["DateTime"].max(), freq="h")
    main_df = pd.DataFrame()
    for site in site_list:
        lane_list = df.loc[df['Detector_ID'] == site, 'Lane'].unique()
        df_lane_list = pd.DataFrame()
        for lane in lane_list:
            # base hourly frame for this site/lane
            interpolate_df = (
                pd.DataFrame(index=full_time_index)
                .rename_axis('DateTime')
                .reset_index()
            )
            interpolate_df['Detector_ID'] = site
            interpolate_df['Lane'] = lane

            # take the actual observations for this site/lane
            sub = df[(df['Detector_ID'] == site) & (df['Lane'] == lane)][
                ['DateTime', 'Volume']
            ].copy()

            # merge to align values to the hourly grid
            interpolate_df = interpolate_df.merge(
                sub, on='DateTime', how='left'
            )

            # set DateTime index for time-aware interpolation
            interpolate_df = interpolate_df.sort_values('DateTime').set_index('DateTime')

            # time-aware interpolation (add a limit if you want only short gaps filled)
            interpolate_df['Volume'] = interpolate_df['Volume'].interpolate(
                method='time'  #, limit=6
            ).round().astype('Int64')

            # back to rows
            interpolate_df = interpolate_df.reset_index()

            df_lane_list = pd.concat([df_lane_list, interpolate_df], ignore_index=True)

        main_df = pd.concat([main_df, df_lane_list], ignore_index=True)
    return main_df

if __name__ == "__main__":
    df = pd.DataFrame()
    main_df = pd.DataFrame()
    df = pre_processing_data()
    main_df = interpolate_data(df)
    file_path = os.path.join(script_dir, "..", "data", "at-dataset", "final_data.csv")
    main_df.to_csv(file_path, index=False)
    print(f"---Data cleaned and stored in {file_path}---")
