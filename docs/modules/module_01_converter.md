# Module 01 — Converter

## 1. OBIETTIVO DEL MODULO

`DSBConverter` è il solo componente dataset-specific del framework: converte i CSV raw GAMMA/DSB nel canonical intermediate format, disaccoppiando ETL e pipeline generica.

## 2. INTERFACCIA PUBBLICA

### Metodi pubblici

```python
def convert_all(self, raw_dir: Path) -> None
def convert_file(self, filepath: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
```

### Metodi privati (firma + comportamento)

```python
def _parse_filename(self, filename: str) -> dict[str, str | int | None]
```
Estrae metadati dal nome file GAMMA. Restituisce tutti i campi a `None` (senza eccezioni) se il filename non rispetta il pattern regolare. In caso di mismatch, emette `logger.warning` specificando che le metriche verranno processate ma i metadati (`fault_type`, `date`, `rps`, `replica_idx`) saranno `None`. Il file non viene scartato — i dati di metrica sono comunque validi.

`convert_file(filepath)` — Converte un singolo file CSV raw nei tre DataFrame canonici `(node_df, edge_df, gt_df)`. Usata internamente da `convert_all` e direttamente nei test per isolare la trasformazione senza I/O su disco.

### Metodi privati (firma + comportamento)

```python
def _aggregate_window_metrics(self, df: pd.DataFrame) -> pd.DataFrame
```
Aggrega le tracce per `window_id` e produce un record per finestra con timestamp, contatori/medie e conteggi anomalia.

```python
def _compute_node_metrics(self, agg: pd.DataFrame, source_file: str) -> pd.DataFrame
```
Converte le metriche nodo in formato long (`cpu_percent`, `mem_mb`, `net_rx_mb`, `net_tx_mb`) con gestione dei reset dei contatori rete.

```python
def _compute_edge_metrics(self, agg: pd.DataFrame, source_file: str) -> pd.DataFrame
```
Calcola metriche arco (`latency_ms`, `error_rate`, `throughput_rps`) usando il nodo destinazione per la latenza e fallback su `window_duration_seconds` da `topology.yaml["metadata"]` per `delta_t` non valido.

```python
def _compute_ground_truth(
    self,
    agg: pd.DataFrame,
    metadata: dict[str, str | int | None],
    source_file: str,
) -> pd.DataFrame
```
Produce il ground truth per finestra con label binaria e `anomaly_node_ids` serializzato in JSON.

## 3. SCHEMA DEI CSV DI OUTPUT

Schemi verificati leggendo i CSV reali in `data/converted/`.

### `node_metrics.csv`

Colonne: `timestamp, window_id, node_id, cpu_percent, mem_mb, net_rx_mb, net_tx_mb, source_file`

- `timestamp` — `int64`: timestamp della finestra (microsecondi, inizio finestra aggregata).
- `window_id` — `object`: identificatore finestra temporale nel file raw.
- `node_id` — `object`: nome canonico del microservizio (da `topology.yaml`).
- `cpu_percent` — `float64`: utilizzo CPU percentuale ricavato da counter cumulativo.
- `mem_mb` — `float64`: memoria in MB del nodo.
- `net_rx_mb` — `float64`: delta traffico ricevuto in MB nella finestra.
- `net_tx_mb` — `float64`: delta traffico trasmesso in MB nella finestra.
- `source_file` — `object`: nome file raw da cui il record e stato derivato.

### `edge_metrics.csv`

Colonne: `timestamp, window_id, edge_id, source, target, latency_ms, error_rate, throughput_rps, source_file`

- `timestamp` — `int64`: timestamp della finestra.
- `window_id` — `object`: identificatore finestra temporale.
- `edge_id` — `object`: ID arco canonico (`e1..e6`).
- `source` — `object`: nodo sorgente dell'arco.
- `target` — `object`: nodo destinazione dell'arco.
- `latency_ms` — `float64`: latenza media in millisecondi dell'interazione sull'arco.
- `error_rate` — `float64`: quota tracce anomale nella finestra.
- `throughput_rps` — `float64`: throughput della finestra in richieste/secondo.
- `source_file` — `object`: nome file raw di origine.

### `ground_truth.csv`

Colonne: `timestamp, window_id, fault_type, date, duration, rps, replica_idx, label_trace, anomaly_node_ids, source_file`

- `timestamp` — `int64`: timestamp della finestra.
- `window_id` — `object`: identificatore finestra temporale.
- `fault_type` — `object`: tipo fault estratto dal filename (es. `cpu`, `mem`, `net`, `cpu_mem`).
- `date` — `object`: token data esperimento dal filename.
- `duration` — `object`: durata fault (stringa, puo essere assente nel nome file).
- `rps` — `float64`: livello di carico (request per second) dal filename.
- `replica_idx` — `float64`: indice replica esperimento dal filename.
- `label_trace` — `int64`: 0/1 anomalia finestra (`1` se almeno una traccia anomala).
- `anomaly_node_ids` — `object`: lista JSON dei nodi anomali nella finestra.
- `source_file` — `object`: nome file raw sorgente.

## 4. TRASFORMAZIONI APPLICATE

- `cpu_percent = (counter_t1 - counter_t0) / (ts_t1 - ts_t0) * 100`. Delta negativi (reset counter Prometheus per restart container) vengono mascherati a NaN e forward-filled, con fallback 0.0 per leading NaN — stesso trattamento di net_rx_mb e net_tx_mb.
- `mem_mb = bytes / 1_048_576`
- `net_rx_mb = (rx_counter_t1 - rx_counter_t0) / 1_048_576`
- `net_tx_mb = (tx_counter_t1 - tx_counter_t0) / 1_048_576`
- `latency_ms = mean(span_duration_us_dest_node) / 1000`
- `throughput_rps = n_tracce / delta_t_secondi` (fallback: `window_duration_seconds` da `topology.yaml["metadata"]` se `delta_t` è `NaN` o `<= 0`, incluso single-window)
- `error_rate = n_anomale / n_totali`, con dominio `[0, 1]`

## 5. ASSUNZIONI OPERATIVE

- **A1** — Prima window scartata (delta CPU non calcolabile).
- **A2** — `mem_mb == 0 -> NaN -> forward-fill` scoped per nodo -> leading NaN -> backward-fill. Copertura post-fill: 100%.
- **A3** — Delta negativo `net_rx/net_tx -> NaN -> forward-fill`.
- **A4** — Timestamp irregolari: mediana ~5s, gap inter-esperimento fino a ~915.000s. Nessun resampling applicato.
- **A5** — Colonne mancanti: quando una colonna di metrica CPU manca per un nodo, quel nodo viene saltato con `logger.warning`. La gestione è già implementata nel codice — il dataset GAMMA ha tutte le colonne per costruzione.

> **Nota — `latency_ms` su arco inattivo**: se in una finestra non
> esistono span con nodo destinazione `v` per l'arco `(u, v)`,
> `mean()` su serie vuota produce `NaN`. Questo `NaN` entra in
> `edge_metrics.csv` e negli snapshot ATG. Sul dataset DSB tutti
> e 6 gli archi sono sempre attivi (topologia fissa), quindi il
> caso non si verifica. Il comportamento NaN è coerente con quello
> di `mem_mb` (Assunzione A2): i valori mancanti passano negli
> snapshot e sono gestiti a valle dai moduli di forecasting.

> **Ultima finestra per file — discontinuità W_t:** in
> `_compute_edge_metrics`, `t_w = t_sec.diff().shift(-1)`
> produce NaN per l'ultima riga di ogni file raw. Il fallback
> è `window_duration_seconds` (5.0s da topology.yaml). Di
> conseguenza, il `throughput_rps` dell'ultima finestra di
> ogni esperimento GAMMA è calcolato con un denominatore
> fisso invece del delta_t reale. Con N file raw concatenati,
> questo introduce N finestre con pesi W_t non confrontabili
> con il resto della serie. L'effetto su PBOBuilder è
> trascurabile su N<<T (N=184, T=41k su DSB) ma va tenuto
> presente su dataset con finestre brevi o N grande.

> **`fault_type` non validato:** `_compute_ground_truth`
> legge `metadata["fault_type"]` dal nome del file senza
> verificare che il valore appartenga al set chiuso noto
> ("cpu", "mem", "cpu_mem", "net"). Un valore inatteso
> nel nome del file diventa `anomaly_type` senza warning.
> `ATGBuilder.get_anomalous_snapshots` filtra per match
> esatto, quindi un tipo non riconosciuto produce
> semplicemente 0 risultati nel filtering — nessun crash.

**Nota di design:** `error_rate` e `throughput_rps` sono calcolati a livello di finestra temporale (tutte le tracce della finestra) e assegnati identici a tutti gli archi della stessa finestra. Questo è un'approssimazione strutturale del dataset GAMMA, che non fornisce conteggi disaggregati per singola dipendenza RPC. Il PAS risultante è quasi costante per questo motivo (documentato in `§4. Proprietà strutturali sul dataset DSB` di `module_04_pbo_builder.md`).

## 6. DIPENDENZE

- **Esterne:** `pandas` — lettura CSV raw, aggregazione, scrittura CSV canonici.
- **Interne:** `ConfigLoader` (`topology_path`, `pipeline_path`).

> - `PyYAML` — dipendenza *transitiva* (importata da `ConfigLoader`, non direttamente da `DSBConverter`).

## 7. METRICHE VERIFICATE — RUN COMPLETO

Run eseguito sui **184 file** `*_graph_2.csv` del flusso home
(`DATASET/processed_dataset/home/multi-modal-data-separate/`).

| File | Righe di dati |
|---|---|
| `ground_truth.csv` | 23.176 |
| `node_metrics.csv` | 160.944 |
| `edge_metrics.csv` | 139.056 |

Il flusso `user/` (184 file, schema a 66 colonne) non è compatibile con
`topology.yaml` (`graph_2`, 7 nodi) e non viene processato.

---

## 8. TEST (25 test in tests/test_converter.py)

- `test_first_window_dropped_for_cpu` — verifica che la prima finestra non produca record nodo (diff CPU `NaN`).
- `test_mem_zero_forward_filled` — verifica imputazione memoria zero con valore precedente.
- `test_net_rx_delta_correct` — verifica correttezza del delta RX in MB.
- `test_latency_ms_conversion` — verifica conversione latenza da microsecondi a millisecondi.
- `test_throughput_rps_positive` — verifica throughput strettamente positivo sui record arco.
- `test_error_rate_window_anomalous` — verifica `error_rate == 1.0` nella finestra anomala del mock.
- `test_ground_truth_anomaly_node_ids` — verifica presenza del nodo anomalo nel JSON `anomaly_node_ids`.
- `test_ground_truth_metadata_extraction` — verifica parsing corretto di `fault_type`, `rps`, `replica_idx`.
- `test_filename_without_duration` — verifica parsing filename senza token `duration`.
- `test_filename_with_repeat_token` — verifica gestione token extra (`repeat`) nel filename.
- `test_filename_cpu_mem` — verifica parsing del `fault_type` composto `cpu_mem`.
- `test_cpu_percent_value_correct` — verifica formula CPU percentuale sul mock controllato.
- `test_net_negative_delta_forward_filled` — verifica gestione delta RX negativo con normalizzazione a valore non negativo.
- `test_error_rate_nominal_zero` — verifica `error_rate == 0.0` nella finestra nominale.
- `test_window_duration_seconds_from_yaml_no_warning` — nessun warning se `window_duration_seconds` è presente in metadata.
- `test_mem_bfill_on_leading_nan` — leading NaN su `mem_mb` (prima window con mem_bytes=0) risolto con backward-fill.
- `test_convert_all_writes_three_csvs` — `convert_all` scrive i tre CSV canonici nei path configurati.
- `test_cpu_negative_delta_masked_and_forward_filled` — delta CPU negativo (restart container) mascherato a NaN e forward-filled; nessun valore negativo in output.
- `test_filename_with_prefix_token` — token opzionale (es. `test`) tra `fault_type` e `date` viene ignorato dalla regex.
- `test_net_negative_delta_true_ffill_three_windows` — in un mock a 3 finestre, il delta negativo su w2 viene forward-filled con il valore positivo di w1 (non con `fillna(0.0)`), verificando il meccanismo reale di ffill quando esiste un predecessore valido.
- `test_error_rate_fillna_on_zero_denominator` — window con 0 tracce anomale (tutte nominali) produce `error_rate == 0.0` senza divisione per zero.
- `test_parse_filename_malformed_returns_none_fields` — filename che non rispetta il pattern restituisce tutti i campi a `None` senza eccezioni.
- `test_cpu_zero_delta_t_produces_nan` — due finestre con timestamp identici (delta_t=0) producono `cpu_percent` finito (non `inf`).
- `test_convert_all_empty_directory_does_not_crash` — `convert_all` su directory vuota termina senza eccezioni e non scrive file di output.
- `test_throughput_fallback_uses_yaml_value` — su singola finestra (delta_t NaN), `throughput_rps = n_tracce / window_duration_seconds` con il valore letto da `topology.yaml`; guard di regressione contro il reintroduzione di fallback hardcoded.

