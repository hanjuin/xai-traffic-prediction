import datetime
import json
import os
from pathlib import Path
import textwrap
from openai import OpenAI
import dotenv
import xml.etree.ElementTree as ET
import pandas as pd
import convert_shap_json as csj
import modified_network as mn
import run_simulation as rs
import traffic_comparison_script as tcs

apikey = dotenv.get_key('.env', 'OPENAI_API_KEY')

# ------------------------------------------------------------
# 1. Network parser -> summarized JSON for context
# ------------------------------------------------------------
def parse_network(file):
    print("Parsing network structure...")
    tree = ET.parse(file)
    root = tree.getroot()

    edges = []
    for e in root.findall("edge"):
        if e.get("function") == "internal":
            continue
        lanes = e.findall("lane")
        speeds = [float(l.get("speed", 0)) for l in lanes if l.get("speed")]
        edges.append({
            "edge_id": e.get("id"),
            "name": e.get("name"),
            "from": e.get("from"),
            "to": e.get("to"),
            "type": e.get("type"),
            "num_lanes": len(lanes),
            "avg_speed": round(sum(speeds)/len(speeds), 2) if speeds else None
        })

    junctions = []
    for j in root.findall("junction"):
        junctions.append({
            "id": j.get("id"),
            "type": j.get("type"),
            "has_signal": j.get("type") == "traffic_light",
            "x": float(j.get("x", 0)),
            "y": float(j.get("y", 0))
        })

    summary = {
        "total_edges": len(edges),
        "total_junctions": len(junctions),
        "lefthand_driving": root.get("lefthand", "false") == "true"
    }

    return {"summary": summary, "edges": edges[:10], "junctions": junctions}  # trim for token limit


def parse_detectors(file):
    tree = ET.parse(file)
    root = tree.getroot()
    rows = []
    for i in root.findall("interval"):
        rows.append({
            "id": i.get("id"),
            "flow": float(i.get("flow", 0)),
            "speed": float(i.get("speed", 0)),
            "occupancy": float(i.get("occupancy", 0))
        })
    df = pd.DataFrame(rows)
    summary = (df.groupby("id")
               .agg(avg_flow=("flow", "mean"),
                    avg_speed=("speed", "mean"),
                    avg_occupancy=("occupancy", "mean"))
               .reset_index())
    summary["congestion_level"] = pd.cut(
        summary["avg_speed"],
        bins=[0,10,20,50],
        labels=["High","Moderate","Low"]
    )
    return summary.to_dict(orient="records")

def parse_summary(file):
    tree = ET.parse(file)
    root = tree.getroot()
    rows = []
    for s in root.findall("step"):
        rows.append({
            "time": float(s.get("time", 0)),
            "meanSpeed": float(s.get("meanSpeed", 0)),
            "meanTravelTime": float(s.get("meanTravelTime", 0)),
            "running": int(s.get("running", 0))
        })
    df = pd.DataFrame(rows)
    return {
        "avg_meanSpeed": round(df["meanSpeed"].mean(), 2),
        "avg_meanTravelTime": round(df["meanTravelTime"].mean(), 2),
        "total_vehicles": int(df["running"].max()),
        "simulation_steps": len(df)
    }

# ------------------------------------------------------------
# 2. Build COT JSON prompt
# ------------------------------------------------------------
def build_prompt(network_info, detector_info, summary_info, context_info, network_text, xai_info):
    schema_hint = json.dumps(
    {
        "reasoning": [
            {
                "edge_or_junction_id": "string",
                "issue_detected": "string",
                "proposed_policy": "string",
                "justification": "string"
            }
        ],
        "actions": [
            {
                "type": "update_attribute|create_element",
                "target": "tlLogic",
                "id": "string",
                "attribute": "offset|phase.duration",
                "new_value": "offset=NN; phase[0]=..; phase[1]=.. (if splits changed)",
                "corridor": {
                    "id": "string (e.g., 'Albert_St_Northbound')",
                    "order": ["J1","J2","J3"], 
                    "progression_speed_kmh": 40,
                    "segment_lengths_m": [180, 220],
                    "reference_junction": "J1"
                },
                "xml_snippet": "<tlLogic ...>...</tlLogic>"
            }
        ],
        "modified_snippets": [
            "<edge ...>...</edge>",
            "<junction ...>...</junction>",
            "<tlLogic ...>...</tlLogic>"
        ]
    }, indent=2)

    prompt = textwrap.dedent(f"""
    You are an expert in Intelligent Transport Systems (ITS) and SUMO traffic simulation.

    ### GOAL
    Analyze the provided network, detector data, simulation summary, and XAI evidence to:
    - Identify congestion and inefficiencies.
    - Propose policy-based changes (lane speed, junction control, signal timing).
    - Add traffic lights (tlLogic) to junctions that need signalization.
    - Fine-tune existing traffic signals based on evidence.

    ### INPUTS
    **1. Network Summary**
    {json.dumps(network_info, indent=2)}

    **2. Detector Data**
    {detector_info}

    **3. Simulation Summary**
    {json.dumps(summary_info, indent=2)}

    **4. Metadata / Context**
    {context_info}

    **5. Original Network XML**
    ```xml
    {network_text}
    ```
    **6. XAI Summary**
    ```
    {json.dumps(xai_info, indent=2)}
    ```

    ### OUTPUT FORMAT
    Respond in valid JSON using this schema:
    {schema_hint}

    ### RULES
    - Modify only what’s necessary:
        - Update `lane` speed, `junction` type, or `tlLogic` phases.
        - If a high-delay junction is `priority`/`unregulated`, **create a new tlLogic** with a reasonable cycle (45–90 s).
        - **If a `tlLogic` exists, you may fine-tune timing** (cycle length, phase splits, offset, min-greens) based on detector/XAI evidence.

    - Signal-timing constraints:
        - Cycle: 45–120 s. Yellow per movement: ≥ 3 s. All-red between conflicting greens: ≥ 1 s.
        - Pedestrian safety: do not reduce ped green below local standard (keep existing ped states if unknown).
        - Phase state string length must equal the number of controlled links.
        - Preserve protected vs permissive groupings unless evidence clearly supports a change.

    - Creating or editing `tlLogic`:
        - Use `<tlLogic id="..." type="actuated" programID="0" offset="...">` (or keep the existing `type` if present).
        - Include ≥ 3–4 `<phase>` elements; the sum of all `duration` ≈ desired cycle.
        - For fine-tuning, return the **full updated** `<tlLogic ...> ... </tlLogic>` in `modified_snippets`.
        - If adjusting only splits, change `duration`; if coordinating a corridor, also set `offset`.

    - Evidence linkage:
        - Tie each recommendation to `xai_evidence_ids` (from XAI local cases) and/or detector KPIs (queues, delay).
        - Prefer small, testable changes (±5–15 s per phase) unless evidence shows severe imbalance.

    - Green-wave (coordination):
        - Allowed when detectors/XAI show recurring platoons/queues along a corridor.
        - Keep a **common cycle (45–90 s)** across selected junctions where feasible.
        - **Green-wave calculation:** let progression speed be `v = progression_speed_kmh * (1000/3600)` [m/s].  
            For junction `i` in corridor order, compute  
            `offset_i ≈ round( ( Σ_{{k<i}}segment_length_k / v ) ) mod cycle`,  
            where `segment_length_k` is the link length (m) from junction `k` to `k+1`.
        - If local cycles differ slightly, either retime to the corridor cycle or set offsets modulo the local cycle.
        - Preserve yellow ≥ 3 s and all-red ≥ 1 s; do not reduce ped green below standard.
        - Prefer offset adjustments first; tweak splits only if detectors/XAI show phase imbalance.

    - Corridor metadata (when coordinating):
        - For each coordinated action, include a `corridor` object with: `{{ "id": "<name>", "order": ["J1","J2",...], "progression_speed_kmh": <num>, "segment_lengths_m": [..], "reference_junction": "J_ref" }}`.

    - Output contract:
        - Do not return the entire network—only modified elements.
        - Escape `"` as `\"` inside JSON strings.
        - If evidence is insufficient or uncertain, return `"actions": []`.

    ### EXAMPLES
    **New traffic light creation**
    ```json
    {{
      "actions": [
        {{
          "type": "create_element",
          "target": "tlLogic",
          "id": "TL_cluster_25772784",
          "xml_snippet": "<tlLogic id=\\"TL_cluster_25772784\\" type=\\"actuated\\" programID=\\"0\\" offset=\\"0\\">\\n  <phase duration=\\"45\\" state=\\"GGgrrr\\"/>\\n  <phase duration=\\"5\\" state=\\"yygrrr\\"/>\\n  <phase duration=\\"45\\" state=\\"rrrGGg\\"/>\\n  <phase duration=\\"5\\" state=\\"rrryyy\\"/>\\n</tlLogic>"
        }}
      ]
    }}
    ```

    ### OUTPUT REQUIREMENTS
    - Return **only JSON** with `reasoning`, `actions`, and `modified_snippets`.
    - Each XML snippet in `modified_snippets` must be a complete element (`<edge>...</edge>`, `<junction>...</junction>`, or `<tlLogic>...</tlLogic>`).
    """)
    return prompt

# ------------------------------------------------------------
# 3. LLM call
# ------------------------------------------------------------
def generate_policy_network(
    network_file="traffic simulation/2906/osm.net.xml",
    detector_file="results/traffic_simulation_results/run_20251010_133531_baseline/detector_output.xml",
    summary_file="results/traffic_simulation_results/run_20251010_133531_baseline/summary.xml",
    context_file="results/llm/context.txt",
    xai_file = "results/shap_exports/2906-20251010-165629/llm_shap_pack.json" ## need to change
):
    # --- Read inputs ---
    net_info = parse_network(network_file)
    with open(context_file, "r", encoding="utf-8") as f:
        context_info = f.read().strip()

    # parse detector and summary info
    detector_info = parse_detectors(detector_file)
    summary_info = parse_summary(summary_file)

    with open(network_file, "r", encoding="utf-8") as f:
        net_text = f.read()  

    with open(xai_file, "r", encoding="utf-8") as f:
        xai_info = json.load(f)

    # --- Build prompt ---
    prompt = build_prompt(net_info, detector_info, summary_info, context_info, net_text, xai_info)
    with open(f"results/llm/llm_policy_prompt-xai.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    # --- LLM call ---
    print("Sending prompt to OpenAI model...")
    client = OpenAI(api_key=apikey)
    response = client.chat.completions.create(
        model="gpt-5",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        # temperature=0.3,
    )

    message = response.choices[0].message

    print("LLM response received.")
    
    filedir = f"results/llm/response/raw_llm_output-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    with open(filedir, "w", encoding="utf-8") as f: 
        f.write(message.content)
    return filedir

# =========================
# Prompt Design for traffic fine tuning
# =========================
def build_prompt_2(network_info, comparison_info, detector_info):

    with open(network_info, "r", encoding="utf-8") as f:
        net_info = f.read()
    with open(comparison_info, "r", encoding="utf-8") as f:
        com_info = f.read()

    det = parse_detectors(detector_info)

    schema_hint = json.dumps(
    {
        "reasoning": [
            {
                "edge_or_junction_id": "string",
                "issue_detected": "string",
                "proposed_policy": "string",
                "justification": "string"
            }
        ],
        "actions": [
            {
                "type": "update_attribute|create_element",
                "target": "tlLogic",
                "id": "string",
                "attribute": "offset|phase.duration",
                "new_value": "offset=NN; phase[0]=..; phase[1]=.. (if splits changed)",
                "corridor": {
                    "id": "string (e.g., 'Albert_St_Northbound')",
                    "order": ["J1","J2","J3"], 
                    "progression_speed_kmh": 40,
                    "segment_lengths_m": [180, 220],
                    "reference_junction": "J1"
                },
                "xml_snippet": "<tlLogic ...>...</tlLogic>"
            }
        ],
        "modified_snippets": [
            "<edge ...>...</edge>",
            "<junction ...>...</junction>",
            "<tlLogic ...>...</tlLogic>"
        ]
    }, indent=2)

    prompt = textwrap.dedent(f"""
        You are an expert in Intelligent Transport Systems (ITS) and SUMO traffic simulation.

        ### GOAL
        Your task is to improve the traffic performance of an existing SUMO network by **modifying only the signal timing** of existing traffic lights.

        ### INPUTS
        1. **Network XML**:
            ```xml
            {net_info}
            ```
        2. **Comparison between baseline and new simulation results**:
            ```csv
            {com_info}
            ```
        3. **Detector Info**:
            ```json
            {json.dumps(det, indent=2)}
            ```
        
        ### TASK
        Focus on **optimizing the signal timing** of existing traffic lights to reduce congestion and improve flow.  
        Do **NOT** add or remove any traffic lights, junctions, or edges.

        Your analysis should:
        1. Identify which junctions are causing delays (low average speed or high occupancy).
        2. Propose realistic timing adjustments (e.g., increase green time for high-flow directions, reduce red time for low-demand approaches).
        3. Ensure the total cycle time remains consistent and safe (typically 60–120 s).
        4. Justify each change based on data.

        ### OUTPUT FORMAT
        Respond in valid JSON using this schema:
        {schema_hint}
        """)
    

    with open(f"results/llm/llm_finetune_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    print("Sending prompt to OpenAI model...")

    client = OpenAI(api_key=apikey)
    response = client.chat.completions.create(
        model="gpt-5",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        # temperature=0.3,
    )

    message = response.choices[0].message

    print("LLM response received.")
    
    filedir = f"results/llm/response/improved_raw_llm_output-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    with open(filedir, "w", encoding="utf-8") as f: 
        f.write(message.content)
    return filedir


# ------------------------------------------------------------
# 4. Main entry
# ------------------------------------------------------------
if __name__ == "__main__":
    file = generate_policy_network()
    modifiednet = mn.apply_policy_updates(
        original_net=os.path.join("traffic simulation", "2906", "osm.net.xml"),
        llm_json_path=file,
        out_prefix="osm_policy",
        # netconvert_path=r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe",
        out_dir= Path("results/road-rebuild"),
        tuning_json_path="signal_tuning.json"   # drop a file with overrides here (optional)
    )
    print(f"Modified network saved to: {modifiednet}")
    resultdir = rs.run_simulation(modifiednet)
    print(f"Simulation results saved to: {resultdir}")
    comparison_path = tcs.comparison_script_2(
        base_dir="results/traffic_simulation_results/run_20251010_133531_baseline",
        new_dir=resultdir
    )
    print("Comparison CSVs generated.")
    
    # =========================
    # Second iteration
    # =========================
    print("--- Starting second iteration for fine-tuning ---")
    print(f"Using modified network: {modifiednet}")
    print(f"Using comparison path: {comparison_path / 'network_comparison_summary.csv'}")
    print(f"Using detector file: {comparison_path / 'detector_output.xml'}")
    
    i = input("Press Enter to continue...")

    file = build_prompt_2(modifiednet, comparison_path / "network_comparison_summary.csv", comparison_path / "detector_output.xml")
    modifiednet = mn.apply_policy_updates(
        original_net=modifiednet,
        llm_json_path=file,
        out_prefix="osm_policy",
        # netconvert_path=r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe",
        out_dir= Path("results/road-rebuild"),
        tuning_json_path="signal_tuning.json"   # drop a file with overrides here (optional)
    )
    improved_resultdir = rs.run_simulation(modifiednet)
    print(f"Simulation results saved to: {resultdir}")
    tcs.comparison_script_3(
        base_dir="results/traffic_simulation_results/run_20251010_133531_baseline",
        new_dir=resultdir,
        improved_dir=improved_resultdir
    )
    print("Comparison CSVs generated.")
