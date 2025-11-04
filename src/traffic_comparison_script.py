import xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path
import math

def parse_summary(path):
    tree = ET.parse(path)
    root = tree.getroot()
    rows = []
    for step in root.iter("step"):
        rec = {}
        for k, v in step.attrib.items():
            try:
                rec[k] = float(v)
            except:
                rec[k] = v
        rows.append(rec)
    df = pd.DataFrame(rows)
    last = df.iloc[-1].to_dict() if not df.empty else {}
    return df, {
        "last_time": last.get("time"),
        "arrived_total": last.get("arrived"),
        "ended_total": last.get("ended"),
        "teleports_total": last.get("teleports"),
        "running": last.get("running"),
        "waiting": last.get("waiting"),
        "mean_speed_avg": float(df["meanSpeed"].replace(-1, pd.NA).dropna().mean()) if "meanSpeed" in df else None,
        "mean_travel_time_last": last.get("meanTravelTime"),
        "mean_waiting_time_avg": float(df["meanWaitingTime"].mean()) if "meanWaitingTime" in df else None,
        "steps": len(df),
    }

def parse_detector_totals(path):
    tree = ET.parse(path)
    root = tree.getroot()
    totals_by_id = {}
    count_rows = 0
    speed_sum = 0.0
    speed_count = 0
    total_nVehEntered = 0.0
    total_nVehContrib = 0.0
    for it in root.iter("interval"):
        count_rows += 1
        id_ = it.attrib.get("id")
        nve = float(it.attrib.get("nVehEntered", "0"))
        nvc = float(it.attrib.get("nVehContrib", "0"))
        spd = float(it.attrib.get("speed", "-1"))
        total_nVehEntered += nve
        total_nVehContrib += nvc
        if spd >= 0:
            speed_sum += spd
            speed_count += 1
        if id_ not in totals_by_id:
            totals_by_id[id_] = {"id": id_, "nVehEntered": 0.0, "nVehContrib": 0.0, "flow": 0.0}
        totals_by_id[id_]["nVehEntered"] += nve
        totals_by_id[id_]["nVehContrib"] += nvc
        try:
            totals_by_id[id_]["flow"] += float(it.attrib.get("flow", "0"))
        except:
            pass
    by_id_df = pd.DataFrame(list(totals_by_id.values()))
    avg_speed = (speed_sum / speed_count) if speed_count else None
    return by_id_df, {
        "interval_rows": count_rows,
        "detector_count": by_id_df["id"].nunique() if not by_id_df.empty else 0,
        "total_nVehEntered_all_detectors": total_nVehEntered,
        "total_nVehContrib_all_detectors": total_nVehContrib,
        "avg_speed_all_rows": avg_speed,
    }

def comparison_script_2(base_dir, new_dir):

    outdir = Path.cwd() / base_dir
    newdir = Path.cwd() / new_dir

    paths = {
        "baseline_summary": str(outdir / "summary.xml"),
        "baseline_detector": str(outdir / "detector_output.xml"),
        "new_summary": str(newdir / "summary.xml"),
        "new_detector": str(newdir / "detector_output.xml"),
    }

    # Parse files
    b_sum_df, b_sum = parse_summary(paths["baseline_summary"])
    n_sum_df, n_sum = parse_summary(paths["new_summary"])
    b_det_df, b_det = parse_detector_totals(paths["baseline_detector"])
    n_det_df, n_det = parse_detector_totals(paths["new_detector"])

    def row(metric, b, n):
        try:
            delta = (n - b) if (b is not None and n is not None) else None
        except TypeError:
            delta = None
        return {"metric": metric, "baseline": b, "new": n, "delta (new - base)": delta}

    comp_rows = [
        row("Simulation end time (s)", b_sum["last_time"], n_sum["last_time"]),
        row("Total arrived vehicles", b_sum["arrived_total"], n_sum["arrived_total"]),
        row("Total teleports", b_sum["teleports_total"], n_sum["teleports_total"]),
        row("Vehicles still running at end", b_sum["running"], n_sum["running"]),
        row("Vehicles waiting at end", b_sum["waiting"], n_sum["waiting"]),
        row("Avg. mean speed over steps (m/s)", b_sum["mean_speed_avg"], n_sum["mean_speed_avg"]),
        row("Mean travel time at end (s)", b_sum["mean_travel_time_last"], n_sum["mean_travel_time_last"]),
        row("Avg. mean waiting time over steps (s)", b_sum["mean_waiting_time_avg"], n_sum["mean_waiting_time_avg"]),
        row("# summary steps", b_sum["steps"], n_sum["steps"]),
        row("Detector interval rows", b_det["interval_rows"], n_det["interval_rows"]),
        row("Detector count", b_det["detector_count"], n_det["detector_count"]),
        row("Total nVehEntered across detectors", b_det["total_nVehEntered_all_detectors"], n_det["total_nVehEntered_all_detectors"]),
        row("Total nVehContrib across detectors", b_det["total_nVehContrib_all_detectors"], n_det["total_nVehContrib_all_detectors"]),
        row("Avg detector speed over intervals (m/s)", b_det["avg_speed_all_rows"], n_det["avg_speed_all_rows"]),
    ]

    comp_df = pd.DataFrame(comp_rows)

    # Per-detector detail
    per_det = pd.merge(b_det_df, n_det_df, on="id", how="outer", suffixes=("_base","_new")).fillna(0)
    per_det["delta_nVehEntered"] = per_det["nVehEntered_new"] - per_det["nVehEntered_base"]
    per_det["delta_nVehContrib"] = per_det["nVehContrib_new"] - per_det["nVehContrib_base"]
    per_det["delta_flow"] = per_det["flow_new"] - per_det["flow_base"]

    # Save CSVs
    out1 = newdir / "network_comparison_summary.csv"
    out2 = newdir / "per_detector_comparison.csv"
    comp_df.to_csv(out1, index=False)
    per_det.to_csv(out2, index=False)

    print("Wrote:", out1.resolve())
    print("Wrote:", out2.resolve())

    return newdir


def comparison_script_3(base_dir, new_dir, improved_dir):
    outdir = Path.cwd() / base_dir
    newdir = Path.cwd() / new_dir
    imprdir = Path.cwd() / improved_dir  # improved (aka latest)

    paths = {
        "baseline_summary": str(outdir / "summary.xml"),
        "baseline_detector": str(outdir / "detector_output.xml"),
        "new_summary": str(newdir / "summary.xml"),
        "new_detector": str(newdir / "detector_output.xml"),
        "improved_summary": str(imprdir / "summary.xml"),
        "improved_detector": str(imprdir / "detector_output.xml"),
    }

    b_sum_df, b_sum = parse_summary(paths["baseline_summary"])
    n_sum_df, n_sum = parse_summary(paths["new_summary"])
    i_sum_df, i_sum = parse_summary(paths["improved_summary"])

    b_det_df, b_det = parse_detector_totals(paths["baseline_detector"])
    n_det_df, n_det = parse_detector_totals(paths["new_detector"])
    i_det_df, i_det = parse_detector_totals(paths["improved_detector"])

    def _safe_delta(a, b):
        try:
            if a is None or b is None:
                return None
            if isinstance(a, float) and math.isnan(a):
                return None
            if isinstance(b, float) and math.isnan(b):
                return None
            return a - b
        except Exception:
            return None

    def row(metric, b, n, i):
        return {
            "metric": metric,
            "baseline": b,
            "new": n,
            "improved": i,
            "delta(new−base)": _safe_delta(n, b),
            "delta(impr−new)": _safe_delta(i, n),
            "delta(impr−base)": _safe_delta(i, b),
        }

    comp_rows = [
        row("Simulation end time (s)",                  b_sum.get("last_time"),            n_sum.get("last_time"),            i_sum.get("last_time")),
        row("Total arrived vehicles",                   b_sum.get("arrived_total"),        n_sum.get("arrived_total"),        i_sum.get("arrived_total")),
        row("Total teleports",                          b_sum.get("teleports_total"),      n_sum.get("teleports_total"),      i_sum.get("teleports_total")),
        row("Vehicles still running at end",            b_sum.get("running"),              n_sum.get("running"),              i_sum.get("running")),
        row("Vehicles waiting at end",                  b_sum.get("waiting"),              n_sum.get("waiting"),              i_sum.get("waiting")),
        row("Avg. mean speed over steps (m/s)",         b_sum.get("mean_speed_avg"),       n_sum.get("mean_speed_avg"),       i_sum.get("mean_speed_avg")),
        row("Mean travel time at end (s)",              b_sum.get("mean_travel_time_last"),n_sum.get("mean_travel_time_last"),i_sum.get("mean_travel_time_last")),
        row("Avg. mean waiting time over steps (s)",    b_sum.get("mean_waiting_time_avg"),n_sum.get("mean_waiting_time_avg"),i_sum.get("mean_waiting_time_avg")),
        row("# summary steps",                           b_sum.get("steps"),                n_sum.get("steps"),                i_sum.get("steps")),
        row("Detector interval rows",                    b_det.get("interval_rows"),        n_det.get("interval_rows"),        i_det.get("interval_rows")),
        row("Detector count",                            b_det.get("detector_count"),       n_det.get("detector_count"),       i_det.get("detector_count")),
        row("Total nVehEntered across detectors",        b_det.get("total_nVehEntered_all_detectors"), n_det.get("total_nVehEntered_all_detectors"), i_det.get("total_nVehEntered_all_detectors")),
        row("Total nVehContrib across detectors",        b_det.get("total_nVehContrib_all_detectors"), n_det.get("total_nVehContrib_all_detectors"), i_det.get("total_nVehContrib_all_detectors")),
        row("Avg detector speed over intervals (m/s)",   b_det.get("avg_speed_all_rows"),   n_det.get("avg_speed_all_rows"),   i_det.get("avg_speed_all_rows")),
    ]

    comp_df = pd.DataFrame(comp_rows)

    per_det = pd.merge(
        pd.merge(b_det_df, n_det_df, on="id", how="outer", suffixes=("_base", "_new")),
        i_det_df.add_suffix("_impr").rename(columns={"id_impr": "id"}),
        on="id", how="outer"
    ).fillna(0)

    def add_delta(col):
        base = f"{col}_base"
        new  = f"{col}_new"
        impr = f"{col}_impr"
        if base in per_det and new in per_det and impr in per_det:
            per_det[f"Δ_{col}(new−base)"] = per_det[new] - per_det[base]
            per_det[f"Δ_{col}(impr−new)"] = per_det[impr] - per_det[new]
            per_det[f"Δ_{col}(impr−base)"] = per_det[impr] - per_det[base]

    for col in ["nVehEntered", "nVehContrib", "flow", "speed", "occupancy", "harmonicMeanSpeed", "length"]:
        add_delta(col)

    out1 = imprdir / "network_comparison_summary.csv"
    out2 = imprdir / "per_detector_comparison.csv"
    comp_df.to_csv(out1, index=False)
    per_det.to_csv(out2, index=False)

    print("Wrote:", out1.resolve())
    print("Wrote:", out2.resolve())

    return imprdir

