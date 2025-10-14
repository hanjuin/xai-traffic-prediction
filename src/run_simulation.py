import subprocess
from pathlib import Path
from datetime import datetime
import re


def run_simulation(modified_net_path: str):
    reg = r"\d{8}-\d{6}"
    timestamp = re.search(reg, modified_net_path)
    if timestamp:
        timestamp = timestamp.group(0)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path.cwd()/"results"/ "traffic_simulation_results"
    results_dir = outdir / f"run_{timestamp}"
    results_dir.mkdir(parents=True, exist_ok=True)

    sumo_cfg = Path.cwd() / "traffic simulation" / "2906" / "osm.sumocfg"
    detectors_file = Path.cwd() / "traffic simulation" / "2906" / "detectors.add.xml"

    detectors_content = detectors_file.read_text(encoding="utf-8")

    safe_path = (results_dir / "detector_output.xml").as_posix()
    updated = re.sub(r'file="[^"]+\.xml"', f'file="{safe_path}"', detectors_content)

    new_detectors_path = results_dir / "detectors.add.xml"
    new_detectors_path.write_text(updated, encoding="utf-8")

    # net_path = Path.cwd() / "Results" / "road-rebuild" / "20251010-181555" / "osm_policy_rebuilt-gpt5.net.xml"
    net_path = Path.cwd() / Path(modified_net_path)
    # net_path = Path.cwd() / "traffic simulation" / "2906" / "osm.net.xml.gz"

    # trips_path = Path.cwd() / "traffic simulation" / "2906" / "my_entry_exit_trips.trips.xml"
    trips_path = Path.cwd() / "traffic simulation" / "2906" / "average-trips-5692-0.5.trips.xml"
    # trips_path = Path.cwd() / "traffic simulation" / "2906" / "max-trips-15781-0.5.trips.xml"

    view_path = Path.cwd() / "traffic simulation" / "2906" / "osm.view.xml"

    cfg_content = sumo_cfg.read_text(encoding="utf-8")
    cfg_content = cfg_content.replace(
        'detectors.add.xml',
        str(new_detectors_path).replace("\\", "/")
    ).replace(
        'results/summary.xml',
        f'{results_dir}/summary.xml'
    ).replace(
        'osm.net.xml.gz',
        str(net_path).replace("\\", "/")
    ).replace(
        'my_entry_exit_trips.trips.xml',
        str(trips_path).replace("\\", "/")
    ).replace(
        'osm.view.xml',
        str(view_path).replace("\\", "/")
    )

    new_cfg_path = results_dir / "osm_config.sumocfg"
    new_cfg_path.write_text(cfg_content, encoding="utf-8")

    # === 5. Run SUMO ===
    print(f"Running SUMO... Results will be saved in: {results_dir}")
    # subprocess.run(["sumo-gui", "-c", str(new_cfg_path)], check=True)
    subprocess.run(["sumo", "-c", str(new_cfg_path)], check=True)

    print("Simulation finished!")
    return results_dir
