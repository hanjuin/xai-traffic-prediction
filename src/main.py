import datetime
import json
import textwrap
from openai import OpenAI
import dotenv
import xml.etree.ElementTree as ET
import pandas as pd
import convert_shap_json as csj

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
def build_prompt(network_info, detector_info, summary_info, context_info, network_text):
    schema_hint = json.dumps({
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
                "type": "update_attribute or create_element",
                "target": "edge/junction/tlLogic",
                "id": "string",
                "attribute": "string (optional)",
                "new_value": "string (for updates)",
                "xml_snippet": "string (for new tlLogic creation)"
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
    Analyze the provided network, detector data, and simulation summary to:
    - Identify congestion and inefficiencies.
    - Propose policy-based changes (lane speed, junction control, signal timing).
    - **Add traffic lights (tlLogic) to junctions that need signalization**.

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

    ### OUTPUT FORMAT
    Respond in valid JSON using this schema:
    {schema_hint}

    ### RULES
    - Modify only necessary elements:
      - Update `lane` speed, `junction` type, or `tlLogic` phases.
      - If a junction shows high congestion and is currently `priority` or `unregulated`, **create a new tlLogic** with reasonable phase durations (e.g., 45–60 s cycles).
    - When creating a new tlLogic:
      - Include a valid `<tlLogic id="..." type="actuated">` element in `modified_snippets`.
      - Make sure the `tlLogic` ID matches the `junction` ID or use a prefix like `TL_`.
      - Include at least 3–4 `<phase>` elements (e.g., green/yellow/red combinations).
    - Do not return the entire network XML — only the modified snippets.
    - Escape double quotes (") inside XML as (\") to maintain valid JSON.

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
    detector_file="results/traffic_simulation_results/baseline/baseline_detector_output.xml",
    summary_file="results/traffic_simulation_results/baseline/baseline_summary.xml",
    context_file="results/llm/context.txt",
    xai_file = "results/shap_exports/2906-20251009-165634/shap_values.json" ## need to change 
):
    # --- Read inputs ---
    net_info = parse_network(network_file)
    with open(context_file, "r", encoding="utf-8") as f:
        context_info = f.read().strip()

    # You can summarize detector/summary externally; using placeholders for now:
    detector_info = parse_detectors(detector_file)
    summary_info = parse_summary(summary_file)

    with open(network_file, "r", encoding="utf-8") as f:
        net_text = f.read()  

    with open(xai_file, "r", encoding="utf-8") as f:
        xai_info = json.load(f)

    # --- Build prompt ---
    prompt = build_prompt(net_info, detector_info, summary_info, context_info, net_text)
    with open("llm_policy_prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    # return prompt
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

    with open(f"results/llm/raw_llm_output-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt", "w", encoding="utf-8") as f: # to test
        f.write(message.content)
    return message

# ------------------------------------------------------------
# 4. Main entry
# ------------------------------------------------------------
if __name__ == "__main__":
    generate_policy_network()
