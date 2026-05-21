# Module 00 — Setup

## 1. Obiettivo del modulo

Fornire le primitive trasversali di configurazione e logging su cui si appoggiano tutti i moduli del framework: lettura validata dei due file YAML di configurazione e creazione di logger nominati con formato uniforme.

---

## 2. Componenti implementati

### `LoggingSetup` — `src/utils/logging_setup.py`

**Interfaccia pubblica:**

```python
LoggingSetup.configure(name: str, level: str) -> logging.Logger
```

**Comportamento:**
Crea e restituisce un `logging.Logger` identificato da `name`, con un `StreamHandler` su stderr e il formato standard `%(asctime)s | %(name)s | %(levelname)s | %(message)s`. Se il logger è già stato configurato (ha già handler), non ne aggiunge un secondo — comportamento idempotente. Non modifica il root logger né altri logger globali.

**Errori:**
- `ValueError` — se `level` non appartiene ai livelli supportati (case-insensitive: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` — both uppercase and lowercase are accepted).

---

### `ConfigLoader` — `src/utils/config_loader.py`

**Interfaccia pubblica:**

```python
ConfigLoader(topology_path: Path, pipeline_path: Path) -> None
ConfigLoader.load_topology() -> dict
ConfigLoader.load_pipeline_params() -> dict
```

**Comportamento:**
Il costruttore accetta i path ai due file YAML senza accedere al filesystem. Il caricamento è lazy: ciascun metodo legge e valida il file corrispondente alla prima chiamata, poi restituisce il dizionario in cache alle chiamate successive.

La validazione è eager rispetto al contenuto: al momento della chiamata vengono verificate tutte le chiavi obbligatorie al livello radice. La prima chiave mancante interrompe la validazione.

**Errori:**
- `FileNotFoundError` — se il file non esiste; il messaggio contiene il path assoluto risolto.
- `ValueError` — se manca almeno una chiave obbligatoria; il messaggio contiene il nome del file e il nome esatto della prima chiave mancante.
- `ValueError` — se il contenuto YAML non è un mapping valido a livello radice (ad esempio file vuoto): il messaggio riporta il tipo ottenuto.
- `ValueError` — se il file contiene YAML sintatticamente invalido (`yaml.YAMLError` viene normalizzata).

---

## 3. Schema di configurazione

### `config/topology.yaml` — chiavi obbligatorie al livello radice

| Chiave | Tipo | Semantica |
|---|---|---|
| `metadata` | dict | Identificatori del sistema (nome, dataset, flow, graph_id). |
| `nodes` | list[dict] | Lista ordinata dei 7 microservizi; l'ordine determina gli indici 0–6 nel dataset. Ogni elemento ha la chiave `id`. |
| `edges` | list[dict] | Lista dei 6 archi; ogni elemento ha `id`, `source`, `target`. |
| `compliance_sets` | dict | Mappa nome → definizione per ogni proprietà certificata. Ogni set contiene `topology_type` (`"linear"` o `"parallel"`), `nodes`, `sla`; i set lineari hanno anche `critical_path`. |
| `node_metrics` | list[str] | Nomi canonici delle feature di nodo disponibili nel dataset. |
| `edge_metrics` | list[str] | Nomi canonici delle feature di arco disponibili nel dataset. |
| `data_paths` | dict | Path relativi ai CSV di input raw e ai tre CSV del formato canonico intermedio. |

### `config/pipeline_params.yaml` — chiavi obbligatorie al livello radice

| Chiave | Tipo | Semantica |
|---|---|---|
| `version` | str | Versione dello schema di configurazione. |
| `pbo` | dict | Parametri del Probabilistic Behavioral Overlay: metrica dei pesi, α EWMA, label del gold standard. |
| `forecasting` | dict | Parametri di previsione: orizzonte, selezione del modello per tipo di serie, architettura LSTM, configurazione ARIMA, soglia di divergenza dalla baseline. |
| `causal_analysis` | dict | Soglie per i tre stadi dell'analisi causale: Pearson, Granger (significatività e max lag), Transfer Entropy. |
| `anomaly_detection` | dict | Parametri per threshold/z-score, Isolation Forest, CUSUM e validatore strutturale. |
| `alert_generation` | dict | Soglie di lead time in giorni che definiscono i livelli Giallo, Arancione e Rosso. |

---

## 4. Separazione delle responsabilità

| File | Contiene | Cambia quando |
|---|---|---|
| `topology.yaml` | Struttura statica: identità dei nodi e il loro ordine, definizione degli archi, compliance set con membership e SLA, critical path, topology_type, data paths. | Cambia l'architettura del sistema o le proprietà certificate. |
| `pipeline_params.yaml` | Parametri algoritmici: iperparametri dei modelli predittivi, soglie statistiche, configurazione CUSUM/IF, soglie di classificazione degli alert. | Si effettua tuning degli algoritmi o si ricalibrano le soglie operative. |

I due file hanno cicli di vita distinti: la topologia è stabile su scala di mesi, i parametri algoritmici variano a ogni sessione di ottimizzazione. La separazione consente di modificare l'uno senza rischiare di alterare l'altro e rende i test di ciascun layer indipendenti dall'altro file.

---

## 5. Dipendenze

**Esterne:**
- `PyYAML` — parsing dei file YAML (`yaml.safe_load`).

**Interne:** `ConfigLoader` dipende da `LoggingSetup` per il logger di modulo. `LoggingSetup` non dipende da altri moduli del framework.

---

## 6. Requisiti dei test

File: `tests/test_config_loader.py` — 33 test.

| Test | Comportamento verificato |
|---|---|
| `test_load_topology_returns_dict` | `load_topology()` restituisce un `dict`. |
| `test_nodes_count` | Il dizionario contiene esattamente 7 nodi. |
| `test_edges_count` | Il dizionario contiene esattamente 6 archi. |
| `test_compliance_sets_present` | Sono presenti sia `H_crit` sia `H_cache` nei compliance set. |
| `test_h_crit_node_count` | `H_crit` contiene esattamente 5 nodi. |
| `test_h_cache_node_count` | `H_cache` contiene esattamente 4 nodi. |
| `test_critical_path_length` | La sequenza del critical path di `H_crit` ha esattamente 5 elementi. |
| `test_edge_naming_starts_at_e1` | Il primo arco nella lista ha `id == "e1"`. |
| `test_node_metrics_exact` | `node_metrics` corrisponde esattamente a `["cpu_percent", "mem_mb", "net_rx_mb", "net_tx_mb"]`. |
| `test_compliance_nodes_subset_of_nodes` | Ogni nodo dichiarato in `H_crit` e `H_cache` è presente nell'insieme globale dei nodi. |
| `test_h_cache_has_no_critical_path` | `H_cache` non contiene la chiave `critical_path`. |
| `test_topology_type_h_crit_linear` | `H_crit["topology_type"] == "linear"`. |
| `test_topology_type_h_cache_parallel` | `H_cache["topology_type"] == "parallel"`. |
| `test_pipeline_params_loads` | `load_pipeline_params()` restituisce un `dict`. |
| `test_lstm_config_present` | Il blocco `lstm` è presente sotto `forecasting`. |
| `test_arima_config_present` | Il blocco `arima` è presente sotto `forecasting`. |
| `test_missing_topology_file_raises` | Con path inesistente viene sollevato `FileNotFoundError` con il path nel messaggio. |
| `test_missing_key_raises` | Con YAML incompleto (mancano chiavi obbligatorie) viene sollevato `ValueError` contenente il nome della chiave mancante (`"edges"`). |
| `test_empty_yaml_raises_value_error` | Con YAML vuoto viene sollevato `ValueError` che segnala l'assenza di un mapping YAML valido. |
| `test_invalid_log_level_raises` | `LoggingSetup.configure(..., "VERBOS")` solleva `ValueError` con messaggio esplicito sui livelli consentiti. |
| `test_logging_idempotent_no_duplicate_handlers` | Due chiamate con lo stesso `name` restituiscono lo stesso logger senza duplicare gli handler (`len(logger.handlers) == 1`). |
| `test_load_pipeline_params_missing_file_raises` | `FileNotFoundError` se `pipeline_path` non esiste. |
| `test_load_pipeline_params_missing_key_raises` | `ValueError` se manca una chiave obbligatoria in `pipeline_params`. |
| `test_load_topology_cache_is_isolated` | Mutare il `dict` restituito non corrompe la cache interna. |
| `test_load_pipeline_cache_is_isolated` | Mutare il `dict` di pipeline restituito non corrompe la cache. |
| `test_edge_metrics_exact` | `topology["edge_metrics"] == ["latency_ms", "error_rate", "throughput_rps"]`. |
| `test_malformed_yaml_raises` | YAML sintaticamente invalido solleva `ValueError` con messaggio che contiene `"sintaticamente non valido"`. |
| `test_load_topology_cache_deep_isolation` | Mutare una struttura annidata (`compliance_sets.H_crit.nodes`) nel dict restituito non corrompe la cache interna (deepcopy protegge anche i livelli annidati). |
| `test_load_pipeline_cache_deep_isolation` | Mutare un valore annidato (`anomaly_detection.cusum.ewma_alpha`) nel dict restituito non corrompe la cache interna. |
| `test_yaml_root_list_raises` | YAML con radice lista (non dict) solleva `ValueError`. |
| `test_window_duration_seconds_missing_raises` | `load_topology()` solleva `ValueError` se `metadata.window_duration_seconds` è mancante. |
| `test_window_duration_seconds_invalid_raises` | `load_topology()` solleva `ValueError` se `window_duration_seconds` è non positivo. |
| `test_lowercase_level_accepted` | `LoggingSetup.configure(..., "info")` accetta livelli in minuscolo senza eccezioni (`logger.level == logging.INFO`). |
---

## 7. Note operative

- **Logger di modulo in `config_loader.py`**: il modulo istanzia il proprio logger a livello `INFO` al momento dell'import. Questo è il comportamento atteso per un modulo di utilità; il livello non è configurabile dall'esterno perché il logging di configurazione non è parte del contratto pubblico del modulo.

- **Assenza di `tests/__init__.py`**: è una scelta architetturale. La presenza di `__init__.py` in `tests/` causa conflitti di discovery con pytest in alcuni layout di progetto. Il campo `pythonpath = .` in `pytest.ini` garantisce che `from src.utils.config_loader import ConfigLoader` funzioni correttamente nei test senza manipolare `sys.path` manualmente.

- **`data/raw/` e `data/converted/`**: le directory sono pre-esistenti e non vengono toccate da questo modulo. `ConfigLoader` legge i path da `topology.yaml["data_paths"]` ma non accede al filesystem dati — questa responsabilità appartiene a `DSBConverter` e agli step successivi della pipeline.
