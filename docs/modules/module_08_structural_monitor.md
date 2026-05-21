# Module 08 — StructuralMonitor

## 1. Obiettivo del modulo

`StructuralMonitor` implementa la Fase III del framework (methodology.tex §3.2.3), eseguendo il monitoraggio gerarchico a quattro livelli su `M_Φi` per un singolo compliance set. Riceve le feature correnti, i pesi di transizione PBO e il gold standard calibrato durante il training, e produce un `MonitorResult` che classifica lo stato del sistema lungo quattro livelli di evidenza crescente.

Il monitor è **stateful**: mantiene l'accumulatore CUSUM (`_cusum_stat`) e lo stato EWMA (`_ewma_state`) tra chiamate successive a `monitor()`. `reset_cusum()` azzera lo stato — tipicamente usato quando si ricomincia un nuovo esperimento.

---

## 2. Struttura MonitorResult

`monitor()` restituisce un `dict[str, Any]` con i seguenti campi:

| Campo | Tipo | Semantica |
|---|---|---|
| `timestamp` | `int` | Timestamp della finestra corrente in µs. |
| `compliance_set` | `str` | Nome del compliance set monitorato (es. `"H_crit"`). |
| `base_signal` | `bool` | `True` se almeno una feature viola threshold SLA o z-score. Condizione necessaria per attivare Livello 2. |
| `if_signal` | `bool` | `True` se Isolation Forest classifica il vettore aggregato come anomalia. `False` per definizione se `base_signal=False`. |
| `cusum_signal` | `bool` | `True` se l'accumulatore CUSUM supera `alert_threshold`. Calcolato in parallelo, indipendente da `base_signal`. |
| `structural_confirmed` | `bool` | `True` se il Validatore strutturale conferma il degrado. `False` per definizione se `if_signal=False` o `cusum_signal=False`. |
| `zscore_violations` | `list[str]` | Feature key con `|z| > zscore_threshold`. Lista vuota se nessuna violazione. |
| `threshold_violations` | `list[str]` | Feature key con valore oltre soglia SLA. Lista vuota se nessuna violazione o se `sla` è assente/vuoto nel YAML. |
| `frobenius_distance` | `float \| None` | Distanza di Frobenius `‖W(t) − W_gold‖_F` corrente. `None` se non calcolabile (es. `weight_series` vuoto). |
| `pas_value` | `float \| None` | PAS corrente `PA(P_cert, t)`. `None` se `topology_type != "linear"` o se il PAS non è calcolabile. |
| `cusum_stat` | `float` | Valore corrente dell'accumulatore CUSUM `S_t ≥ 0`. |
| `ewma_value` | `float \| None` | Ultimo valore EWMA della serie di aderenza. `None` prima della prima chiamata a `monitor()` dopo `fit()` o dopo `reset_cusum()`. |

---

## 3. Gerarchia di attivazione dei quattro livelli

```
Livello 1a: _check_threshold(features)  → threshold_violations
Livello 1b: _check_zscore(features)     → zscore_violations
                   ↓
base_signal = len(threshold_violations) > 0 OR len(zscore_violations) > 0

Livello 2:  _check_isolation_forest(features)  [solo se base_signal=True]
                   → if_signal

Livello 3:  _update_ewma_cusum(weight_series)  [sempre, in parallelo]
                   → cusum_signal, cusum_stat, ewma_value,
                     frobenius_distance, pas_value

Livello 4:  _check_structural_validator(...)   [solo se if_signal AND cusum_signal]
                   → structural_confirmed
```

**Nota sulla metrica di Livello 3:**
- `topology_type = "linear"` (H_crit): il CUSUM opera sul **PAS**, accumulando decrementi rispetto a `PAS_gold`. Un PAS che scende sotto il riferimento indica degradazione del critical path.
- `topology_type = "parallel"` (H_cache): il CUSUM opera sulla **norma di Frobenius**, accumulando incrementi rispetto a 0 (`Frobenius_gold = 0` per costruzione). Qualsiasi deviazione dalla distribuzione nominale del traffico contribuisce all'accumulatore.

> **Nota DSB-specifico:** questa assunzione è valida solo quando `W(t)` è costante nei dati nominali — caso DSB dove il throughput è aggregato a livello di finestra (vedi Module 04 §4 per la dimostrazione). Su dataset con throughput variabile, Frobenius nominale > 0 e il CUSUM accumulerebbe anche in condizioni nominali. Su tali dataset la reference dovrebbe essere la media della Frobenius distance sui timestamp nominali, calcolata in `fit()`.

> **Tensione con scenario multivariato:** methodology.tex
> §3.2.3 descrive uno scenario in cui cpu=15% e
> pool_saturation=75% — entrambi sotto le singole soglie
> SLA e sotto il zscore — costituiscono una combinazione
> anomala rilevabile da IF come spike multivariato. Per
> costruzione, questo scenario non può essere rilevato dal
> framework: `base_signal=False` previene l'attivazione di
> IF (Livello 2). Questa è una limitazione intrinseca della
> gerarchia condizionale prescritta dalla stessa
> methodology.tex: il gating `base_signal` è il meccanismo
> che governa l'attivazione del Livello 2. Il caso d'uso
> multivariato puro richiede un'architettura alternativa
> (IF senza gating o gating basato su window-level zscore
> del vettore aggregato) non implementata in questa versione.

---

## 4. Formule matematiche

> **Comportamento con std=0 in z-score:** se una feature ha valore
   > costante nel training nominale (`σ_m = 0`), il calcolo
   > `z = (m(t) − μ_m) / 0` produce `±inf` se `m(t) ≠ μ_m` e `nan`
   > se `m(t) == μ_m`. Il caso `nan` è trattato come assenza di violazione
   > (NaN non è mai una violazione). Il caso `±inf` supera qualsiasi
   > soglia finita `zscore_threshold` ed è trattato come violazione —
   > semanticamente corretto: qualsiasi deviazione da un valore nominale
   > invariante è anomala. Questo comportamento non è testato esplicitamente
   > perché sul dataset DSB tutte le serie nominali hanno varianza non nulla.

### EWMA (Exponentially Weighted Moving Average)

```
s_1 = signal_1                          (cold start: primo valore = osservazione raw)
s_t = α × signal_t + (1 − α) × s_{t−1} (t > 1)
```

dove `α = ewma_alpha` e `signal_t` è il PAS corrente (lineare) o la Frobenius corrente (parallela).

### CUSUM unidirezionale

**Topologia lineare (PAS, accumulare decrementi):**
```
S_t = max(0, S_{t−1} + (PAS_gold − s_t − k))
```

**Topologia parallela (Frobenius, accumulare incrementi):**
```
S_t = max(0, S_{t−1} + (s_t − 0 − k))
```

dove `k = tolerance_factor` (default `0.0` — con `k > 0` si ignorano variazioni inferiori a `k`). Il `max(0, ...)` esterno impedisce che `S_t` diventi negativo (CUSUM con reset a zero). `cusum_signal = True` se `S_t > alert_threshold`. L'accumulatore decresce verso zero durante il recovery (quando PAS risale verso PAS_gold). Il reset esplicito tramite `reset_cusum()` rimane necessario tra esperimenti distinti.

**Nota:** `tolerance_factor` deve essere `< PAS_gold` per le topologie lineari. Con `PAS_gold = 0.25` e `tolerance_factor = 0.0` il CUSUM si attiva per qualsiasi decremento del PAS. Con `tolerance_factor ≥ 0.25` il CUSUM non accumula mai su H_crit.

### Derivata EWMA persistente (Validatore strutturale)

Condizione di attivazione del Livello 4:

1. soglia distanza: per topologie lineari, `|PAS(t) − PAS_gold| > distance_threshold`; per topologie parallele, `Frobenius > distance_threshold`.
2. Gli ultimi `consecutive_windows` diff consecutivi di `_ewma_history` hanno lo stesso segno di degrado: negativo per PAS (decrescente), positivo per Frobenius (crescente).

`_ewma_history` è una `deque(maxlen=consecutive_windows + 1)` — servono almeno `consecutive_windows + 1` valori per calcolare `consecutive_windows` diff.

> **Segnale di distanza per topologia lineare:**
> il Validatore usa il PAS-gap `|PAS(t) − PAS_gold| > δ`
> per topologie lineari, come prescritto da methodology.tex §3.2.3.
> Per topologie parallele usa la norma di Frobenius
> `‖W(t) − W_gold‖_F > δ`. Il discriminante è `topology_type`
> letto da `topology.yaml`.

---

## 5. Interfaccia pubblica

```python
class StructuralMonitor:
    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
        pbo_builder: PBOBuilder,
    ) -> None

    def fit(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
        nominal_snapshots: list[dict],
        weight_series: list[dict],
        gold_standard: dict[str, float],
    ) -> None

    def monitor(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
        weight_series: list[dict],
        timestamp: int,
    ) -> dict[str, Any]

    def reset_cusum(self) -> None
```

**`fit(compliance_set_name, features, nominal_snapshots, weight_series, gold_standard)`**
Addestra il monitor sui dati nominali:
1. Costruisce il vettore aggregato `X_{H_Φi}(t)` dai `nominal_snapshots` (solo feature di nodo, ordine `sorted(cs_nodes) × sorted(node_metrics)`).
2. Addestra Isolation Forest su `X` (NaN imputati con media di colonna).
3. Calcola `mean` e `std` nominali per ogni feature di M_Φi (per z-score).
4. Calcola `PAS_gold` (topologia lineare) o imposta `reference = 0.0` (parallela).
5. Chiama `reset_cusum()`.

Solleva `RuntimeError` se `nominal_snapshots = []`. Solleva `KeyError` se `compliance_set_name` non esiste in `topology.yaml`.

**`monitor(compliance_set_name, features, weight_series, timestamp) → dict`**
Esegue i quattro livelli e restituisce il `MonitorResult`. Solleva `RuntimeError` se chiamato prima di `fit()`. Solleva `KeyError` per compliance set invalido. Emette `logger.warning` se `compliance_set_name` è diverso dal compliance set usato in `fit()` — il monitor continua comunque con i parametri del CS originale (PAS_gold, topology_type).

> **Comportamento su timestamp mismatch in batch:**
> `_get_current_value` fa fallback all'ultimo valore
> disponibile della feature se il timestamp richiesto non
> è presente nell'indice del DataFrame. In esecuzione
> real-time (timestamp corrente sempre all'estremo della
> serie) questo è opportuno. In esecuzione batch con
> timestamp non allineati tra features e weight_series,
> il monitor consuma silenziosamente l'ultimo valore
> disponibile — potenzialmente datato — senza emettere
> warning. Il chiamante è responsabile di garantire
> l'allineamento temporale tra features e weight_series.

**`reset_cusum()`**
Azzera `_cusum_stat = 0.0`, `_ewma_state = None`, svuota `_ewma_history`. Chiamare prima di ogni nuovo esperimento per evitare carry-over dello stato di deriva.

---

## 6. Schema SLA in topology.yaml

Il threshold statico (Livello 1a) legge la sezione `sla` del compliance set:

```yaml
compliance_sets:
  H_crit:
    sla:
      latency_ms:
        bound: upper       # violazione se valore > threshold
        threshold: 100.0
      error_rate:
        bound: upper
        threshold: 0.05
      throughput_rps:
        bound: lower       # violazione se valore < threshold
        threshold: 10.0
```

Il matching usa il nome metrica finale della feature key: `"edge:e1:latency_ms"` → `"latency_ms"`. Se la sezione `sla` è assente o vuota `{}`, il Livello 1a non produce violazioni senza sollevare eccezioni. I valori NaN non sono mai considerati violazioni.

> **Applicazione SLA alle feature `interf:`:** il suffix matching si
   > applica a tutte le chiavi in `features`, incluse quelle con prefisso
   > `interf:`. Ad esempio, `interf:e2:throughput_rps` viene controllato
   > contro la SLA `throughput_rps` del compliance set target se tale
   > metrica è dichiarata nella sezione `sla`. Semanticamente, questo
   > confonde carico esterno (throughput di un arco di interferenza) con
   > performance interna (throughput degli archi di A(H_Φi)). Su DSB,
   > H_crit ha M_interf=∅ e H_cache non include `throughput_rps` nella
   > SLA, quindi il caso non si manifesta. Su topologie con M_interf≠∅
   > e SLA con metriche sovrapposte, le feature di interferenza vengono
   > verificate contro le soglie del CS target — comportamento da tenere
   > presente in future estensioni.

---

## 7. Parametri da pipeline_params.yaml

Tutti da `pipeline_params["anomaly_detection"]`. Chiavi obbligatorie (ValueError con nome chiave se mancanti):

| Parametro | Tipo | Valore default DSB | Descrizione |
|---|---|---|---|
| `zscore_threshold` | float | `3.0` | Soglia `|z|` per la violazione z-score adattiva. |
| `isolation_forest.contamination` | float | `0.1` | Frazione attesa di anomalie nel training set per IF. |
| `isolation_forest.n_estimators` | int | `100` | Numero di alberi dell'Isolation Forest. |
| `cusum.ewma_alpha` | float | `0.3` | Fattore di smorzamento EWMA `α ∈ (0, 1]`. |
| `cusum.alert_threshold` | float | `5.0` | Soglia CUSUM `S_t > alert_threshold` per `cusum_signal=True`. |
| `structural_validator.distance_threshold` | float | `0.15` | Soglia distanza Frobenius per il Validatore strutturale. |

Parametri opzionali con default:

| Parametro | Default | Nota |
|---|---|---|
| `cusum.tolerance_factor` | `0.0` | Margine `k` nel CUSUM. Deve essere `< PAS_gold` per topologie lineari. Con `k ≥ PAS_gold (0.25)` il CUSUM non accumula mai su H_crit. |
| `isolation_forest.random_state` | `42` | Seed per riproducibilità IF. |
| `structural_validator.trend_intervals` | `3` | Numero di finestre consecutive richieste per la derivata persistente. |

---

## 8. Dipendenze

**Esterne:**
- `scikit-learn` (`IsolationForest`) — rilevamento anomalie multivariate.
- `numpy` — operazioni vettoriali su matrici X e imputation NaN.

**Interne:**
- `ConfigLoader` — lettura di `anomaly_detection.*` da `pipeline_params.yaml` e `compliance_sets.*sla*` da `topology.yaml`.
- `TopologyBuilder` — `get_compliance_set_nodes` (per ordine deterministico del vettore IF).
- `PBOBuilder` — `compute_path_adherence` (PAS Livello 3), `compute_frobenius_distance` (Frobenius Livello 3 e 4).
- `LoggingSetup` — logger nominato `src.phase3.structural_monitor`.

---

## 9. Test (29 test in tests/test_structural_monitor.py)

Mock costruiti in memoria. 20 snapshot nominali con valori DSB nominali (cpu≈5%, mem≈512 MB). Weight series con pesi simmetrici (e3=e4=0.5, e5=e6=0.5) per training; pesi asimmetrici per test di degrado CUSUM.

### Struttura e fit (4)

| Test | Comportamento verificato |
|---|---|
| `test_monitor_returns_dict` | `monitor()` restituisce `dict`. |
| `test_monitor_result_has_required_keys` | Il dict ha esattamente le 12 chiavi richieste dal MonitorResult. |
| `test_fit_raises_on_empty_nominal_snapshots` | `fit()` con `nominal_snapshots=[]` solleva `RuntimeError`. |
| `test_monitor_raises_before_fit` | `monitor()` prima di `fit()` solleva `RuntimeError`. |

### Livello 1 — Threshold (3)

| Test | Comportamento verificato |
|---|---|
| `test_threshold_no_violation_on_nominal` | `latency_ms=10.0 < 100.0` (SLA upper) → `threshold_violations=[]`. |
| `test_threshold_violation_on_high_latency` | `latency_ms=200.0 > 100.0` → almeno una chiave `latency_ms` in `threshold_violations`. |
| `test_threshold_nan_value_not_a_violation` | Feature con `NaN` → non compare in `threshold_violations`. |

### Livello 1 — Z-score (3)

| Test | Comportamento verificato |
|---|---|
| `test_zscore_no_violation_on_nominal` | Valori nominali → `zscore_violations=[]`. |
| `test_zscore_violation_on_spike` | `cpu = mean + 4×std` (z=4 > 3.0) → chiave `cpu_percent` in `zscore_violations`. |
| `test_zscore_nan_not_a_violation` | `NaN` → non compare in `zscore_violations`. |

### Livello 2 — Isolation Forest (3)

| Test | Comportamento verificato |
|---|---|
| `test_if_inactive_without_base_signal` | `base_signal=False` → `if_signal=False` per definizione. |
| `test_if_detects_multivariate_anomaly` | `cpu=1000` (>400σ) su training con `cpu≈5±0.5` (40 snap, varianza non nulla): `base_signal=True` e `if_signal=True`. |
| `test_if_imputes_nan_in_state_vector` | Feature nodo NaN → `monitor()` completa senza eccezioni (imputation con training mean). |

### Livello 3 — EWMA + CUSUM (4)

| Test | Comportamento verificato |
|---|---|
| `test_cusum_starts_at_zero` | Dopo `fit()`, `_cusum_stat == 0.0`. |
| `test_cusum_accumulates_on_degradation` | 5 chiamate con pesi degradati → `cusum_stat > 0.0` (e4=99.0, e3=1.0) — verifica accumulo effettivo, non solo non-negatività. |
| `test_reset_cusum_zeros_accumulator` | `reset_cusum()` → `_cusum_stat == 0.0`, `_ewma_state is None`. |
| `test_cusum_signal_when_threshold_exceeded` | Con `alert_threshold=0.0001` e pesi degradati: `cusum_signal=True` in ≤10 iterazioni. |

### Livello 4 — Validatore strutturale (3)

| Test | Comportamento verificato |
|---|---|
| `test_structural_confirmed_requires_both_signals` | Solo uno dei due segnali `if_signal`/`cusum_signal` True → `structural_confirmed=False`. |
| `test_structural_not_confirmed_below_frobenius_threshold` | `frobenius_distance < distance_threshold` → `structural_confirmed=False`. |
| `test_structural_confirmed_on_persistent_degradation` | 8 finestre di degrado con `cpu=1000` (`if_signal=True` via zscore+IF), pesi fortemente degradati (`cusum_signal=True` via `threshold=0.0001`), `frobenius_threshold=0.0`: `structural_confirmed=True` confermato. |

### Robustezza (3)

| Test | Comportamento verificato |
|---|---|
| `test_monitor_unknown_compliance_set_raises` | `monitor("H_nonexistent", ...)` solleva `KeyError`. |
| `test_fit_unknown_compliance_set_raises` | `fit("H_nonexistent", ...)` solleva `KeyError`. |
| `test_missing_anomaly_detection_key_raises` | Costruttore solleva `ValueError` con match `"zscore_threshold"` se la chiave è rimossa dal YAML patchato. |

### Config guard (1)

| Test | Comportamento verificato |
|---|---|
| `test_cusum_k_loaded_from_yaml` | `monitor._cusum_k == 0.0` — guard di regressione: `tolerance_factor` in `pipeline_params.yaml` deve essere `0.0` per garantire il funzionamento del CUSUM su H_crit (PAS_gold=0.25). |

### Warning (1)

| Test | Comportamento verificato |
|---|---|
| `test_monitor_warns_on_compliance_set_mismatch` | `monitor()` emette `logger.warning` quando chiamato con CS diverso da quello di `fit()` (fit su H_crit, monitor su H_cache). |

### Robustezza aggiuntiva (4)

| Test | Comportamento verificato |
|---|---|
| `test_structural_validator_warmup_returns_false` | Warmup: `consecutive_windows` iterazioni con pesi degradati → `structural_confirmed=False` per definizione (`_ewma_history` ha meno di `consecutive_windows + 1` valori richiesti per calcolare le differenze). |
| `test_monitor_with_empty_weight_series_does_not_crash` | `weight_series=[]` → `monitor()` completa senza eccezioni; `frobenius_distance is None` (non calcolabile). |
| `test_cusum_decreases_on_recovery` | CUSUM scende verso zero durante il recovery con pesi super-nominali (PAS=1.0 >> PAS_gold=0.25) dopo accumulo su pesi degradati. Il decremento richiede ewma_new > PAS_gold: con pesi nominali (PAS=PAS_gold) l'EWMA converge dal basso e il CUSUM continua ad accumularsi; i pesi super-nominali producono ewma_new > PAS_gold e increment < 0. Verifica la rimozione dell'inner `max(0,...)`. |
| `test_structural_validator_uses_pas_gap_for_linear` | Il validatore usa PAS-gap (`|PAS(t) − PAS_gold| > δ`, non Frobenius) per topologie lineari. Verifica con soglia esplicita e pesi fortemente degradati (PAS-gap ≈ 0.24 > threshold=0.10). |
