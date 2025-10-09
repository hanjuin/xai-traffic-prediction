# modified_network.py — actuated signals + robust linking + per-junction tuning
import xml.etree.ElementTree as ET
import json
import re
import subprocess
import os
from collections import defaultdict

# ---------------------------
# Helpers
# ---------------------------

def safe_load_llm_json(path_or_str):
    if os.path.exists(path_or_str):
        with open(path_or_str, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = path_or_str
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        candidate = m.group(0).replace('\r', '')
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    with open("invalid_llm_output.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print("Could not parse LLM JSON; raw content saved to invalid_llm_output.txt")
    return None


def write_xml(tree, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"Saved: {path}")


def rebuild_with_netconvert(input_net, output_net, netconvert_path="netconvert"):
    os.makedirs(os.path.dirname(output_net), exist_ok=True)
    try:
        subprocess.run(
            [netconvert_path, "-s", input_net, "-o", output_net],
            check=True, capture_output=True, text=True
        )
        print(f"Rebuilt with netconvert → {output_net}")
        return True
    except subprocess.CalledProcessError as e:
        print("netconvert failed:\n", e.stderr)
        print("Ensure netconvert is in PATH or pass full path with netconvert_path=...")
        return False


def count_and_assign_link_indices(root):
    """
    Build tl_id -> list(connections) and ensure linkIndex 0..n-1 per tl.
    """
    tl_to_conns = defaultdict(list)
    for conn in root.findall("connection"):
        tl = conn.get("tl")
        if tl:
            tl_to_conns[tl].append(conn)
    for tl_id, conns in tl_to_conns.items():
        for idx, c in enumerate(conns):
            c.set("linkIndex", str(idx))
    return tl_to_conns


# ---------------------------
# Tuning config
# ---------------------------

DEFAULT_TUNING = {
    "defaults": {
        "main_share": 0.6,             # portion of links treated as “mainline”
        "green": {
            "main": {"min": 10, "max": 70, "dur": 35},
            "side": {"min": 7,  "max": 40, "dur": 25}
        },
        "yellow": 3                    # seconds for both yellows
    },
    "per_tl": {
        # "TL_25772784": {
        #   "main_share": 0.7,
        #   "green": {
        #       "main": {"min": 12, "max": 80, "dur": 40},
        #       "side": {"min": 7,  "max": 30, "dur": 20}
        #   },
        #   "yellow": 3
        # }
    }
}

def load_tuning_config(path=None):
    if not path:
        return DEFAULT_TUNING
    if not os.path.exists(path):
        print(f"ℹTuning file not found, using defaults: {path}")
        return DEFAULT_TUNING
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # shallow-merge with defaults
        merged = DEFAULT_TUNING.copy()
        merged["defaults"] = {**DEFAULT_TUNING["defaults"], **cfg.get("defaults", {})}
        merged["per_tl"] = {**DEFAULT_TUNING["per_tl"], **cfg.get("per_tl", {})}
        print(f"🧩 Loaded tuning config: {path}")
        return merged
    except Exception as e:
        print(f"Failed to load tuning config, using defaults. ({e})")
        return DEFAULT_TUNING


def _states_for_links(n_links, main_share):
    """
    Return four state strings (main G, main y, side G, side y) sized to n_links,
    based on how many links are considered “mainline” by main_share.
    """
    if n_links <= 0:
        return "", "", "", ""
    m = max(1, int(round(n_links * float(main_share))))
    m = min(m, n_links - 1) if n_links > 1 else 1
    p1 = ''.join('G' if i <  m else 'r' for i in range(n_links))  # main green
    p2 = ''.join('y' if i <  m else 'r' for i in range(n_links))  # main yellow
    p3 = ''.join('r' if i <  m else 'G' for i in range(n_links))  # side green
    p4 = ''.join('r' if i <  m else 'y' for i in range(n_links))  # side yellow
    return p1, p2, p3, p4


def build_actuated_phases_from_cfg(n_links, cfg_for_tl):
    """
    Build actuated phases using a (per-TL) tuning dict:
    {
      "main_share": 0.7,
      "green": {"main":{"min":10,"max":70,"dur":35}, "side":{"min":7,"max":35,"dur":25}},
      "yellow": 3
    }
    Returns list of (minDur, maxDur, duration, state)
    """
    d = cfg_for_tl
    main_share = float(d.get("main_share", DEFAULT_TUNING["defaults"]["main_share"]))
    g = d.get("green", {})
    g_main = g.get("main", {})
    g_side = g.get("side", {})

    main_min = int(g_main.get("min", DEFAULT_TUNING["defaults"]["green"]["main"]["min"]))
    main_max = int(g_main.get("max", DEFAULT_TUNING["defaults"]["green"]["main"]["max"]))
    main_dur = int(g_main.get("dur", DEFAULT_TUNING["defaults"]["green"]["main"]["dur"]))
    side_min = int(g_side.get("min", DEFAULT_TUNING["defaults"]["green"]["side"]["min"]))
    side_max = int(g_side.get("max", DEFAULT_TUNING["defaults"]["green"]["side"]["max"]))
    side_dur = int(g_side.get("dur", DEFAULT_TUNING["defaults"]["green"]["side"]["dur"]))

    yellow = int(d.get("yellow", DEFAULT_TUNING["defaults"]["yellow"]))

    p1, p2, p3, p4 = _states_for_links(n_links, main_share)
    return [
        (main_min, main_max, main_dur, p1),
        (yellow,  yellow,    yellow,   p2),
        (side_min, side_max, side_dur, p3),
        (yellow,   yellow,   yellow,   p4),
    ]


# ---------------------------
# Core functions
# ---------------------------

def merge_tlLogic_snippets(original_net, llm_json, merged_out_path):
    """
    Merge new/updated <tlLogic> elements from LLM JSON and link junctions (type + tl attr).
    Returns parsed ElementTree for further processing.
    """
    print("Merging tlLogic snippets…")
    tree = ET.parse(original_net)
    root = tree.getroot()

    data = safe_load_llm_json(llm_json) if isinstance(llm_json, str) else llm_json
    if data is None:
        print("No valid LLM JSON to merge.")
        write_xml(tree, merged_out_path)
        return tree

    snippets = data.get("modified_snippets", [])
    actions  = data.get("actions", [])

    # 1) Insert/replace tlLogic elements
    for snip in snippets:
        try:
            elem = ET.fromstring(snip)
            if elem.tag != "tlLogic":
                continue
            tl_id = elem.get("id")
            existing = root.find(f".//tlLogic[@id='{tl_id}']")
            if existing is not None:
                root.remove(existing)
                print(f"Replaced tlLogic {tl_id}")
            else:
                print(f"Added tlLogic {tl_id}")
            root.append(elem)
        except Exception as e:
            print(f"Skipped non-XML or invalid snippet: {str(e)}")

    # 2) Set junction type + tl attr from actions
    for act in actions:
        if act.get("type") == "create_element" and act.get("target") == "tlLogic":
            tl_id = act.get("id")
            junc_id = tl_id.replace("TL_", "")
            j = root.find(f".//junction[@id='{junc_id}']")
            if j is None:
                # cluster fallback
                for jj in root.findall("junction"):
                    if junc_id in (jj.get("id") or ""):
                        j = jj
                        break
            if j is not None:
                j.set("type", "traffic_light")
                j.set("tl", tl_id)
                print(f"Linked junction {j.get('id')} → {tl_id}")
            else:
                print(f"Could not find junction for tlLogic {tl_id}")

    write_xml(tree, merged_out_path)
    return tree


def link_connections_to_tllogic(tree, linked_out_path):
    """
    For every junction with type='traffic_light' and a 'tl' id:
    - Link all connections whose 'via' includes :<junction_id>_ (or contains that token)
    - Remove uncontrolled="1"
    - Ensure linkIndex is compact 0..n-1
    """
    print("Linking connections to traffic lights…")
    root = tree.getroot()

    # Build map of junction_id -> tl_id
    junc_to_tl = {}
    for j in root.findall("junction"):
        if j.get("type") == "traffic_light":
            tl_id = j.get("tl") or f"TL_{j.get('id')}"
            j.set("tl", tl_id)
            junc_to_tl[j.get("id")] = tl_id

    total_linked = 0
    for conn in root.findall("connection"):
        via = conn.get("via", "")
        if not via:
            continue
        for junc_id, tl_id in junc_to_tl.items():
            if f":{junc_id}_" in via or via.endswith(f":{junc_id}") or f":{junc_id}" in via:
                conn.attrib.pop("uncontrolled", None)
                conn.set("tl", tl_id)
                if conn.get("state") is None:
                    conn.set("state", "O")
                total_linked += 1
                break

    tl_to_conns = count_and_assign_link_indices(root)
    write_xml(tree, linked_out_path)
    print(f"Linked {total_linked} connections across {len(tl_to_conns)} signals")
    return tl_to_conns


def ensure_tllogic_programs(tree, tl_to_conns, ensured_out_path, tuning_cfg):
    """
    Ensure each tlLogic exists and has actuated phases sized to number of controlled links,
    using per-junction tuning config when available.
    """
    print("Ensuring tlLogic programs (actuated, tuned)…")
    root = tree.getroot()
    existing = {tl.get("id"): tl for tl in root.findall("tlLogic")}
    changed = 0

    # convenience shortcuts
    defaults = tuning_cfg.get("defaults", {})
    per_tl   = tuning_cfg.get("per_tl", {})

    for tl_id, conns in tl_to_conns.items():
        n_links = len(conns)
        if n_links <= 0:
            continue

        # get per-TL override or defaults
        tl_cfg = {**defaults, **per_tl.get(tl_id, {})}

        tl = existing.get(tl_id)
        regen = False

        if tl is None:
            tl = ET.Element("tlLogic", id=tl_id, type="actuated", programID="0", offset="0")
            root.append(tl)
            existing[tl_id] = tl
            regen = True
            print(f"Created tlLogic {tl_id} (no existing program)")

        # ensure actuated
        if tl.get("type") != "actuated":
            tl.set("type", "actuated")
            regen = True

        if not regen:
            phases = tl.findall("phase")
            if not phases:
                regen = True
            else:
                for p in phases:
                    if len(p.get("state", "")) != n_links:
                        regen = True
                        break

        if regen:
            # wipe old phases
            for p in list(tl):
                tl.remove(p)
            for minDur, maxDur, dur, state in build_actuated_phases_from_cfg(n_links, tl_cfg):
                ET.SubElement(
                    tl, "phase",
                    duration=str(dur),
                    minDur=str(minDur),
                    maxDur=str(maxDur),
                    state=state
                )
            changed += 1
            print(f"Regenerated actuated (tuned) phases for {tl_id} with {n_links} links")

    write_xml(tree, ensured_out_path)
    print(f"tlLogic check complete (updated {changed} programs)")
    return tree


# ---------------------------
# Orchestrator
# ---------------------------

def apply_policy_updates(
    original_net=os.path.join("traffic simulation", "2906", "osm.net.xml"),
    llm_json_path="results/llm/response/raw_llm_output-gpt5.txt",
    out_prefix="osm_policy",
    netconvert_path="netconvert",
    out_dir="results/road-rebuild",
    tuning_json_path=None   # ← NEW: optional tuning file
):
    """
    Pipeline:
    1) Merge tlLogic snippets + link junctions
    2) Link connections to those tlLogics
    3) Ensure tlLogic programs exist and are ACTUATED + sized (using tuning config)
    4) Rebuild with netconvert
    """
    merged  = os.path.join(out_dir, f"{out_prefix}_merged-gpt5.net.xml")
    linked  = os.path.join(out_dir, f"{out_prefix}_linked-gpt5.net.xml")
    ensured = os.path.join(out_dir, f"{out_prefix}_ensured-gpt5.net.xml")
    rebuilt = os.path.join(out_dir, f"{out_prefix}_rebuilt-gpt5.net.xml")

    # Load tuning
    tuning_cfg = load_tuning_config(tuning_json_path)

    # Step 1
    tree = merge_tlLogic_snippets(original_net, llm_json_path, merged)

    # Step 2
    tl_to_conns = link_connections_to_tllogic(tree, linked)

    # Step 3
    tree = ET.parse(linked)
    tree = ensure_tllogic_programs(tree, tl_to_conns, ensured, tuning_cfg)

    # Step 4
    ok = rebuild_with_netconvert(ensured, rebuilt, netconvert_path=netconvert_path)
    if ok:
        print("\nDone. Open this file in NetEdit / SUMO-GUI:")
        print(f"   {rebuilt}")
    else:
        print("\nRebuild failed. You can still inspect:")
        print(f"   {merged}\n   {linked}\n   {ensured}")


# ---------------------------
# CLI
# ---------------------------

if __name__ == "__main__":
    apply_policy_updates(
        original_net=os.path.join("traffic simulation", "2906", "osm.net.xml"),
        llm_json_path="results/llm/response/raw_llm_output-gpt5.txt",
        out_prefix="osm_policy",
        # netconvert_path=r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe",
        out_dir="results/road-rebuild",
        tuning_json_path="signal_tuning.json"   # drop a file with overrides here (optional)
    )
