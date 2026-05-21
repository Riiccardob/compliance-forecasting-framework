# Module 03 — ATGBuilder

## 1. Obiettivo del modulo

`ATGBuilder` implementa il Layer 2 del framework, caricando i tre CSV canonici e costruendo la sequenza temporale di snapshot `G_t = (V, E_t, X_V,t, X_E,t)` come lista di dizionari navigabili. È il substrato computazionale su cui operano tutte le fasi successive della pipeline — non esegue modelli predittivi.

---

## 2. Interfaccia pubblica

```python
class ATGBuilder:
    def __init__(
        self,
        config: ConfigLoader,
        node_metrics_path: Path,
        edge_metrics_path: Path,
        ground_truth_path: Path,
    ) -> None

    def build(
        self,
        node_df: pd.DataFrame | None = None,
        edge_df: pd.DataFrame | None = None,
        gt_df: pd.DataFrame | None = None,
    ) -> list[dict[str, Any]]
    def get_node_feature_matrix(self, snapshots: list[dict], node_id: str) -> pd.DataFrame
    def get_edge_feature_matrix(self, snapshots: list[dict], edge_id: str) -> pd.DataFrame
    @staticmethod
    def get_nominal_snapshots(snapshots: list[dict]) -> list[dict]
    @staticmethod
    def get_anomalous_snapshots(snapshots: list[dict], anomaly_type: str | None = None) -> list[dict]
```

**`build(node_df=None, edge_df=None, gt_df=None) → list[dict[str, Any]]`**

> I tre parametri sono opzionali: se `None`, il CSV corrispondente
> viene letto da disco dal path passato al costruttore. Passare
> DataFrame in-memory è supportato per i test; mescolare DataFrame
> in-memory con lettura da disco (es. `build(node_df=df)`) è
> tecnicamente possibile ma non è un pattern d'uso raccomandato
> perché il DataFrame in-memory e il CSV su disco potrebbero
> provenire da sessioni diverse.

Accetta DataFrame opzionali in memoria; se `None`, legge dal path CSV passato al costruttore. Ogni chiamata esegue l'intera pipeline di costruzione (non idempotente rispetto alla lettura su disco). Applica le tre deduplicazioni (GT, node, edge), controlla la consistenza V/E tra CSV e topology (emettendo `logger.warning` per node_id o edge_id extra o mancanti — controllo puramente consultivo, non blocca la costruzione), allinea i timestamp per inner join e restituisce la lista di snapshot ordinata per timestamp crescente. Solleva `ValueError` se l'intersezione dei timestamp è vuota. Il set degli archi `E_t` in ogni snapshot riflette gli archi effettivamente presenti in `edge_metrics.csv` per quel timestamp: se un arco dichiarato in `topology.yaml` è assente dal CSV, non comparirà nel dizionario `edges` dello snapshot.

**`get_node_feature_matrix(snapshots, node_id) → pd.DataFrame`**
Estrae la serie temporale delle feature del nodo specificato. Index: `timestamp`. Colonne: `cpu_percent`, `mem_mb`, `net_rx_mb`, `net_tx_mb`.

**`get_edge_feature_matrix(snapshots, edge_id) → pd.DataFrame`**
Estrae la serie temporale delle feature dell'arco specificato. Index: `timestamp`. Colonne: `latency_ms`, `error_rate`, `throughput_rps`.

**`get_nominal_snapshots(snapshots) → list[dict]`**
Filtra i soli snapshot con `label == 0`.

**`get_anomalous_snapshots(snapshots, anomaly_type=None) → list[dict]`**
Filtra i soli snapshot con `label == 1`. Se `anomaly_type` è specificato, filtra ulteriormente per tipo con match esatto sulla stringa (`"cpu"`, `"mem"`, `"net"`, `"cpu_mem"`) — non regex né substring.

---

## 3. Struttura dati di output — lo snapshot

Ogni elemento della lista prodotta da `build()` ha questa struttura:

```python
{
    "timestamp": int,             # timestamp in µs (chiave di join)
    "nodes": {
        "<node_id>": {            # es. "nginx-web-server"
            "cpu_percent": float,
            "mem_mb":      float,
            "net_rx_mb":   float,
            "net_tx_mb":   float,
        },
        ...                       # tutti e 7 i nodi
    },
    "edges": {
        "<edge_id>": {            # es. "e1"
            "source":         str,
            "target":         str,
            "latency_ms":     float,
            "error_rate":     float,
            "throughput_rps": float,
        },
        ...                       # archi presenti in edge_metrics.csv per quel timestamp
    },
    "label":            int,        # 0 = nominale, 1 = anomalo
    "anomaly_type":     str | None, # "cpu"/"mem"/"net"/"cpu_mem", None se label==0
    "anomaly_node_ids": list[str],  # nomi servizi anomali; [] se label==0
}
```

---

## 4. Logica di costruzione

### Deduplicazione dei tre CSV

Prima di qualsiasi join, `build()` applica tre deduplicazioni distinte nell'ordine riportato. La causa strutturale è comune a tutte e tre: nel dataset GAMMA, due esperimenti distinti eseguiti a distanza di pochi microsecondi possono generare finestre con lo stesso timestamp in µs, producendo righe con chiave identica ma valori metrici diversi.

| Chiave di deduplicazione | CSV | Righe scartate sul dataset DSB |
|---|---|---|
| `timestamp` | `ground_truth` | ≈ 623 (stimato ≈ 1%) |
| `(timestamp, node_id)` | `node_metrics` | ≈ 2.800–4.400 righe |
| `(timestamp, edge_id)` | `edge_metrics` | ≈ 623 × 6 archi |

La strategia è `keep="first"`: si mantiene la prima occorrenza per chiave. L'informazione della seconda occorrenza viene scartata senza tentare un merge — un merge produrrebbe valori metrici sintetici non presenti nel dataset originale.

### Join sui timestamp

Il join avviene sull'intersezione dei timestamp unici (`node_ts ∩ edge_ts ∩ gt_ts`) dopo le deduplicazioni. Il metodo pre-indicizza i DataFrame per `timestamp` con `groupby` prima del loop principale, riducendo il costo di lookup da O(n) a O(1) per snapshot.

### Gestione NaN

I NaN residui in `node_metrics` (presenti su `mem_mb` per l'Assunzione A2 del converter — zero forward-fill incompleto su sessioni con tutti i valori zero) vengono rilevati prima del loop e loggati come warning con il conteggio per colonna. La costruzione non si interrompe: i NaN passano nello snapshot e vengono gestiti dai moduli di forecasting a valle.

> **`get_node_feature_matrix` e `get_edge_feature_matrix` su ID
> sconosciuto**: entrambi i metodi restituiscono un DataFrame vuoto
> quando l'ID specificato non è presente in nessuno snapshot, ed
> emettono `logger.warning` con il nome dell'ID. Questo comportamento
> è coerente con il warning emesso da `build()` per ID non presenti
> nel CSV.

> **Colonne extra in `get_node_feature_matrix`:** il metodo
> costruisce il DataFrame espandendo direttamente il dict
> `snapshot["nodes"][node_id]` senza filtrare le chiavi su
> `node_metrics` di topology.yaml. Se uno snapshot contiene
> chiavi aggiuntive (ad esempio dopo un'evoluzione del
> formato CSV), queste compaiono come colonne extra nel
> DataFrame senza errori né warning. I moduli downstream
> (FeatureSelector, StatForecaster) selezionano le metriche
> per nome, quindi le colonne extra vengono semplicemente
> ignorate — nessun impatto funzionale, ma il contratto
> del metodo è più permissivo di quanto documentato.

### Campi `anomaly_type` e `anomaly_node_ids`

Derivati da `ground_truth.csv`. La semantica è:
- Se `label_trace == 0`: `anomaly_type = None`, `anomaly_node_ids = []`
- Se `label_trace == 1`: `anomaly_type = fault_type` (dal filename), `anomaly_node_ids = json.loads(anomaly_node_ids)`

Il `fault_type` in `ground_truth.csv` è estratto dal nome file dell'esperimento e vale per l'intera sessione — anche nelle finestre nominali (`label_trace == 0`) all'inizio di un esperimento. Per questo, `anomaly_type` viene impostato a `None` (non al `fault_type` grezzo) quando `label == 0`.

**Robustezza su valori NaN e malformati:** `fault_type` NaN (es. esperimento con metadati incompleti) viene convertito a `None` — mai alla stringa `"nan"`. `anomaly_node_ids` malformati (JSON non valido o NaN) producono `anomaly_node_ids = []` con `logger.warning`; non propagano eccezioni. Label fuori da {0, 1} emette `logger.warning` descrivendo che lo snapshot non sarà classificato né nominale né anomalo.

---

## 5. Comportamento su dataset reale DSB

Verificato dal sanity check ETL sul dataset completo (368 file):

| Metrica | Valore |
|---|---|
| Timestamp unici `ground_truth` | 41.849 |
| Timestamp unici `node_metrics` (per nodo) | 41.481 |
| Timestamp unici `edge_metrics` (per arco) | 41.849 |
| Differenza node vs edge | **368** (= una prima window scartata per file) |
| NaN in `mem_mb` | 99.382 celle |
| NaN in `edge_metrics` | 0 |

La differenza di 368 timestamp tra `node_metrics` e `edge_metrics` è il comportamento atteso dell'Assunzione A2 del converter (prima window scartata per nodo per assenza del baseline del counter CPU). Il `build()` la gestisce emettendo un warning e usando l'inner join; i 41.481 timestamp comuni producono la sequenza di snapshot operativa.

> **Nota sul sanity check:** i valori di §5 (41.849 timestamp GT, 41.481 node, 99.382 NaN su `mem_mb`) sono prodotti da un run che include entrambi i flussi GAMMA (`home/` e `user/`, 368 file totali). Il run di produzione standard usa solo il flusso `home/` (`read-home-timeline`, 184 file), che produce circa metà dei timestamp. I valori assoluti del sanity check non sono confrontabili con i valori di Module 01 (che documenta il solo flusso `home/`) per questa ragione.

---

## 6. Assunzioni operative

| ID | Assunzione |
|---|---|
| A1 | Timestamp come intero µs: il campo non viene convertito in `datetime64` — la conversione è delegata ai moduli di forecasting. |
| A2 | NaN residui in `mem_mb`: passano negli snapshot senza interrompere la costruzione; gestiti a valle. |
| A3 | Prima window scartata per nodo: il join inner sulle intersezioni dei timestamp la esclude automaticamente. |
| A4 | `anomaly_type = None` quando `label == 0`: anche se `fault_type` è valorizzato nel CSV, il campo viene azzerato per semantica corretta. |
| A5 | **Timestamp duplicati**: `node_metrics` e `edge_metrics` vengono deduplicati su `(timestamp, node_id)` e `(timestamp, edge_id)` con `keep="first"` prima della costruzione degli snapshot. Sul dataset DSB: ≈ 481 coppie nodo, ≈ 623 coppie arco (≈ 1%). L'informazione della seconda occorrenza viene scartata. Questo è documentato come limitazione strutturale, non corretto con logica di merge (che produrrebbe dati sintetici). |
| A6 | **Consistenza V/E consultiva**: dopo le deduplicazioni, `build()` confronta i `node_id` e `edge_id` presenti nei CSV con quelli dichiarati in `topology.yaml`. Node/edge extra o mancanti emettono `self._logger.warning` ma non bloccano la costruzione. Gli snapshot vengono prodotti dalle righe effettivamente presenti nel CSV — node_id sconosciuti appaiono negli snapshot come chiavi aggiuntive nel dizionario `nodes`; node_id mancanti producono snapshot con entry assente per quel nodo. |

---

## 7. Dipendenze

**Esterne:**
- `pandas` — caricamento CSV, groupby, join, deduplicazione.

**Interne:**
- `ConfigLoader` — accesso alla topologia.
- `LoggingSetup` — logger nominato `src.layer2.atg_builder`.

---

## 8. Test (32 test in tests/test_atg_builder.py)

Tutti i test usano mock DataFrames sintetici. I test senza fixture `atg`/`node_df`/`edge_df`/`gt_df` scrivono i CSV su `tmp_path`; i test con quelle fixture passano i DataFrame direttamente a `build()`. Mock base: tre timestamp `t0` (nominale), `t1` (anomalo `cpu`), `t2` (anomalo `cpu_mem`). Nessun CSV reale.

### Struttura della lista di snapshot (5)

| Test | Comportamento verificato |
|---|---|
| `test_build_returns_list` | `build()` restituisce un `list`. |
| `test_snapshot_count` | La lista ha esattamente 3 elementi (uno per timestamp allineato). |
| `test_snapshot_keys` | Ogni snapshot ha esattamente le chiavi `timestamp`, `nodes`, `edges`, `label`, `anomaly_type`, `anomaly_node_ids`. |
| `test_node_ids_complete` | Ogni snapshot contiene tutti e 7 i nodi da `topology.yaml`. |
| `test_edge_ids_complete` | Ogni snapshot contiene tutti e 6 gli archi da `topology.yaml`. |

### Label e anomaly_type (4)

| Test | Comportamento verificato |
|---|---|
| `test_nominal_label` | `t0` ha `label == 0` e `anomaly_type is None`. |
| `test_anomalous_label` | `t1` ha `label == 1` e `anomaly_type == "cpu"`. |
| `test_cpu_mem_type` | `t2` ha `anomaly_type == "cpu_mem"`. |
| `test_nominal_anomaly_node_ids_empty` | `t0` nominale ha `anomaly_node_ids == []`. |

### Ordinamento (1)

| Test | Comportamento verificato |
|---|---|
| `test_snapshots_ordered_by_timestamp` | I timestamp nella lista sono in ordine crescente. |

### Serie temporali per nodo e arco (2)

| Test | Comportamento verificato |
|---|---|
| `test_get_node_feature_matrix_shape` | `get_node_feature_matrix(_, "nginx-web-server")` restituisce un DataFrame di shape `(3, 4)` con colonne `cpu_percent`, `mem_mb`, `net_rx_mb`, `net_tx_mb`. |
| `test_get_edge_feature_matrix_shape` | `get_edge_feature_matrix(_, "e1")` restituisce un DataFrame di shape `(3, 3)` con colonne `latency_ms`, `error_rate`, `throughput_rps`. |

### Filtri snapshot (3)

| Test | Comportamento verificato |
|---|---|
| `test_get_nominal_snapshots_count` | `get_nominal_snapshots()` restituisce 1 elemento (`t0`). |
| `test_get_anomalous_snapshots_all_count` | `get_anomalous_snapshots()` senza filtro restituisce 2 elementi (`t1`, `t2`). |
| `test_get_anomalous_snapshots_by_type_count` | `get_anomalous_snapshots(anomaly_type="cpu")` restituisce 1 elemento (`t1`). |

### Deduplicazione (3)

| Test | Comportamento verificato |
|---|---|
| `test_duplicate_gt_timestamp_deduplicates` | Due righe GT con stesso timestamp e label diverse: la prima occorrenza (label=0) viene mantenuta, 1 snapshot prodotto. |
| `test_duplicate_node_timestamp_deduplicates` | Due righe node_metrics con stessa `(timestamp, node_id)` e `cpu_percent` diversi: la prima occorrenza (10.0) viene mantenuta. |
| `test_duplicate_edge_timestamp_deduplicates` | Due righe edge_metrics con stessa `(timestamp, edge_id)` e `latency_ms` diversi: la prima occorrenza (10.0 ms) viene mantenuta. |

### Error handling (1)

| Test | Comportamento verificato |
|---|---|
| `test_timestamp_mismatch_raises` | `ValueError` quando `node_metrics` e `edge_metrics` hanno timestamp completamente disgiunti (intersezione vuota). |

### Valori numerici esatti (2)

| Test | Comportamento verificato |
|---|---|
| `test_snapshot_node_value_exact` | `cpu_percent` di `nginx-web-server` nel primo snapshot corrisponde esattamente al valore del mock (5.0, tolleranza 1e-9). |
| `test_snapshot_edge_value_exact` | `latency_ms` di e1 nel primo snapshot corrisponde esattamente al mock (10.0 ms, tolleranza 1e-9). |

### Nodo/arco inesistente (2)

| Test | Comportamento verificato |
|---|---|
| `test_get_node_feature_matrix_unknown_node_returns_empty` | `get_node_feature_matrix` su `node_id` inesistente restituisce DataFrame vuoto ed emette `logger.warning` con il nome del `node_id`. |
| `test_get_edge_feature_matrix_unknown_edge_returns_empty` | `get_edge_feature_matrix` su `edge_id` inesistente restituisce DataFrame vuoto ed emette `logger.warning` con il nome dell'`edge_id`. |

### Robustezza ground_truth (3)

| Test | Comportamento verificato |
|---|---|
| `test_fault_type_nan_produces_none_anomaly_type` | `fault_type` NaN produce `anomaly_type=None`, mai la stringa `"nan"`. |
| `test_anomaly_node_ids_malformed_json_produces_empty_list` | `anomaly_node_ids` JSON malformato produce lista vuota senza eccezioni. |
| `test_anomaly_node_ids_dict_json_produces_empty_list` | `anomaly_node_ids` JSON valido ma non lista (es. `{}`) viene normalizzato a `[]`. |

### Consistenza V/E e label fuori range (6)

| Test | Comportamento verificato |
|---|---|
| `test_extra_node_in_csv_warns` | `node_df` con `node_id` sconosciuto (`"unknown-service"`) passato a `build()`: `logger.warning` chiamato con il nome dell'ID extra. |
| `test_build_warns_on_isolated_node` | `build()` emette warning quando un nodo è presente in `topology.yaml` e nel CSV ma non appartiene ad alcun compliance set (blind spot di monitoraggio). |
| `test_missing_node_in_csv_warns` | `node_df` privo di tutte le righe `"nginx-web-server"` passato a `build()`: `logger.warning` chiamato con il nome dell'ID mancante. |
| `test_extra_edge_in_csv_warns` | `build()` emette warning se `edge_metrics.csv` contiene un `edge_id` non dichiarato in `topology.yaml`. |
| `test_missing_edge_in_csv_warns` | `edge_df` privo di tutte le righe di un `edge_id` atteso da `topology.yaml` passato a `build()`: `logger.warning` chiamato con il nome dell'ID mancante. |
| `test_label_out_of_range_included_but_not_classified` | `label_trace == 2` emette warning; lo snapshot è incluso nella lista con `label == 2`, `anomaly_type is None`, `anomaly_node_ids == []`. |
