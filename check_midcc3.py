import yaml
with open("config/topology_gamma_aug.yaml") as f:
    t = yaml.safe_load(f)

print("H_crit SLA:", t["compliance_sets"]["H_crit"]["sla"]["latency_ms"]["threshold"])
print("H_cache SLA:", t["compliance_sets"]["H_cache"]["sla"]["latency_ms"]["threshold"])
print("edge_metrics path:", t.get("data_paths", {}).get("edge_metrics_csv", "MANCANTE"))
print("window_duration:", t.get("metadata", {}).get("window_duration_seconds", "MANCANTE"))