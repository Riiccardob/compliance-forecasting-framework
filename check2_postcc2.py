import pandas as pd

# Leggi i due file e confronta
aug     = pd.read_csv("data/converted/edge_metrics_aug.csv")
aug_ramp = pd.read_csv("data/converted/edge_metrics_aug_ramp.csv")
gt       = pd.read_csv("data/converted/ground_truth.csv")

merged_aug  = aug.merge(gt[["timestamp","label_trace"]], on="timestamp", how="left")
merged_ramp = aug_ramp.merge(gt[["timestamp","label_trace"]], on="timestamp", how="left")

H_CRIT = ["e1","e2","e4","e6"]
SLA    = 284.4

# FP in edge_metrics_aug.csv (prima del ramp)
nom_pre  = merged_aug[merged_aug["label_trace"]==0]
agg_pre  = nom_pre[nom_pre["edge_id"].isin(H_CRIT)].groupby("timestamp")["latency_ms"].sum()
fp_pre   = (agg_pre > SLA).sum()

# FP in edge_metrics_aug_ramp.csv (dopo il ramp)
nom_post = merged_ramp[merged_ramp["label_trace"]==0]
agg_post = nom_post[nom_post["edge_id"].isin(H_CRIT)].groupby("timestamp")["latency_ms"].sum()
fp_post  = (agg_post > SLA).sum()

print(f"FP H_crit PRIMA del ramp: {fp_pre} ({fp_pre/len(agg_pre)*100:.2f}%)")
print(f"FP H_crit DOPO il ramp:   {fp_post} ({fp_post/len(agg_post)*100:.2f}%)")
print(f"Nuovi FP introdotti dal ramp: {fp_post - fp_pre}")