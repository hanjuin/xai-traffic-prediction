import xml.etree.ElementTree as ET
import pandas as pd
import textwrap
import os
import statistics
import json

# --- CONFIG ---
NETWORK_FILE = "traffic simulation/2906/osm.net.xml"
DETECTOR_FILE = "traffic simulation/2906/results/detector_output.xml"
SUMMARY_FILE = "traffic simulation/2906/results/summary.xml"
CONTEXT_FILE = "traffic simulation/2906/results/context.txt"
OUTPUT_PROMPT = "policy_prompt.txt"

# --- 1. Parse network info ---
def parse_network(file):
    try:
        print("Parsing network structure...")
        tree = ET.parse(file)
        root = tree.getroot()

        network_data = {
            "summary": {
                "total_edges": 0,
                "total_junctions": 0,
                "lefthand_driving": root.get("lefthand", "false") == "true",
            },
            "edges": [],
            "junctions": []
        }

        # --- Extract edges ---
        for e in root.findall("edge"):
            # Skip internal function edges (like :123_0)
            if e.get("function") == "internal":
                continue

            lanes = e.findall("lane")
            lane_speeds = []
            for lane in lanes:
                try:
                    lane_speeds.append(float(lane.get("speed", 0)))
                except:
                    pass

            edge_info = {
                "id": e.get("id"),
                "from": e.get("from"),
                "to": e.get("to"),
                "name": e.get("name"),
                "type": e.get("type"),
                "num_lanes": len(lanes),
                "avg_speed": round(statistics.mean(lane_speeds), 2) if lane_speeds else None,
            }
            network_data["edges"].append(edge_info)

        # --- Extract junctions ---
        for j in root.findall("junction"):
            network_data["junctions"].append({
                "id": j.get("id"),
                "type": j.get("type"),
                "x": float(j.get("x")),
                "y": float(j.get("y")),
                "incLanes": j.get("incLanes", "").split(),
                "has_signal": j.get("type") == "traffic_light"
            })

        # Update summary counts
        network_data["summary"]["total_edges"] = len(network_data["edges"])
        network_data["summary"]["total_junctions"] = len(network_data["junctions"])

        # Save JSON
        json_file = file.replace(".xml", "_summary.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(network_data, f, indent=2)

        print(f"Network summary saved to: {json_file}")
        return network_data

    except Exception as e:
        print(f"Error reading network: {e}")
        return {}

# --- 2. Parse detector output ---
def parse_detectors(file):
    try:
        tree = ET.parse(file)
        root = tree.getroot()
        rows = []
        for interval in root.findall("interval"):
            rows.append({
                "begin": interval.get("begin"),
                "end": interval.get("end"),
                "id": interval.get("id"),
                "flow": interval.get("flow"),
                "occupancy": interval.get("occupancy"),
                "speed": interval.get("speed"),
            })
        df = pd.DataFrame(rows)
        df["flow"] = df["flow"].astype(float)
        df["occupancy"] = df["occupancy"].astype(float)
        df["speed"] = df["speed"].astype(float)
        df_summary = df.groupby("id").agg({"flow":"mean","speed":"mean","occupancy":"mean"}).reset_index()
        return df_summary.head(10).to_string(index=False)
    except Exception as e:
        return f"Error reading detectors: {e}"

# --- 3. Parse summary file ---
def parse_summary(file):
    try:
        tree = ET.parse(file)
        root = tree.getroot()
        rows = []
        for step in root.findall("step"):
            rows.append({
                "time": step.get("time"),
                "running": step.get("running"),
                "meanSpeed": step.get("meanSpeed"),
                "meanTravelTime": step.get("meanTravelTime"),
            })
        df = pd.DataFrame(rows)
        df["meanSpeed"] = df["meanSpeed"].astype(float)
        df["meanTravelTime"] = df["meanTravelTime"].astype(float)
        df_summary = {
            "avg_speed": df["meanSpeed"].mean(),
            "avg_travel_time": df["meanTravelTime"].mean(),
            "total_steps": len(df)
        }
        return df_summary
    except Exception as e:
        return f"Error reading summary: {e}"

# --- 4. Load context file ---
def load_context(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return "(No context file found.)"
    
# --- 5. Load network file ---  
def load_network(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return "(No network file found.)"


# --- 5. Build LLM prompt ---
def build_prompt(network_info, detector_info, summary_info, context_info):
    prompt = textwrap.dedent(f"""
    You are a transportation policy advisor with expertise in intelligent transport systems (ITS), traffic management, and urban mobility optimization.

    Your task is to analyze the provided SUMO simulation results and related traffic data to propose realistic and data-driven traffic management policies.

    ### INPUTS

    **1. Network Structure**
    {network_info}

    **2. Detector Data**
    {detector_info}

    **3. Simulation Summary**
    Average speed: {summary_info.get("avg_speed", "N/A")} m/s
    Average travel time: {summary_info.get("avg_travel_time", "N/A")} s
    Simulation steps: {summary_info.get("total_steps", "N/A")}

    **4. Metadata / Context**
    {context_info}

    ### TASK
    1. Identify key congestion areas and inefficiencies.
    2. Suggest short-, medium-, and long-term traffic management policies.
    3. Justify each policy based on the data above.
    4. Format results as a table with: Category | Policy | Description | Evidence | Expected Impact.

    Generate your policy recommendations below:
    """)
    return prompt

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    network_info = parse_network(NETWORK_FILE)
    detector_info = parse_detectors(DETECTOR_FILE)
    summary_info = parse_summary(SUMMARY_FILE)
    context_info = load_context(CONTEXT_FILE)
    # network_text = load_network(NETWORK_FILE)

    prompt = build_prompt(network_info, detector_info, summary_info, context_info)

    with open(OUTPUT_PROMPT, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"Policy prompt generated and saved to: {OUTPUT_PROMPT}")
