# Module 09 — AlertGenerator

## 1. Obiettivo del modulo

`AlertGenerator` implementa la Fase IV del framework (methodology.tex §3.2.4). Aggrega le previsioni di Fase I (`StatForecaster.predict()`), il grafo causale di Fase II (`CausalAnalyzer.analyze()`) e i segnali strutturali di Fase III (`StructuralMonitor.monitor()`) per produrre un alert strutturato con lead time stimato, classificazione di criticità (yellow/orange/red) e causa radice identificata.

`generate()` restituisce `None` se nessun passo nell'orizzonte viola la soglia SLA — questo non è un errore, indica che la proprietà è conforme nell'orizzonte corrente.

---

## 2. Struttura Alert

`generate()` restituisce `dict[str, Any] | None`.

| Campo | Tipo | Semantica |
|---|---|---|
| `timestamp` | `int` | Timestamp della finestra corrente in µs. |
| `compliance_set` | `str` | Nome del compliance set (es. `"H_crit"`). |
| `property_at_risk` | `str` | Proprietà a rischio: `"latency"` \| `"reliability"` \| `"capacity"`. |
| `criticality` | `str` | Livello di criticità: `"yellow"` \| `"orange"` \| `"red"`. |
| `lead_time_steps` | `int` | τ* ≥ 1: primo step con violazione SLA prevista. |
| `lead_time_hours` | `float` | `lead_time_steps × step_duration_hours`. |
| `aggregated_forecast` | `list[float]` | Previsione aggregata Φ̂_i(t+τ') per τ'=1..horizon. |
| `sla_threshold` | `float` | Soglia SLA della proprietà. |
| `sla_bound` | `str` | `"upper"` o `"lower"`. |
| `critical_arc` | `str \| None` | Edge_id dell'arco con maggior contributo alla violazione (es. `"e4"`). `None` se non determinabile. |
| `root_cause` | `str \| None` | Feature key sorgente dell'edge causale con intensità massima da Fase II. `None` se grafo causale vuoto. |
| `cross_property_interference` | `str \| None` | `source_cs` della prima catena cross-property `confirmed=True`. `None` se nessuna catena confermata. |
| `causal_chain` | `list[str]` | Lista dei nodi della catena causale confermata. `[]` se assente. |
| `structural_signals` | `dict` | Riassunto segnali Fase III (vedi sotto). |
| `model_uncertainty_flag` | `bool` | `True` se almeno una feature ha divergenza normalizzata > `divergence_threshold`. |

`structural_signals` contiene: `base_signal`, `if_signal`, `cusum_signal`, `structural_confirmed` (bool), `frobenius_distance` (float\|None), `pas_value` (float\|None).

**Esempio concreto per H_crit DSB:**
```python
{
    "timestamp": 1_000_000_000,
    "compliance_set": "H_crit",
    "property_at_risk": "latency",
    "criticality": "orange",
    "lead_time_steps": 3,
    "lead_time_hours": 72.0,
    "aggregated_forecast": [40.0, 60.0, 120.0, 145.0, 160.0, 170.0],
    "sla_threshold": 100.0,
    "sla_bound": "upper",
    "critical_arc": "e4",
    "root_cause": "node:post-storage-service:cpu_percent",
    "cross_property_interference": None,
    "causal_chain": [],
    "structural_signals": {"base_signal": False, "if_signal": False,
                           "cusum_signal": True, "structural_confirmed": False,
                           "frobenius_distance": 0.23, "pas_value": 0.18},
    "model_uncertainty_flag": False,
}
```

---

## 3. Logica di aggregazione per proprietà

La proprietà viene rilevata dalla sezione `sla` del compliance set in `topology.yaml` con priorità decrescente: **latency > reliability > capacity**.

| Proprietà | Metrica | Funzione di aggregazione | Formula |
|---|---|---|---|
| `latency` | `latency_ms` | `sum` (linear) / `max` (parallel) | Σ yhat degli archi (linear); max yhat (parallel) |
| `reliability` | `error_rate` | `product_complement` | Π (1 − ε_e) per arco |
| `capacity` | `throughput_rps` | `min` | min yhat tra archi |

La scelta sum/max per la latency dipende da `topology_type` del compliance set:
- `"linear"` → `"sum"` (latenze in serie si sommano sul critical path)
- `"parallel"` → `"max"` (il percorso peggiore determina la latenza percepita)

Se `yhat` è `NaN` per una feature, viene usata la soglia SLA originale (`display_threshold`) come valore conservativo per la metrica del singolo arco (documentata con `logger.warning`). Se nessuna feature rilevante è presente in `forecasts`, l'aggregazione restituisce `[]` e `generate()` ritorna `None`.

**NOTA sulla proprietà reliability:** il valore aggregato Π(1−ε_e) è una reliability ∈ [0,1]. Per il violation check, la SLA error_rate (upper, 0.05) viene convertita in reliability (lower, 0.95) secondo Eq. 3.32. L'alert riporta `sla_threshold=0.05` e `sla_bound="upper"` (valori originali del certificato) per leggibilità dell'operatore. Il NaN fallback è conservativo per entrambe le direzioni della SLA: per upper-bound (latency, reliability), il fallback usa `display_threshold` (valore al boundary); per lower-bound (capacity), il fallback usa `0.0` (valore minimo assoluto, garantendo la rilevazione della violazione). Questo assicura che l'incertezza del forecast si traduca sempre in un alert piuttosto che in una non-rilevazione.

---

## 4. Stima lead time e classificazione criticità

**Lead time:** τ* = min{ τ' : is_violated(Φ̂(t+τ'), SLA) }

```
if sla_bound == "upper": violazione se aggregated_forecast[τ'-1] > sla_threshold
if sla_bound == "lower": violazione se aggregated_forecast[τ'-1] < sla_threshold
```

I valori NaN nell'aggregazione sono ignorati (non generano violazione).

**Classificazione criticità** — regole valutate in ordine (RED prima):

```
lead_time_days = lead_time_steps × step_duration_hours / 24

RED se:
  lead_time_days < orange_min_days
  OPPURE (cusum_signal AND structural_confirmed)
  OPPURE (if_signal AND structural_confirmed)

ORANGE se non RED e:
  orange_min_days ≤ lead_time_days < yellow_min_days
  OPPURE cusum_signal
  OPPURE if_signal

YELLOW altrimenti (lead_time_days ≥ yellow_min_days AND NOT cusum_signal AND NOT if_signal)
```

I criteri RED e ORANGE sono indipendenti dal lead time: `cusum_signal=True` eleva a ORANGE anche con lead time molto lungo; `structural_confirmed=True` con almeno un segnale IF/CUSUM eleva a RED.

**Nota metodologica — estensione di methodology.tex §3.2.4:** la specifica teorica definisce RED esclusivamente come `lead_time < orange_min_days`. L'implementazione aggiunge due condizioni che elevano a RED indipendentemente dal lead time: `(cusum_signal AND structural_confirmed)` e `(if_signal AND structural_confirmed)`. Questa è un'estensione deliberata della specifica — il rationale è che la convergenza di segnale IF, segnale CUSUM persistente e conferma strutturale della deriva della matrice PBO costituisce evidenza sufficiente per elevare il livello di allerta, indipendentemente da quanto distante sia la violazione SLA prevista. Su dataset DSB, `structural_confirmed` è sempre False (vedi Module 04 §4 e Module 08 §3), quindi queste condizioni aggiuntive non si attivano mai operativamente sul dataset corrente.

**Note di configurazione DSB:**
Con `horizon_steps=12` e `step_duration_hours=24.0`, il lead time massimo è 12 giorni > `yellow_min_days=7`. YELLOW è quindi raggiungibile in produzione (violazione a step 8+ con tutti i segnali Fase III inattivi). Il test `test_criticality_yellow_on_long_lead_time` costruisce un forecast a 10 step con violazione allo step 10 (`lead_time_days=10 > 7`), il che è consistente con la configurazione di produzione.

**Declassamento per incertezza:** se `model_uncertainty_flag=True` e criticality ≠ "yellow": red→orange, orange→yellow. Non si applica a YELLOW (già il livello minimo).

---

## 5. Estrazione root cause e interferenza cross-property

`_extract_root_cause` analizza il `CausalGraph` di Fase II:

1. **Selezione edge rilevanti:** filtra gli edge il cui `target` termina con `:<metric_suffix>` (es. `:latency_ms`). Se nessuno corrisponde, usa tutti gli edge del grafo.
2. **critical_arc:** edge_id dell'arco con intensità massima — estratto dal campo `target` con `.split(":")[1]`. Se il grafo è vuoto, usa il fallback `_find_critical_arc_from_forecast` (arco con massimo/minimo yhat al passo `lead_time_steps`).
3. **root_cause:** campo `source` dell'edge con intensità massima (feature key completa, es. `"node:post-storage-service:cpu_percent"`).
4. **cross_property_interference:** `source_cs` della prima catena in `cross_property_chains` con `confirmed=True`. `None` se nessuna catena confermata.
5. **causal_chain:** `chain` della prima catena confermata come `list[str]`. `[]` se assente.

> **Nota su `critical_arc` con grafo causale node→node:** se
   > `_extract_root_cause` non trova edge con target che inizia con
   > `edge:` (es. grafo con sole coppie node→node), attiva il fallback
   > `_find_critical_arc_from_forecast`. Se il fallback non è raggiunto
   > e l'edge con intensità massima ha target `node:v:metric`, il campo
   > `.split(':')[1]` restituisce un node_id invece di un edge_id —
   > valore semanticamente errato ma non causa di crash. L'alert riporta
   > il valore così calcolato senza validazione aggiuntiva.

---

## 6. Incertezza modellistica

`_check_model_uncertainty` calcola per ogni feature in `forecasts`:

1. Baseline lineare `np.polyfit(x, yhat, 1)` sulla serie `yhat`.
2. MAD = mean(|yhat − baseline|).
3. Normalizzazione: `MAD / (max − min)` se range > 0; `MAD / |mean|` se range = 0 e mean ≠ 0; 0.0 altrimenti.
4. Se `normalized_div > divergence_threshold` per almeno una feature: `True`.

Con il placeholder Ridge per LSTM, `yhat` è quasi lineare → il flag è quasi sempre `False` in produzione. Sarà più discriminativo con un LSTM reale con previsione non-lineare (TODO-02).

---

## 7. Parametri da pipeline_params.yaml

| Parametro | Tipo | Obbligatorio | Descrizione |
|---|---|---|---|
| `alert_generation.yellow_min_days` | int | Sì | Lead time ≥ yellow_min_days → Yellow. `ValueError` se mancante. |
| `alert_generation.orange_min_days` | int | Sì | Lead time < orange_min_days → Red. `ValueError` se mancante. |
| `forecasting.horizon_steps` | int | No (letto) | Numero di step previsionali. |
| `forecasting.step_duration_hours` | float | No | Durata di ogni step in ore (default `24.0`, `logger.warning` se assente). |
| `forecasting.divergence_threshold` | float | No | Soglia MAD normalizzata per il flag di incertezza (default `0.2`). |

`step_duration_hours` è ora presente nel YAML con valore `24.0` — ogni step corrisponde a 24 ore ai fini della classificazione (finestre DSB reali: 5 s, ma l'orizzonte di forecast è calibrato su scala giornaliera per la tesi).

> **Vincolo di configurazione:** `orange_min_days` deve essere
   > strettamente inferiore a `yellow_min_days`. Se invertiti, la
   > classificazione produce risultati errati senza sollevare eccezioni.
   > Il costruttore non valida questa relazione — la correttezza è
   > responsabilità del file `pipeline_params.yaml`.

---

## 8. Dipendenze

**Esterne:**
- `numpy` — `polyfit` per baseline lineare in `_check_model_uncertainty`.
- `pandas` — operazioni su DataFrame dei forecasts.

**Interne:**
- `ConfigLoader` — lettura di `alert_generation.*` e `forecasting.*` da `pipeline_params.yaml`; lettura di `compliance_sets.*sla*` e `topology_type` da `topology.yaml`.
- `TopologyBuilder` — `get_edges_for_compliance_set` (selezione archi di A(H_Φi)).
- `LoggingSetup` — logger nominato `src.phase4.alert_generator`.

---

## 9. Test (34 test in tests/test_alert_generator.py)

Mock costruiti in memoria. Nessun CSV reale. Forecast costruiti con `_make_forecast_df(yhats)` (DataFrame con indice timestamp `i×5_000_000`, colonne `yhat`, `yhat_lower`, `yhat_upper`). SLA H_crit: `latency_ms upper 100.0`. Con 4 archi e aggregazione `sum`, soglia attivazione = `yhat_per_arc=25.0` (4×25=100, ma serve >100, quindi si usa 30.0→4×30=120>100).

**`_aggregate_forecasts` — accesso per indice:** usa `df.loc[step, "yhat"]` (step 1-based, compatibile con l'indice intero di `StatForecaster.predict()`). Se il DataFrame ha indice timestamp (mock), cade sull'`except KeyError` e usa `df.iloc[step-1]["yhat"]`. Se `n_steps < horizon_steps`, emette `logger.warning`.

### Validazione configurazione (2)

| Test | Comportamento verificato |
|---|---|
| `test_critical_arc_is_edge_id_not_node_id` | Grafo causale con solo edge node→node: critical_arc deve essere un edge_id (via fallback) e non un node_id estratto con split(':')[1]. |
| `test_orange_min_days_less_than_yellow_min_days_or_raises` | orange_min_days=7 > yellow_min_days=2: documenta il comportamento attuale (nessuna validazione) e serve come guard per futura validazione. |

### Struttura output (4)

| Test | Comportamento verificato |
|---|---|
| `test_generate_returns_none_when_no_violation` | `yhat=10.0` per arco (sum=40 < 100 SLA) → `generate()` restituisce `None`. |
| `test_generate_returns_dict_on_violation` | `yhat=30.0` per arco (sum=120 > 100 SLA) → `generate()` restituisce `dict`. |
| `test_alert_has_required_keys` | Il dict ha esattamente le 15 chiavi richieste dalla struttura Alert. |
| `test_compliance_set_in_alert` | `alert["compliance_set"] == "H_crit"`. |

### Lead time (3)

| Test | Comportamento verificato |
|---|---|
| `test_lead_time_steps_is_first_violation` | Step 1-2 sum=80<100, step 3+ sum=120>100 → `lead_time_steps==3`. |
| `test_lead_time_none_means_no_alert` | Nessuna violazione nell'orizzonte → `generate()` restituisce `None`. |
| `test_lead_time_step_1_possible` | Violazione già al primo step (`yhat=30.0`) → `lead_time_steps==1`. |

### Classificazione criticità (4)

| Test | Comportamento verificato |
|---|---|
| `test_criticality_yellow_on_long_lead_time` | Forecast 10 step, violazione a step 10 (lead_time=10 giorni > 7), tutti i segnali False → `"yellow"`. |
| `test_criticality_orange_on_cusum_signal` | `cusum_signal=True`, `structural_confirmed=False` → almeno `"orange"`. |
| `test_criticality_red_on_structural_confirmed` | `cusum_signal=True` AND `structural_confirmed=True` → `"red"`. |
| `test_criticality_red_on_short_lead_time` | `lead_time_steps=1` (1 giorno < `orange_min_days=2`) → `"red"`. |

### Aggregazione (5)

| Test | Comportamento verificato |
|---|---|
| `test_aggregation_latency_is_sum_for_linear` | H_crit (linear): `aggregated_forecast[0] = 4 × 30.0 = 120.0`. |
| `test_aggregation_no_relevant_features_returns_none` | Forecasts senza feature di arco per H_crit → `None`. |
| `test_aggregation_nan_yhat_uses_sla_as_conservative` | `yhat=NaN` su latency (upper-bound) → usa `sla_threshold=100.0` come fallback: 4×100=400>100 → violazione. |
| `test_aggregation_capacity_nan_yhat_is_conservative` | `yhat=NaN` su throughput_rps (lower-bound, SLA=10.0) → fallback=0.0 (minimo assoluto); `aggregated_forecast[0]≈0.0 < 10.0` → violazione rilevata (non mascherata). |
| `test_aggregation_latency_max_for_parallel_topology` | H_cache (parallel, `topology_type="parallel"`): forecasts e3=10, e4=60, e5=20 → `aggregated_forecast[0]=60.0` (max, non sum). |

### Root cause (3)

| Test | Comportamento verificato |
|---|---|
| `test_root_cause_from_highest_intensity_edge` | Grafo con edge di intensità 0.3 e 0.7: `root_cause` corrisponde al source con intensità 0.7. |
| `test_cross_property_interference_from_confirmed_chain` | Catena `confirmed=True` con `source_cs="H_cache"`: `cross_property_interference=="H_cache"`, `len(causal_chain)==3`. |
| `test_no_root_cause_on_empty_causal_graph` | Grafo senza edges → `root_cause=None`, `causal_chain=[]`. |

### Incertezza modellistica (4)

| Test | Comportamento verificato |
|---|---|
| `test_uncertainty_flag_false_on_smooth_forecast` | Trend lineare puro (`yhat=[30,40,50,60,70,80]`) → `model_uncertainty_flag=False`. |
| `test_uncertainty_flag_true_on_oscillating_forecast` | `yhat=[10,300,10,300,10,300]`: MAD/range ≈ 0.46 > 0.20 → `model_uncertainty_flag=True`. |
| `test_uncertainty_demotes_red_to_orange` | RED (structural_confirmed=True) + `model_uncertainty_flag=True` → `criticality=="orange"`. |
| `test_uncertainty_demotes_orange_to_yellow` | Violazione al step 5 (ORANGE per lead time), forecast oscillante → `model_uncertainty_flag=True` → `criticality=="yellow"` (demozione ORANGE→YELLOW). |

### Aggregazione estesa (3)

| Test | Comportamento verificato |
|---|---|
| `test_aggregation_reliability_product_complement` | Reliability = Π(1−ε_e): `error_rate=0.02` per arco → reliability ≈ 0.9224 < 0.95 → violation; `error_rate=0.01` → 0.9606 > 0.95 → `None`. Verifica la conversione SLA `upper 0.05` → check `lower 0.95`. |
| `test_aggregation_capacity_min` | Capacity = min(throughput per arco): `min(50,30,80,20)=20 < SLA 25` → violation; `aggregated_forecast[0]==20.0` e `lead_time_steps==1`. |
| `test_reliability_threshold_derived_from_sla_dynamically` | SLA `error_rate upper 0.10` → `check_threshold=0.90` derivato dinamicamente (Eq. 3.32); `error_rate=0.02` → reliability=0.98^4≈0.9224 > 0.90 → `generate()` restituisce `None` (non violazione). Conferma che la soglia check non è hardcoded a 0.95. |

### Robustezza (3)

| Test | Comportamento verificato |
|---|---|
| `test_generate_unknown_compliance_set_raises` | `generate("H_nonexistent", ...)` solleva `KeyError`. |
| `test_missing_alert_generation_key_raises` | Costruttore solleva `ValueError` con match `"yellow_min_days"` se la chiave manca nel YAML patchato. |
| `test_generate_with_empty_forecasts_returns_none` | `forecasts={}` → `None` (nessuna feature da aggregare). |

### Valori numerici (3)

| Test | Comportamento verificato |
|---|---|
| `test_aggregated_forecast_reliability_value` | 4 archi × `error_rate=0.02` → `aggregated_forecast[0] = 0.98^4 ≈ 0.9224` (valore numerico esatto della product_complement). |
| `test_critical_arc_from_highest_intensity_edge` | CausalGraph con archi a intensità 0.3 (e1) e 0.7 (e4): `critical_arc == "e4"` — solo l'edge_id, non la feature key completa. |
| `test_lead_time_hours_value` | Violazione al step 1, `step_duration_hours=24.0` → `lead_time_hours == 24.0`. |
