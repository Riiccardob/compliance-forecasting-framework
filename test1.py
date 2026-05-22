import pandas as pd

gt   = pd.read_csv("data/converted/ground_truth.csv")
node = pd.read_csv("data/converted/node_metrics.csv")

ts_join = set(node["timestamp"].unique()) & set(gt["timestamp"].unique())
merged  = gt[gt["timestamp"].isin(ts_join)]
anom    = merged[merged["label_trace"] == 1]

print("Finestre anomale per fault_type:")
print(anom.groupby("fault_type").size())
print(f"\nTotale: {len(anom)}")

print("\nN source_file per fault_type con almeno 1 finestra anomala:")
print(anom.groupby("fault_type")["source_file"].nunique())