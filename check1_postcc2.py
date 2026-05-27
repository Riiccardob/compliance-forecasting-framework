import pandas as pd
from pathlib import Path

gt    = pd.read_csv("data/converted/ground_truth.csv")
edges = pd.read_csv("data/converted/edge_metrics_aug_ramp.csv")

n_nom = gt[gt["label_trace"]==0].groupby("source_file").size().rename("n_nominal")
low   = n_nom[n_nom < 10]
print(f"Esperimenti con n_nominal < 10: {len(low)}")
print(low.sort_values())