import json, numpy as np, pandas as pd, pathlib

def build_llm_json(
    shap_csv="shap_exports/shap_values.csv",
    features_csv=None,                 # e.g., "shap_exports/X_explain_sample.csv"
    pred_csv=None,                     # e.g., "shap_exports/predictions.csv" (columns: y_hat)
    ytrue_csv=None,                    # e.g., "shap_exports/y_true.csv" (columns: y_true)
    units="veh/hr",
    k_top=5,
    out_json="shap_exports/llm_pack.json",
    out_jsonl="shap_exports/llm_pack_local.jsonl"
):
    outdir = pathlib.Path(out_json).parent
    outdir.mkdir(parents=True, exist_ok=True)

    # --- Load SHAP matrix (rows=samples, cols=features)
    shap_df = pd.read_csv(shap_csv, index_col=0)
    feature_names = list(shap_df.columns)

    # Optional feature values
    X_df = None
    if features_csv:
        X_df = pd.read_csv(features_csv, index_col=0).reindex(shap_df.index)
        # Ensure same column order:
        X_df = X_df[feature_names]

    # Optional predictions / y_true
    y_hat = None
    if pred_csv:
        y_hat = pd.read_csv(pred_csv, index_col=0).reindex(shap_df.index)["y_hat"].to_numpy()

    y_true = None
    if ytrue_csv:
        y_true = pd.read_csv(ytrue_csv, index_col=0).reindex(shap_df.index)["y_true"].to_numpy()

    # --- Global explanations
    mean_abs = shap_df.abs().mean(axis=0).to_numpy()
    order_global = np.argsort(mean_abs)[::-1]
    top_global = [
        {"feature": feature_names[i], "mean_abs_shap": float(mean_abs[i]), "units": units}
        for i in order_global[:10]
    ]
    global_block = {
        "model": "TreeExplainer (SHAP)",
        "target": "veh_per_hr",
        "top_features": top_global
    }

    # --- Feature glossary (simple humanized names)
    glossary = {f: f.replace("_", " ") for f in feature_names}

    # --- Local explanations (Top-K per row)
    locals_list = []
    shap_np = shap_df.to_numpy()
    for r, idx in enumerate(shap_df.index.astype(str)):
        row = shap_np[r]
        ord_k = np.argsort(np.abs(row))[::-1][:k_top]
        contribs = []
        for j in ord_k:
            rec = {
                "feature": feature_names[j],
                "contribution": float(row[j]),
                "units": units
            }
            if X_df is not None:
                rec["value"] = float(X_df.iat[r, j])
            contribs.append(rec)

        loc = {
            "id": idx,
            "top_contributors": contribs,
            "units": units
        }
        if y_hat is not None:
            loc["y_hat"] = float(y_hat[r])
        if y_true is not None:
            loc["y_true"] = float(y_true[r])
        if y_hat is not None and y_true is not None:
            loc["residual"] = float(y_true[r] - y_hat[r])

        locals_list.append(loc)

    # --- Pack + save
    pack = {
        "feature_glossary": glossary,
        "global_explanations": global_block,
        "local_explanations": locals_list
    }
    pathlib.Path(out_json).write_text(json.dumps(pack, ensure_ascii=False, indent=2))

    # JSON Lines (1 record per local explanation) – handy for batching
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for rec in locals_list:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote:\n- {out_json}\n- {out_jsonl}")

# build_llm_json(
#     shap_csv="shap_exports/shap_values.csv",
#     features_csv="shap_exports/X_explain_sample.csv",   # set to None if you don't have it
#     pred_csv="shap_exports/predictions.csv",            # optional
#     ytrue_csv=None,                                     # optional
#     units="veh/15min",
#     k_top=5,
#     out_json="shap_exports/llm_pack.json",
#     out_jsonl="shap_exports/llm_pack_local.jsonl"
# )
