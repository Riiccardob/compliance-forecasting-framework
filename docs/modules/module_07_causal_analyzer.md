# Module 07 — CausalAnalyzer

## 1. Obiettivo del modulo

`CausalAnalyzer` implementa la Fase II del framework (methodology.tex §3.2.2), eseguendo l'analisi causale guidata dalla topologia sulle feature prodotte da `FeatureSelector`. Riceve in input `M_Φi = M_direct ∪ M_interf` per un singolo compliance set e restituisce un `CausalGraph` orientato con tipo (linear/nonlinear), intensità e metodo per ogni arco causale rilevato.

---

## 2. Struttura dati CausalGraph

Il metodo `analyze()` restituisce un dizionario con la seguente struttura:

```python
{
    "compliance_set": str,          # nome del compliance set (es. "H_crit")
    "edges": [
        {
            "source": str,          # feature key sorgente (es. "node:nginx-web-server:cpu_percent")
            "target": str,          # feature key target
            "type": str,            # "linear" (Granger) | "nonlinear" (Transfer Entropy)
            "intensity": float,     # ΔR² (Granger) | TE normalizzata (TE)
            "method": str,          # "granger" | "transfer_entropy"
            "lag": int | None,      # lag ottimale Granger; None per Transfer Entropy
        },
        ...
    ],
    "cross_property_chains": [
        {
            "source_cs": str,       # compliance set sorgente dell'interferenza
            "target_cs": str,       # compliance set target (il corrente)
            "chain": list[str],     # [interf_key, node_key, internal_edge_key]
            "confirmed": bool,      # True se entrambi i link Granger della catena sono positivi
        },
        ...
    ],
}
```

---

## 3. Pipeline di analisi

### 3.1 Categorizzazione delle coppie candidate

`_build_candidate_pairs` produce le coppie nella struttura `(source_key, target_key, category)`:

| Categoria | Descrizione | Filtro Pearson |
|---|---|---|
| `node_arc` | `node:v:metric → edge:e:metric` dove `v` è source o target di `e` e `v ∉ Shared` | Sì |
| `intra` | Tutte le coppie tra feature M_direct non già classificate `node_arc` o `inter2` | Sì |
| `inter` | `interf:e:metric` (source) → `node:v:metric` (target) dove `v ∈ Shared(H_i, H_j)`. Prima freccia della catena cross-property: θ_e_j → node_v. | **No** (bypass Pearson) |
| `inter2` | `node:v:metric → edge:e_int:metric` dove `v ∈ Shared(H_i, H_j)`. Seconda freccia della catena cross-property: node_v → e_int ∈ A(H_Φi). Come `inter`, bypassa il filtro Pearson (methodology.tex §3.2.2). | **No** (bypass Pearson) |

La deduplica si basa su `frozenset` di chiave coppia: nessuna coppia (A,B) e (B,A) vengono entrambe incluse. L'ordine di costruzione garantisce che `node_arc` e `intra` precedano `inter`.

> **Nota su analisi unidirezionale per `intra`:** la deduplica via `frozenset` garantisce che l'analisi sia unidirezionale — solo una direzione per ogni coppia è testata. La direzione causale emerge dal test di Granger e Transfer Entropy (entrambi asimmetrici: `_granger_test(A, B) ≠ _granger_test(B, A)`). L'ordine di test segue l'inserimento in `direct_keys = node_keys + edge_keys`.

### 3.2 Flusso di analisi per coppia

```
Per categoria "inter" / "inter2":
    _align_series → _test_pair_no_pearson → _run_granger_then_te

Per categoria "intra" / "node_arc":
    _align_series → _test_pair_with_pearson (controlla |r| > pearson_threshold)
        Se False → coppia scartata
        Se True  → _run_granger_then_te

_run_granger_then_te:
    1. _granger_test (con ADF pre-processing) → se positivo → edge "linear" con ΔR²
    2. Se Granger negativo → _transfer_entropy → se TE > te_threshold → edge "nonlinear"
    3. Se entrambi negativi → coppia non inclusa nel grafo
```

### 3.3 Catene cross-property

`_check_cross_property` individua catene causali del tipo:

```
interf:e_j:metric → node:v:metric → edge:e_internal:metric
```

dove `v ∈ Shared(H_i, H_j)` e `e_internal ∈ A(H_Φi)`. Ogni catena viene testata con due Granger consecutivi. Una catena è `confirmed=True` solo se entrambi i link sono statisticamente significativi. Le coppie auto-referenziali (stesso `edge_id` per `interf` e `internal_arc`) vengono saltate.

---

## 4. Implementazione dei test statistici

### 4.1 Pre-processing ADF (`_make_stationary_pair`)

Applica il test ADF (Augmented Dickey-Fuller) su entrambe le serie `effect` e `cause` indipendentemente; calcola il numero di differenziazioni necessarie per ciascuna; applica il massimo dei due conteggi a entrambe le serie. Il processo si ripete al massimo 2 volte per serie. Se dopo 2 differenziazioni la stazionarietà non è raggiunta, emette `logger.warning` e prosegue. Applicare lo stesso numero di differenziazioni ad entrambe le serie è essenziale per preservare l'allineamento temporale causa-effetto.

> **Parametri ADF fissati:** `autolag="AIC"` e il numero massimo di differenziazioni (2) non sono configurabili via YAML — corrispondono ai parametri `max_d` e alla soglia standard adottati nel modello ARIMA della Fase I.

### 4.2 Test di Granger (`_granger_test`)

- Usa `statsmodels.tsa.stattools.grangercausalitytests` con `maxlag=granger_max_lag`.
- Output soppresso via `contextlib.redirect_stdout` per evitare stampe a console.
- Seleziona il lag con p-value (F-test `ssr_ftest`) più basso.
- Calcola ΔR² = `rsquared_full − rsquared_restricted` accedendo a `results[best_lag][1]`, dove `[1][0]` è il modello ristretto e `[1][1]` è il modello completo (struttura statsmodels).
- Restituisce `None` se `best_pval ≥ granger_significance` o dati insufficienti (`n < max_lag + 2`).
- **Nota:** `ΔR² = max(0.0, r2_full − r2_restr)` — clipping a zero per evitare valori negativi da arrotondamento numerico.

### 4.3 Transfer Entropy (`_transfer_entropy`)

Stima discreta con discretizzazione uniforme `n_bins` bin:

```
TE(X→Y) = Σ p(y_t, y_{t-1}, x_{t-1}) · log2[ p(y_t, y_{t-1}, x_{t-1}) · p(y_{t-1}) / (p(y_{t-1}, x_{t-1}) · p(y_t, y_{t-1})) ]
```

Restituisce `TE / H(Y)` (normalizzata, range [0, 1]). Restituisce 0.0 se `H(Y) ≤ 0` (serie costante) o dati insufficienti.

> `n_bins` (default 10) è configurabile da
> `pipeline_params["causal_analysis"]["n_bins"]` ed è ora
> presente nel YAML. Valori più alti riducono il bias
> campionario ma richiedono n >> n_bins^2 campioni per
> stime affidabili.

### 4.4 Screening Pearson (`_pearson_screen`)

Filtro preliminare per coppie `intra` e `node_arc`: restituisce `True` se `|r_Pearson| > pearson_threshold`. Scarta la coppia (log warning) se l'intersezione ha meno di 3 campioni. Le coppie `inter` bypassano completamente questo filtro perché la correlazione lineare non è un prerequisito per l'interferenza cross-compliance.

> **Assenza di p-value nella soglia Pearson:** il filtro
> usa il valore assoluto della correlazione `|r| > threshold`
> senza associare un p-value statistico. Con n piccolo
> (n=30 nei test sintetici), `|r|=0.70` può comparire per
> caso con p-value ≈ 0.08–0.15 (non significativo a 0.05).
> Su dataset DSB reale con n≈20.000 campioni, qualsiasi
> `|r|>0.7` ha p-value ≈ 0 — il problema non si manifesta
> operativamente. Nei test sintetici con n=30, il filtro
> Pearson offre protezione statistica debole.

### 4.5 Allineamento serie (`_align_series`)

Interseca gli indici (timestamp µs) dei due DataFrame e applica `dropna()` sull'intersezione. Restituisce due `pd.Series` allineate senza NaN. Se l'intersezione ha meno di 3 campioni, la coppia viene saltata con log warning.

---

## 5. Interfaccia pubblica

```python
class CausalAnalyzer:
    def __init__(
        self,
        config: ConfigLoader,
        topology_builder: TopologyBuilder,
    ) -> None

    def analyze(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
    ) -> dict[str, Any]

    def get_causal_pairs(
        self,
        compliance_set_name: str,
        features: dict[str, pd.DataFrame],
    ) -> list[tuple[str, str, str]]
```

**`__init__(config, topology_builder)`**
Valida i parametri obbligatori di `pipeline_params["causal_analysis"]`. Solleva `ValueError` se manca una chiave obbligatoria (`pearson_threshold`, `granger_max_lag`, `granger_significance`, `transfer_entropy_threshold`). Pre-calcola le lookup table degli endpoint degli archi da `topology.yaml`.

**`analyze(compliance_set_name, features) → dict`**
Esegue la pipeline causale completa (coppie candidate → allineamento → test statistici → cross-property chains) e restituisce il `CausalGraph`. Solleva `KeyError` se `compliance_set_name` non esiste in `topology.yaml`. Le eccezioni per singola coppia vengono catturate e loggate come warning senza interrompere la pipeline.

**`get_causal_pairs(compliance_set_name, features) → list[tuple[str, str, str]]`**
Restituisce le coppie candidate `(source_key, target_key, category)` prima dell'analisi statistica. Utile per ispezione e test del meccanismo di categorizzazione. Solleva `KeyError` se `compliance_set_name` non esiste.

---

## 6. Parametri da pipeline_params.yaml

Tutti i parametri sono letti da `pipeline_params["causal_analysis"]`:

| Parametro | Tipo | Valore default DSB | Descrizione |
|---|---|---|---|
| `pearson_threshold` | float | `0.7` | Soglia `|r|` per lo screening Pearson su coppie intra/node_arc. |
| `granger_max_lag` | int | `5` | Massimo lag testato da `grangercausalitytests`. |
| `granger_significance` | float | `0.05` | Soglia p-value F-test per accettare la causalità di Granger. |
| `transfer_entropy_threshold` | float | `0.1` | Soglia TE normalizzata per accettare dipendenza nonlineare. |
| `n_bins` | int | `10` (default) | Numero di bin per la discretizzazione nella TE. Lettura da `ca.get("n_bins", 10)`. |

---

## 7. Dipendenze

**Esterne:**
- `scipy.stats.pearsonr` — screening di correlazione lineare.
- `statsmodels.tsa.stattools` (`adfuller`, `grangercausalitytests`) — test ADF e causalità di Granger.
- `numpy` — operazioni vettoriali per Transfer Entropy e stazionarietà.
- `pandas` — DataFrame input/output e allineamento serie.

**Interne:**
- `ConfigLoader` — lettura di `causal_analysis.*` da `pipeline_params.yaml` e `topology.yaml` (archi, compliance sets, edge_metrics).
- `TopologyBuilder` — query topologiche: `get_shared_nodes`, `get_edges_for_compliance_set`.
- `LoggingSetup` — logger nominato `src.phase2.causal_analyzer`.

---

## 8. Test (26 test in tests/test_causal_analyzer.py)

Mock costruiti direttamente in memoria. Serie temporali con `n=30` campioni (base) o `n=50/100/200/1000` per i test statistici. Nessun CSV reale.

### Struttura output (4)

| Test | Comportamento verificato |
|---|---|
| `test_analyze_returns_dict` | `analyze()` restituisce `dict`. |
| `test_causal_graph_has_required_keys` | Il dict ha esattamente le chiavi `{"compliance_set", "edges", "cross_property_chains"}`. |
| `test_edges_have_required_fields` | Ogni elemento di `edges` contiene almeno `{"source", "target", "type", "intensity", "method", "lag"}`. |
| `test_compliance_set_in_output` | `result["compliance_set"] == "H_crit"`. |

### Coppie candidate (5)

| Test | Comportamento verificato |
|---|---|
| `test_get_causal_pairs_returns_list` | `get_causal_pairs()` restituisce `list`. |
| `test_get_causal_pairs_categories` | Ogni elemento è una tupla di 3 con `category ∈ {"intra", "inter", "inter2", "node_arc"}`. |
| `test_inter_pairs_bypass_pearson` | Una coppia `inter` con `|r| ≈ 0` è inclusa nel risultato (bypass Pearson). |
| `test_shared_node_arc_pairs_bypass_pearson` | Coppie `(node:shared → edge:internal)` classificate come `inter2` (bypass Pearson). `home-timeline-service ∈ Shared(H_crit, H_cache)`: la coppia con `e4` deve essere `inter2`. |
| `test_adf_applied_to_both_series` | `_make_stationary_pair` applica ADF a entrambe le serie; `n_diff = max(n_effect, n_cause)`; entrambe le serie hanno lunghezza `n - n_diff`. |

### Granger (3)

| Test | Comportamento verificato |
|---|---|
| `test_granger_detects_linear_causality` | Serie lag-1 dipendente: `_granger_test` non restituisce `None`, `intensity > 0.0`, `lag ≥ 1`. |
| `test_granger_returns_none_on_independent_series` | Due serie di rumore bianco indipendente (`n=100`, seed separati): `_granger_test` restituisce `None`. |
| `test_granger_handles_insufficient_data` | Con 3 campioni (`< max_lag+2=7`): `_granger_test` restituisce `None` senza eccezioni. |

### Pearson screening (2)

| Test | Comportamento verificato |
|---|---|
| `test_pearson_screen_passes_correlated` | Serie con `r ≈ 0.99 > 0.7`: `_pearson_screen` restituisce `True`. |
| `test_pearson_screen_blocks_uncorrelated` | Serie indipendenti con `r ≈ 0 < 0.7`: `_pearson_screen` restituisce `False`. |

### Transfer Entropy (2)

| Test | Comportamento verificato |
|---|---|
| `test_transfer_entropy_positive_on_dependent` | Dipendenza nonlineare `tanh(cause_{t-1})` con `n=200`: `TE > 0.1`. |
| `test_transfer_entropy_near_zero_on_independent` | Due rumore bianco indipendente con `n=1000`, `n_bins=5`: `TE < 0.3` (bias campionamento finito < 0.02 bit). |

### Robustezza (3)

| Test | Comportamento verificato |
|---|---|
| `test_analyze_unknown_compliance_set_raises` | `analyze("H_nonexistent", ...)` solleva `KeyError`. |
| `test_analyze_empty_features_returns_empty_graph` | `features={}`: `edges=[]` e `cross_property_chains=[]`. |
| `test_analyze_all_nan_series_skips_gracefully` | Feature con tutti NaN: `analyze()` completa senza eccezioni e la feature NaN non compare in `edges`. |

### Error handling (1)

| Test | Comportamento verificato |
|---|---|
| `test_missing_causal_analysis_key_raises` | Costruttore solleva `ValueError` con match `"pearson_threshold"` se la chiave manca nel YAML patchato. |

### Regression guards (3)

| Test | Comportamento verificato |
|---|---|
| `test_get_causal_pairs_unknown_cs_raises` | `get_causal_pairs("H_nonexistent", ...)` solleva `KeyError` coerentemente con `analyze()`. |
| `test_inter_pairs_have_interf_as_source` | Le coppie `inter` hanno sempre `interf:` come source e `node:` come target — guard sulla direzione causale (throughput esterno → metrica nodo condiviso). |
| `test_granger_intensity_positive_on_causal_series` | Guard di regressione contro accesso errato alla struttura OLS di statsmodels: `ΔR² > 0.0` per relazione causale forte. |

### Cross-property e deduplicazione (3)

| Test | Comportamento verificato |
|---|---|
| `test_h_crit_has_no_cross_property_chains` | H_crit non ha feature `interf:` → `cross_property_chains = []` per costruzione. |
| `test_frozenset_deduplication_no_reverse_pair` | `get_causal_pairs` non contiene mai sia `(A, B)` che `(B, A)`: ogni coppia non ordinata compare una sola volta. |
| `test_cross_property_chain_confirmed_false_on_independent_series` | Su serie indipendenti (seed fisso), le catene di H_cache sono presenti ma `confirmed=False` — Granger non rileva causalità su dati non correlati. |
