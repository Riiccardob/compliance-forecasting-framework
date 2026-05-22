# scripts/diagnose_user_csv.py
import pandas as pd
import numpy as np
from pathlib import Path

CSV = Path("DATASET/processed_dataset/user/multi-modal-data-separate/"
           "mem_sep22_10min_800_0_graph_2.csv")

df = pd.read_csv(CSV)

lat_cols = [f"{i}_latency" for i in range(9)]
start_cols = [f"{i}_start" for i in range(9)]

print("=" * 60)
print(f"FILE: {CSV.name}")
print(f"Righe totali: {len(df)}")
print(f"Finestre uniche (window_id): {df['window_id'].nunique()}")
print(f"Tracce per finestra - media: "
      f"{df.groupby('window_id').size().mean():.1f}")

print("\n=== STATISTICHE LATENZA PER COLONNA (valori in microsecondi) ===")
desc = df[lat_cols].describe().round(0)
print(desc.to_string())

print("\n=== QUANTE RIGHE HANNO LATENZA = 0 ===")
for col in lat_cols:
    n_zero = (df[col] == 0).sum()
    n_nan  = df[col].isna().sum()
    print(f"  {col}: zero={n_zero}, NaN={n_nan}")

print("\n=== SOGLIA 500μs: quante tracce hanno latenza SOTTO soglia ===")
# Se una colonna ha molte righe < 500μs, quel nodo e' probabilmente non visitato
# (o e' un'operazione Redis in-memory quasi istantanea)
threshold = 500
for col in lat_cols:
    n_below = (df[col] < threshold).sum()
    pct = 100 * n_below / len(df)
    print(f"  {col}: {n_below} righe ({pct:.1f}%) sotto {threshold}μs")

print("\n=== SOGLIA 100μs: quasi-zero (nodo non visitato?) ===")
threshold2 = 100
for col in lat_cols:
    n_below = (df[col] < threshold2).sum()
    pct = 100 * n_below / len(df)
    print(f"  {col}: {n_below} righe ({pct:.1f}%) sotto {threshold2}μs")

print("\n=== DISTRIBUZIONE LABEL ===")
print(df['label_trace'].value_counts().sort_index())

print("\n=== ESEMPIO: prime 3 righe, solo latenze ===")
print(df[lat_cols].head(3).to_string())

print("\n=== CONTA TRACCE PER PATH (approssimato) ===")
# Un proxy del path e' quanti nodi hanno latenza significativa (>500μs)
df['n_hops_significant'] = (df[lat_cols] >= threshold).sum(axis=1)
print(df['n_hops_significant'].value_counts().sort_index())

print("\n=== COLONNE RPC LABEL ===")
rpc_cols = [c for c in df.columns if '_label_RPC' in c]
print(f"RPC label columns: {rpc_cols}")
print(df[rpc_cols].value_counts().head(10))