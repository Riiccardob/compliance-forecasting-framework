# Module 05 — FeatureSelector

## 1. Obiettivo del modulo

`FeatureSelector` implementa il Mapping M della Fase I (§3.1.3 di `methodology.tex`), producendo `M_direct ∪ M_interf` come dizionario di serie temporali input per il forecasting.

---

## 2. Interfaccia pubblica

```python
class FeatureSelector:
    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None

    def select_features(
        self,
        compliance_set_name: str,
        snapshots: list[dict],
    ) -> dict[str, pd.DataFrame]

    def get_feature_names(
        self,
        compliance_set_name: str,
    ) -> dict[str, list[str]]
```

**`select_features(compliance_set_name, snapshots) → dict[str, pd.DataFrame]`**
Estrae `M_direct ∪ M_interf` per il compliance set specificato. Restituisce un dizionario di serie temporali (vedere §4 per la convenzione di naming). Solleva `KeyError` se `compliance_set_name` non esiste in `topology.yaml`.

**`get_feature_names(compliance_set_name) → dict[str, list[str]]`**
Restituisce i nomi delle feature senza calcolare i valori: `{"direct": [...], "interference": [...]}`. Utile per ispezionare il mapping prima di eseguirlo. Stessa garanzia di ordinamento di `select_features`. Solleva `KeyError` se il compliance set non esiste.

### Metodi privati

| Firma | Comportamento |
|---|---|
| `_collect_interference_edges(compliance_set_name) → list[tuple[str, str]]` | Raccoglie tutti gli archi di interferenza M_interf iterando sugli altri compliance set; deduplica tramite `seen` set. |
| `_build_node_series(node_id, metric, snapshots) → pd.DataFrame` | Costruisce la serie temporale di una metrica di nodo; emette `logger.warning` e inserisce `float('nan')` per ogni snapshot in cui il nodo è assente. |
| `_build_edge_series(edge_id, metric, snapshots) → pd.DataFrame` | Costruisce la serie temporale di una metrica di arco; emette `logger.warning` e inserisce `float('nan')` per ogni snapshot in cui l'arco è assente. |

---

## 3. Definizioni formali implementate

**M_direct(H_Φi)**

```
M_direct(H_Φi) = { node:<v>:<m>   | v ∈ H_Φi,       m ∈ node_metrics  }
               ∪ { edge:<e>:<m>   | e ∈ A(H_Φi),    m ∈ edge_metrics  }
```

dove `A(H_Φi) = { e=(u,v) ∈ E | u ∈ H_Φi AND v ∈ H_Φi }` (archi interni al compliance set) e le liste `node_metrics` / `edge_metrics` sono lette da `topology.yaml` — nessun hardcoding.

> **Approssimazione dataset-driven (DSB vs sistema di riferimento):** methodology.tex §3.2.1.1 specifica per H_crit una selezione architettura-specifica: 2 metriche uniformi (cpu, mem) per tutti i nodi più metriche JVM per nodi specifici (gc_SIN, pool_SDB). Il dataset GAMMA/DSB non espone metriche JVM per singolo servizio. L'implementazione usa una selezione uniforme di tutte le metriche disponibili in `topology.yaml` (`node_metrics`): per DSB queste sono `cpu_percent`, `mem_mb`, `net_rx_mb`, `net_tx_mb`. Le metriche di rete (`net_rx_mb`, `net_tx_mb`) fungono da proxy delle metriche architetturali del sistema di riferimento non disponibili in GAMMA. Il risultato è 20 feature di nodo per H_crit invece delle 12 teoriche — una selezione conservativa (non esclude informazione).

**M_interf(H_Φi, H_Φj)**

```
M_interf(H_Φi, H_Φj) = { interf:<e>:throughput_rps | e=(u,v),
                           v ∈ Shared(H_Φi, H_Φj),
                           u ∉ H_Φi }
```

dove `Shared(H_Φi, H_Φj) = H_Φi ∩ H_Φj`. Solo `throughput_rps` è estratto: rappresenta il carico esterno sulle risorse condivise, non le latenze interne. `M_interf` è calcolato rispetto a tutti gli altri compliance set noti (non solo a coppie), con deduplicazione degli archi.

Nota: `throughput_rps` è l'unica costante di dominio non
   configurabile via YAML — è la sola metrica che quantifica il
   carico esterno sulle risorse condivise, come specificato in
   methodology.tex §3.1.3. Viene validata nel costruttore contro
   `edge_metrics` di topology.yaml.

**Portabilità:** se `throughput_rps` è assente da `edge_metrics` di `topology.yaml`, `FeatureSelector` emette `logger.warning` alla costruzione e imposta `M_interf = ∅` per tutti i compliance set. Non solleva `ValueError` — il modulo rimane utilizzabile per dataset senza metrica di throughput.

---

## 4. Formato delle chiavi e dei valori

### Naming delle chiavi

| Prefisso | Formato | Appartenenza |
|---|---|---|
| `node:` | `node:<node_id>:<metrica>` | M_direct — feature di nodo |
| `edge:` | `edge:<edge_id>:<metrica>` | M_direct — feature di arco |
| `interf:` | `interf:<edge_id>:throughput_rps` | M_interf — interferenza |

Esempi: `"node:nginx-web-server:cpu_percent"`, `"edge:e4:latency_ms"`, `"interf:e2:throughput_rps"`.

### Struttura dei valori

Ogni valore è un `pd.DataFrame` con:
- **Index**: `timestamp` (int µs, `index.name == "timestamp"`)
- **Colonne**: una sola colonna `"value"` (float o `float('nan')` se il nodo/arco è assente nello snapshot)
- **Lunghezza**: uguale al numero di snapshot in input

### Ordine delle chiavi

Le chiavi `node:` seguono l'ordine `sorted(cs_nodes)` (ordine lessicografico sui node ID). Le chiavi `edge:` seguono l'ordine degli archi in `topology.yaml`. Le chiavi `interf:` seguono l'ordine di visita degli altri compliance set. L'ordine è deterministico e coincide tra `select_features` e `get_feature_names`.

L'ordine delle chiavi `interf:` riflette l'ordine di dichiarazione dei compliance set in `topology.yaml` (Python 3.7+ mantiene l'ordine di inserimento). Non assumere un ordine assoluto — usare `get_feature_names()` per ottenere l'ordine prima di indicizzare per posizione.

> **Ordine chiavi `node:` in `select_features`:** le chiavi
> `node:<v>:<metric>` seguono `sorted(cs_nodes)` — ordine
> lessicografico alfabetico sui node_id. Questo differisce
> dall'ordine di dichiarazione in `topology["nodes"]`.
> La differenza è invisibile ai consumer che accedono per
> chiave (dict lookup) ma può creare confusione nel dump
> degli alert o nei log dove l'ordine delle chiavi riflette
> `sorted()` anziché l'ordine topologico. `get_feature_names`
> garantisce lo stesso ordine di `select_features` — usare
> quest'ultimo come riferimento.

> **Separazione `node:` / `edge:` in `get_feature_names["direct"]`:** il campo `"direct"` restituisce una lista piatta che mescola chiavi `node:` e `edge:` (nell'ordine: prima tutti i nodi in sorted order, poi tutti gli archi in ordine topologico). I moduli downstream che necessitano solo delle feature di nodo (es. `StructuralMonitor` per il vettore di Isolation Forest) filtrano per prefisso `key.startswith("node:")`. Questa responsabilità di filtraggio è esplicitamente lasciata ai chiamanti.

---

## 5. Valori verificati sul dataset DSB

| Compliance set | node: | edge: | interf: | Totale feature |
|---|---|---|---|---|
| H_crit | 5 nodi × 4 metriche = **20** | 4 archi × 3 metriche = **12** | **0** | **32** |
| H_cache | 4 nodi × 4 metriche = **16** | 3 archi × 3 metriche = **9** | **1** | **26** |

**H_crit — archi interni A(H_crit):** `{e1, e2, e4, e6}` — 4 archi (nginx-web-server→nginx-thrift, nginx-thrift→home-timeline-service, home-timeline-service→post-storage-service, post-storage-service→post-storage-mongodb).

**H_cache — archi interni A(H_cache):** `{e3, e4, e5}` — 3 archi (home-timeline-service→home-timeline-redis, home-timeline-service→post-storage-service, post-storage-service→post-storage-memcached).

**H_cache — feature di interferenza:** `"interf:e2:throughput_rps"` — arco nginx-thrift→home-timeline-service. `nginx-thrift` è esterno a H_cache e punta a `home-timeline-service`, nodo condiviso con H_crit.

**Nota strutturale su M_interf(H_crit) = ∅**: questa è una proprietà della topologia DSB, non un caso generale. Tutti gli archi che puntano verso i nodi condivisi `{home-timeline-service, post-storage-service}` hanno come sorgente nodi già interni a H_crit (`nginx-thrift` via e2, `home-timeline-service` via e4): nessun arco esterno raggiunge un nodo condiviso.

---

## 6. Dipendenze

**Esterne:**
- `pandas` — costruzione dei DataFrame di serie temporali.

**Interne:**
- `ConfigLoader` — lettura di `topology.yaml` per `node_metrics`, `edge_metrics` e lista degli archi (usata per precalcolare `_edge_id_lookup`).
- `TopologyBuilder` — tutte le query topologiche sono delegate: `get_compliance_set_nodes`, `get_edges_for_compliance_set`, `get_interference_edges`. Il `FeatureSelector` non manipola il grafo direttamente.
- `LoggingSetup` — logger nominato `src.layer3.feature_selector`.

`TopologyBuilder` è il consumatore primario dell'API di query topologica; `FeatureSelector` ne dipende completamente per calcolare sia M_direct sia M_interf.

---

## 7. Test (28 test in tests/test_feature_selector.py)

Mock costruiti direttamente in memoria come lista di snapshot (struttura ATGBuilder). Tre timestamp: `t0`, `t1`, `t2`. Tutti i nodi e archi presenti in ogni snapshot con valori costanti e noti.

### Struttura generale (1)

| Test | Comportamento verificato |
|---|---|
| `test_select_returns_dict` | `select_features` restituisce un `dict`. |

### M_direct — H_crit (2)

| Test | Comportamento verificato |
|---|---|
| `test_h_crit_direct_node_count` | 5 nodi × 4 metriche = 20 chiavi `node:` per H_crit. |
| `test_h_crit_direct_edge_count` | A(H_crit) = {e1,e2,e4,e6} × 3 metriche = 12 chiavi `edge:` per H_crit. |

### M_interf — H_crit (1)

| Test | Comportamento verificato |
|---|---|
| `test_h_crit_no_interference` | `M_interf(H_crit, H_cache) = ∅` — 0 chiavi `interf:` per H_crit. |

### M_direct — H_cache (2)

| Test | Comportamento verificato |
|---|---|
| `test_h_cache_direct_node_count` | 4 nodi × 4 metriche = 16 chiavi `node:` per H_cache. |
| `test_h_cache_direct_edge_count` | A(H_cache) = {e3,e4,e5} × 3 metriche = 9 chiavi `edge:` per H_cache. |

### M_interf — H_cache (2)

| Test | Comportamento verificato |
|---|---|
| `test_h_cache_has_interference` | `M_interf(H_cache, H_crit)` produce esattamente 1 chiave `interf:`. |
| `test_h_cache_interference_key_format` | La chiave di interferenza è esattamente `"interf:e2:throughput_rps"`. |

### Formato DataFrame (3)

| Test | Comportamento verificato |
|---|---|
| `test_dataframe_index_is_timestamp` | Ogni DataFrame ha `index.name == "timestamp"`. |
| `test_dataframe_column_is_value` | Ogni DataFrame ha un'unica colonna `"value"`. |
| `test_dataframe_length_matches_snapshots` | Ogni DataFrame ha tante righe quanti gli snapshot (3). |

### Valori numerici (3)

| Test | Comportamento verificato |
|---|---|
| `test_node_value_correct` | `cpu_percent` di `nginx-web-server` a `t0` corrisponde al valore mock (5.0, tolleranza 1e-9). |
| `test_edge_value_correct` | `latency_ms` di e1 a `t0` corrisponde al valore mock (10.0 ms, tolleranza 1e-9). |
| `test_interf_value_is_throughput_only` | La feature `interf:e2` contiene solo `throughput_rps`; assenza di `interf:e2:latency_ms` e `interf:e2:error_rate`. |

### Error handling (1)

| Test | Comportamento verificato |
|---|---|
| `test_unknown_compliance_set_raises` | `select_features("H_nonexistent", ...)` solleva `KeyError`. |

### get_feature_names (3)

| Test | Comportamento verificato |
|---|---|
| `test_get_feature_names_direct_count_h_crit` | `get_feature_names("H_crit")["direct"]` ha 32 elementi (20 nodo + 12 arco). |
| `test_get_feature_names_interference_count_h_crit` | `get_feature_names("H_crit")["interference"]` ha 0 elementi. |
| `test_get_feature_names_interference_count_h_cache` | `get_feature_names("H_cache")["interference"]` ha 1 elemento (e2). |

### Ordine deterministico (2)

| Test | Comportamento verificato |
|---|---|
| `test_select_features_key_order_deterministic` | Le chiavi non-`interf:` di `select_features` coincidono in ordine con `get_feature_names(...)["direct"]`. |
| `test_interf_key_order_matches_get_feature_names` | Le chiavi `interf:` di `select_features` coincidono in ordine con `get_feature_names(...)["interference"]`. |

### dtype e valori NaN (3)

| Test | Comportamento verificato |
|---|---|
| `test_missing_node_series_has_float_nan_dtype` | Snapshot privo di `nginx-web-server`: la serie ha `dtype == float64` e il valore assente è `float('nan')`, non `dtype=object` con `pd.NA`. |
| `test_node_partial_presence_produces_float_nan` | Nodo presente in alcuni snapshot e assente in altri: `dtype=float64`, primo valore `NaN`, secondo non-`NaN`. |
| `test_edge_metric_key_absent_produces_float_nan` | Snapshot con arco ma senza la chiave della metrica: `_build_edge_series` produce `float('nan')` con `dtype=float64`. |

### Error handling — get_feature_names (1)

| Test | Comportamento verificato |
|---|---|
| `test_get_feature_names_unknown_raises` | `get_feature_names("H_nonexistent")` solleva `KeyError`. |

### Valore numerico interferenza (1)

| Test | Comportamento verificato |
|---|---|
| `test_interf_value_numeric` | `"interf:e2:throughput_rps"` a `t0` per H_cache corrisponde a `_TP["e2"] = 5.0` (tolleranza 1e-9). |

### Snapshot vuoti e metrica mancante (2)

| Test | Comportamento verificato |
|---|---|
| `test_select_features_empty_snapshots` | `select_features` con lista snapshot vuota restituisce un dict con le chiavi corrette e DataFrame a 0 righe con colonna `"value"`. |
| `test_missing_interf_metric_produces_warning_not_error` | Se `throughput_rps` è assente da `edge_metrics`, `FeatureSelector.__init__` emette `logger.warning` (non `ValueError`) e `M_interf` è vuoto per tutti i compliance set. |

### dtype float — cast esplicito (1)

| Test | Comportamento verificato |
|---|---|
| `test_node_nan_value_preserved_as_float_nan` | Un valore numerico intero nel nodo (es. `5`) produce `dtype == float64` nella serie (guard contro assenza del cast `float(raw)` in `_build_node_series`). |
