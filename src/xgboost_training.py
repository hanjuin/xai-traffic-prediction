import numpy as np
import pandas as pd
from xgboost import XGBRegressor
import xgboost as xgb
from xgboost.callback import EarlyStopping
import os
from sklearn.metrics import mean_absolute_error, mean_squared_error
import sys, inspect, xgboost as xgb, pandas as pd

# ---------- CONFIG ----------
TARGET = "Volume"
ID_COLS = ["Detector_ID", "Lane"]
TIME_COL = "DateTime"

# choose lags/rolls (adjust as needed)
LAGS = [1, 2, 3, 6, 12, 24, 168]   # last hour, last day, last week
ROLLS = [3, 6, 24]                 # rolling windows (hours)

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    TIME_COL = "DateTime"
    TARGET = "Volume"
    ID_COLS = ["Detector_ID", "Lane"]

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    df = df.sort_values(ID_COLS + [TIME_COL]).dropna(subset=[TIME_COL])

    # time & cyclical
    df["hour"]  = df[TIME_COL].dt.hour
    df["dow"]   = df[TIME_COL].dt.dayofweek
    df["month"] = df[TIME_COL].dt.month
    df["sin_hour"] = np.sin(2*np.pi*df["hour"]/24)
    df["cos_hour"] = np.cos(2*np.pi*df["hour"]/24)
    df["sin_dow"]  = np.sin(2*np.pi*df["dow"]/7)
    df["cos_dow"]  = np.cos(2*np.pi*df["dow"]/7)

    # categoricals
    for c in ID_COLS:
        df[c] = df[c].astype("category")

    # lags per site/lane (pass observed to silence future warning)
    g = df.groupby(ID_COLS, group_keys=False, observed=False)
    for lag in [1,2,3,6,12,24,168]:
        df[f"lag_{lag}"] = g[TARGET].shift(lag)

    for w in [3,6,24]:
        df[f"roll_mean_{w}"] = g[TARGET].shift(1).rolling(w).mean()
        df[f"roll_std_{w}"]  = g[TARGET].shift(1).rolling(w).std()

    # ---- FIXED: past same-hour mean (no KeyError) ----
    # Group by (Detector_ID, Lane, hour) on the TARGET Series, compute expanding mean on shifted values.
    ser = df.set_index(ID_COLS + ["hour"])[TARGET]
    hod_mean = ser.groupby(level=[0,1,2]).apply(lambda s: s.shift(1).expanding().mean())

    # bring back as a column aligned to df's row order
    df["hod_mean_past"] = (
    df.groupby(["Detector_ID", "Lane", "hour"], observed=False)[TARGET]
      .transform(lambda s: s.shift(1).expanding().mean())
    )

    # drop rows with NaNs introduced by lags/rolls (starts of each series)
    feature_cols = [c for c in df.columns if c not in [TARGET, TIME_COL]]
    df = df.dropna(subset=feature_cols + [TARGET]).reset_index(drop=True)
    return df


def time_split(df: pd.DataFrame, valid_days=14, test_days=14):
    """Split by DateTime from the end: [train | valid | test]."""
    last_time = df[TIME_COL].max()
    test_start  = last_time - pd.Timedelta(days=test_days) + pd.Timedelta(hours=1)
    valid_start = test_start - pd.Timedelta(days=valid_days)

    train = df[df[TIME_COL] < valid_start]
    valid = df[(df[TIME_COL] >= valid_start) & (df[TIME_COL] < test_start)]
    test  = df[df[TIME_COL] >= test_start]
    return train, valid, test

def train_xgb(train, valid, features, TARGET="Volume"):
    X_train, y_train = train[features], train[TARGET]
    X_valid, y_valid = valid[features], valid[TARGET]

    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=2000,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        tree_method="hist",
        enable_categorical=True,   # keep if your features include pandas categoricals
        eval_metric="rmse",        # set here (not in fit)
        random_state=42,
    )

    es = EarlyStopping(
        rounds=100,     # patience
        save_best=True, # keep the best iteration
        maximize=False  # for RMSE lower is better
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_valid, y_valid)],
        callbacks=[es],
        verbose=False
    )
    return model

def evaluate(model, df, features, split_name="set"):
    preds = model.predict(df[features])
    y = df[TARGET].values
    mae = mean_absolute_error(y, preds)
    rmse = mean_squared_error(y, preds, squared=False)

    # sMAPE (robust to zeros)
    denom = (np.abs(y) + np.abs(preds))
    smape = np.mean(np.where(denom==0, 0, np.abs(y - preds) / denom)) * 2 * 100

    print(f"{split_name}: MAE={mae:.2f}, RMSE={rmse:.2f}, sMAPE={smape:.2f}%")
    return mae, rmse, smape

# ---------- USAGE ----------

print("Python:", sys.version)
print("XGBoost:", xgb.__version__)
print("fit signature:", inspect.signature(xgb.XGBRegressor.fit))

script_dir = os.path.dirname(os.path.abspath(__file__)) 
file_path = os.path.join(script_dir, "..", "data", "at-dataset", "final_data.csv")

df = pd.read_csv(file_path)
feat_df = make_features(df)

# Select features (exclude target and timestamp explicitly)
drop_cols = [TARGET, TIME_COL]
features = [c for c in feat_df.columns if c not in drop_cols]

train, valid, test = time_split(feat_df, valid_days=14, test_days=14)
model = train_xgb(train, valid, features)

print("Best iteration:", model.best_iteration)
evaluate(model, train, features, "train")
evaluate(model, valid, features, "valid")
evaluate(model, test,  features, "test")


