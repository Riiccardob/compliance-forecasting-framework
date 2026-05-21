# Module 04 — PBOBuilder

## 1. Obiettivo del modulo

`PBOBuilder` implementa il livello PBO `G_Behavior(t) = (V, E_all, W_t)`, distinto dall'ATG. Trasforma gli snapshot ATG in una rappresentazione comportamentale stocastica per il monitoraggio strutturale: invece di misurare latenze e utilizzo CPU, cattura come si distribuisce il traffico tra i percorsi disponibili e quanto tale distribuzione si discosta dal comportamento nominale atteso.

---

## 2. Interfaccia pubblica

```python
class PBOBuilder:
    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None

    def compute_transition_weights(
        self, snapshots: list[dict]
    ) -> list[dict]

    def compute_gold_standard(
        self, weight_series: list[dict], snapshots: list[dict]
    ) -> dict[str, float]

    def compute_path_adherence(
        self, weight_series: list[dict], compliance_set_name: str
    ) -> list[dict]

    def compute_frobenius_distance(
        self, weight_series: list[dict], gold_standard: dict[str, float]
    ) -> list[dict]
```

> **Chiavi obbligatorie in `pipeline_params["pbo"]`:** le chiavi `weight_metric` e `gold_standard_label` vengono accedute direttamente con `pbo_cfg["weight_metric"]`. Se la sotto-sezione `pbo` esiste in `pipeline_params.yaml` ma manca di una di queste chiavi, viene sollevato `KeyError` non descrittivo. La validazione di livello radice di `ConfigLoader` garantisce che la chiave `pbo` esista, ma non le sue sotto-chiavi.

**`compute_transition_weights(snapshots) → list[dict]`**
Calcola i pesi di transizione stocastici per ogni snapshot. Restituisce `[{"timestamp": int, "weights": {"e1": float, ...}}, ...]`. I nodi terminali (sink) non compaiono nel dizionario. **Fallback uniforme**: se il throughput totale uscente da un nodo è zero, oppure se almeno un valore è negativo, NaN o non finito, i pesi degli archi uscenti sono impostati a `1/n` con `logger.warning`. `weight_metric` viene validato in `__init__` contro `edge_metrics` di `topology.yaml` — solleva `ValueError` se non presente.

La metrica usata per il calcolo dei pesi è letta da `pipeline_params["pbo"]["weight_metric"]` (default: `"throughput_rps"`). Analogamente, la label che identifica le finestre nominali per W_gold è letta da `pipeline_params["pbo"]["gold_standard_label"]` (default: `0`). Nessuna di queste due impostazioni è hardcoded nel codice.

**`compute_gold_standard(weight_series, snapshots) → dict[str, float]`**
Calcola W_gold come media dei pesi sulle finestre nominali (`label == gold_standard_label`, da `pipeline_params["pbo"]["gold_standard_label"]`). Solleva `ValueError` se nessuno snapshot è nominale.

**`compute_path_adherence(weight_series, compliance_set_name) → list[dict]`**
Calcola PAS per il critical path del compliance set specificato. Restituisce `[{"timestamp": int, "pas": float}, ...]`. Solleva `ValueError` se `topology_type != "linear"` — il PAS non è definito per topologie parallele. **Pattern PAS_gold (Fase III):** per ottenere il valore scalare `PAS_gold` da usare come riferimento nel CUSUM, chiamare il metodo con `weight_series=[{"timestamp": 0, "weights": W_gold}]` dove `W_gold` è il risultato di `compute_gold_standard()`. Il valore restituito è `pas_gold = result[0]["pas"]`. Non aggiungere un metodo `compute_pas_gold()` a PBOBuilder — questo pattern è il meccanismo definito in D2.

**`compute_frobenius_distance(weight_series, gold_standard) → list[dict]`**
Calcola `||W(t) − W_gold||_F` per ogni timestamp. Restituisce `[{"timestamp": int, "frobenius": float}, ...]`. La somma itera su E_all (tutti gli archi della topologia via `self._edges`), usando `weights.get(eid, 0.0)` e `gold_standard.get(eid, 0.0)`. Un arco con peso esplicitamente `0.0` e uno assente dal dict producono lo stesso contributo alla Frobenius.

---

## 3. Matematica implementata

**Matrice dei pesi W_t** — per ogni nodo `u` con archi uscenti:

```
w(u→v, t) = weight_metric(u→v, t) / Σ_k weight_metric(u→k, t)
```

dove `weight_metric` è la metrica di arco configurata in `pipeline_params.yaml` (default: `throughput_rps`).

La somma per riga è 1.0 (proprietà stocastica). Nodi senza archi uscenti (terminali) non compaiono in W_t.

**Gold standard W_gold** — media sui timestamp nominali:

```
w_gold(e) = (1/|T_nominal|) × Σ_{t ∈ T_nominal} w(e, t)
```

dove `T_nominal = {t : label(t) == gold_standard_label}`.

**Path Adherence Score (PAS)** — prodotto dei pesi lungo il critical path `P_cert = (v_1, v_2, ..., v_n)`:

```
PA(P_cert, t) = ∏_{k=1}^{n-1} w(v_k → v_{k+1}, t)
```

Interpretato, sotto ipotesi di Markov, come la probabilità empirica che una richiesta percorra l'intero percorso certificato nella finestra temporale `t`.

**Norma di Frobenius** — distanza scalare tra W(t) e W_gold su tutti gli archi:

```
||W(t) - W_gold||_F = sqrt( Σ_e (w_e(t) - w_gold_e)² )
```

La somma itera su E_all (tutti gli archi della topologia via `self._edges`), usando `weights.get(eid, 0.0)` e `gold_standard.get(eid, 0.0)`. Iterare su E_all invece che sulle chiavi di `gold_standard` garantisce che eventuali archi non calibrati nel gold standard contribuiscano con `(0−0)² = 0`.

---

## 4. Proprietà strutturali sul dataset DSB

**PAS(H_crit) costante a 0.25 nel dataset GAMMA.**
Il critical path di H_crit attraversa gli archi e1, e2, e4, e6. Nel dataset GAMMA:
- `nginx-web-server` e `nginx-thrift` hanno un solo arco uscente ciascuno → w(e1) = w(e2) = 1.0
- `home-timeline-service` ha due archi uscenti con throughput simmetrico (e3 = e4) → w(e4) = 0.5
- `post-storage-service` ha due archi uscenti anch'essi con throughput simmetrico nel dataset GAMMA → w(e6) = 0.5

PAS = 1.0 × 1.0 × 0.5 × 0.5 = **0.25** costante. Questa costanza non è un bug: è la simmetria strutturale del throughput nel dataset GAMMA (Prometheus aggrega il traffico per container, non per singola dipendenza RPC).

**Nota sui mock dei test**: `test_pas_h_crit_exact_value_nominal` usa `_TP_NOMINAL = {e5: 8.0, e6: 12.0}`, quindi `w(e6) = 12/(8+12) = 0.6` e PA = 0.30, non 0.25. La differenza non è un'incongruenza: il mock usa throughput asimmetrico per testare il calcolo esatto. Il dataset GAMMA reale usa throughput simmetrici (post-storage-memcached ≈ post-storage-mongodb) che producono PA = 0.25.

**H_cache: topology_type = "parallel", PAS non applicabile.**
H_cache ha topologia ramificata (home-timeline-service fa fan-out verso home-timeline-redis e post-storage-service): non esiste un singolo percorso sequenziale certificato. Per H_cache, la norma di Frobenius è il monitor strutturale sostitutivo. Chiamare `compute_path_adherence("H_cache")` solleva `ValueError`.

**W_gold deve essere calibrato su finestre nominali.**
Includere finestre anomale nella calibrazione di W_gold inquinerebbe il gold standard, aumentando la tolleranza alla deriva e producendo falsi negativi durante il monitoraggio operativo. La funzione `compute_gold_standard` filtra rigorosamente su `label == gold_standard_label`.

---

**Frobenius strutturalmente zero su DSB (H_cache)**

La stessa causa strutturale si applica simmetricamente a H_cache e
alla norma di Frobenius.

Su DSB, `throughput_rps` è un aggregato a livello di finestra:
il suo valore è identico per tutti gli archi nello stesso snapshot.
Per ogni nodo con più archi uscenti (come `home-timeline-service` con
e3 e e4, e `post-storage-service` con e5 e e6), il denominatore è:
Σ_k throughput(u→k) = X + X = 2X

quindi `w(e) = X / 2X = 0.5` indipendentemente dal valore di `X > 0`.
Per i nodi con un solo arco uscente il peso è sempre `1.0`.

Di conseguenza `W(t) = W_gold` per ogni finestra temporale `t`,
incluse le finestre anomale, e:
||W(t) − W_gold||_F = 0   ∀t

**Conseguenza combinata sulla Fase III sul dataset DSB:**

| Compliance set | Metrica CUSUM | Valore runtime | Effetto operativo |
|---|---|---|---|
| H_crit (lineare) | PAS | 0.25 = PAS_gold costante | CUSUM mai attivo |
| H_cache (parallelo) | Frobenius | 0.0 sempre | CUSUM mai attivo |

Poiché il Validatore Strutturale (Livello 4) richiede
`cusum_signal AND if_signal`, e `cusum_signal` è sempre `False` per
entrambi i compliance set sul dataset DSB, il Livello 4 non produce
mai `structural_confirmed = True` su dati reali GAMMA.

**Questa è una limitazione del dataset, non del framework.**
Il Livello 4 è progettato per dataset con traffico non aggregato a
livello di finestra (es. metriche Prometheus per singola dipendenza
RPC), dove `W(t)` varia effettivamente tra finestre nominali e anomale.
La Fase III rimane operativamente utile tramite i Livelli 1
(threshold/z-score) e 2 (Isolation Forest), che funzionano
correttamente sul dataset DSB.

---

## 5. Dipendenze

**Esterne:**
- `math` (stdlib) — `math.sqrt` per la norma di Frobenius. Nessuna dipendenza da librerie di terze parti.

**Interne:**
- `ConfigLoader` — lettura di `topology.yaml` (lista archi, compliance set, topology_type).
- `TopologyBuilder` — `get_critical_path(name)` per il PAS.
- `LoggingSetup` — logger nominato `src.layer2.pbo_builder`.

---

## 6. Test (27 test in tests/test_pbo_builder.py)

Mock costruiti direttamente in memoria come lista di dizionari snapshot (struttura ATGBuilder). Tre timestamp: `t0` (nominale), `t1` (nominale), `t2` (anomalo `cpu`). Throughput differenziato per verificare asimmetria a `t2`.

### Pesi W_t (4)

| Test | Comportamento verificato |
|---|---|
| `test_weight_series_length` | `compute_transition_weights` restituisce una lista di 3 elementi. |
| `test_weights_stochastic_per_source` | Per ogni timestamp e ogni nodo con archi uscenti, la somma dei pesi è 1.0 (tolleranza 1e-6). |
| `test_weight_e4_symmetric_at_t0` | A `t0`: `w(e4) = 10/(10+10) = 0.5` (e3 = e4 = 10.0 rps). |
| `test_weight_e4_asymmetric_at_t2` | A `t2`: `w(e4) = 18/(18+2) = 0.9` (e4 = 18.0, e3 = 2.0 rps). |

### Fallback e validazione (6)

| Test | Comportamento verificato |
|---|---|
| `test_weight_fallback_uniform_on_zero_throughput` | Se il throughput totale uscente da un nodo è zero (e3=e4=0), i pesi sono uniformi 0.5 e la loro somma è 1.0. |
| `test_weight_nan_throughput_uses_uniform_fallback` | `throughput_rps=NaN` attiva il fallback uniforme (1/n) senza propagare NaN nella matrice stocastica W_t. |
| `test_weight_negative_throughput_uses_uniform_fallback` | Throughput negativo su un arco attiva il fallback uniforme; il peso negativo viola la proprietà stocastica. |
| `test_zero_total_throughput_emits_warning` | Se il throughput totale uscente da un nodo è zero, viene emesso un `logger.warning` prima di applicare il fallback uniforme (1/n). |
| `test_weight_invalid_metric_raises_at_init` | `weight_metric` non in `edge_metrics` solleva `ValueError` in `__init__`. |
| `test_gold_standard_covers_absent_edge` | W_gold include e6 anche se e6 è assente (popped) dal primo snapshot nominale — trattato come peso 0.0 e mediato correttamente. |

### Archi mancanti e disallineamento (2)

| Test | Comportamento verificato |
|---|---|
| `test_path_adherence_missing_arc_raises` | `compute_path_adherence` con critical_path contenente arco inesistente solleva `ValueError` con "non esiste in topology". |
| `test_gold_standard_warns_on_misaligned_series` | `compute_gold_standard` emette `logger.warning` quando alcuni timestamp nominali degli snapshot non hanno corrispondenza in `weight_series`; il gold è calcolato sui soli timestamp disponibili. |

### Gold standard (3)

| Test | Comportamento verificato |
|---|---|
| `test_gold_standard_uses_only_nominal` | `W_gold["e4"] = (0.5 + 0.5) / 2 = 0.5` — media su `t0` e `t1`, entrambi nominali; `t2` escluso. |
| `test_gold_standard_no_nominal_raises` | `ValueError` se tutti gli snapshot hanno `label == 1`. |
| `test_gold_standard_covers_all_topology_edges` | W_gold include tutti gli archi di E_all anche se il primo snapshot nominale ha e6 con throughput zero (e6 assente nei pesi del primo snapshot). |

### Path Adherence Score (5)

| Test | Comportamento verificato |
|---|---|
| `test_pas_h_crit_in_range` | `PA(H_crit, t) ∈ [0.0, 1.0]` per tutti i timestamp. |
| `test_pas_h_crit_length` | La lista PAS ha 3 elementi. |
| `test_pas_parallel_raises` | `compute_path_adherence("H_cache")` solleva `ValueError` (topology_type = parallel). |
| `test_pas_h_crit_exact_value_nominal` | `PA(H_crit, t0) = 1.0×1.0×0.5×0.6 = 0.30` con `_TP_NOMINAL` (tolleranza 1e-9). |
| `test_pas_invalid_compliance_set_raises` | `compute_path_adherence(weight_series, "H_nonexistent")` solleva `KeyError` con messaggio "Compliance set non trovato". |

### Norma di Frobenius (6)

| Test | Comportamento verificato |
|---|---|
| `test_frobenius_non_negative` | `frobenius ≥ 0.0` per tutti i timestamp. |
| `test_frobenius_zero_at_nominal` | A `t0` e `t1` (pesi identici a W_gold): `frobenius < 1e-9`. |
| `test_frobenius_positive_at_anomaly` | A `t2`: `frobenius > 0.0` — e4 cambia da 0.5 (gold) a 0.9. |
| `test_frobenius_length` | La lista Frobenius ha 3 elementi. |
| `test_frobenius_exact_value_at_anomaly` | `frobenius(t2) = sqrt(0.32)` — Δe3=−0.4, Δe4=+0.4, tutti gli altri archi invariati (tolleranza 1e-9). |
| `test_frobenius_explicit_zero_weight_contributes` | Un arco con peso `0.0` esplicito nel dict e uno assente producono identico contributo alla Frobenius (entrambi trattati come `weight=0.0`). |

### Gold standard — chiavi esatte (1)

| Test | Comportamento verificato |
|---|---|
| `test_gold_standard_key_arcs` | `W_gold["e1"] = 1.0` (sorgente con singolo arco uscente); `W_gold["e6"] = 0.6` (12/(8+12)). |
