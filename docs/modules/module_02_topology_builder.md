# Module 02 — TopologyBuilder

## 1. Obiettivo del modulo

`TopologyBuilder` implementa il Layer 1 del framework, costruendo l'ipergrafo di certificazione H_cert dal file `topology.yaml` tramite Strategia di Annotazione Semantica: la topologia del grafo è invariata rispetto al service dependency graph reale e la semantica dei compliance set è codificata come attributo `hyperedges` su ogni arco.

---

## 2. Interfaccia pubblica

```python
class TopologyBuilder:
    def __init__(self, config: ConfigLoader) -> None
    def build(self) -> nx.DiGraph
    def get_compliance_set_nodes(self, name: str) -> set[str]
    def get_critical_path(self, name: str) -> list[str]
    def get_shared_nodes(self, h_i: str, h_j: str) -> set[str]
    def get_edges_for_compliance_set(self, name: str) -> list[tuple[str, str]]
    def get_interference_edges(self, target_cs: str, other_cs: str) -> list[tuple[str, str]]
```

**`build() → nx.DiGraph`**
Costruisce il grafo H_cert e lo restituisce. **Idempotente**: alla prima chiamata costruisce e memorizza in cache; alle chiamate successive restituisce una nuova copia profonda (`copy.deepcopy`) del grafo senza ricalcolare. Ogni arco porta l'attributo `id` (edge_id da topology.yaml) oltre a `hyperedges`. Prima di aggiungere gli archi, valida che ogni endpoint (`source`, `target`) sia dichiarato in `topology["nodes"]`; solleva `ValueError` con messaggio descrittivo in caso contrario. Dopo la costruzione, emette `logger.warning` se uno o più nodi di V non appartengono ad alcun compliance set (blind spot di monitoraggio).

**`get_compliance_set_nodes(name) → set[str]`**
Restituisce l'insieme dei nodi del compliance set `name`. Solleva `KeyError` se il nome non esiste in `topology.yaml`.

**`get_critical_path(name) → list[str]`**
Restituisce la sequenza ordinata del percorso critico se definita (`topology_type: linear`). Restituisce `[]` se il compliance set ha topologia parallela (`topology_type: parallel`). Solleva `KeyError` se il compliance set non esiste. Emette `logger.warning` in due casi: (1) `topology_type == "linear"` ma `critical_path` non è definito in topology.yaml (PAS non sarà calcolabile); (2) `topology_type` non è né `"linear"` né `"parallel"` — tipo non riconosciuto, restituisce `[]`.

**`get_shared_nodes(h_i, h_j) → set[str]`**
Implementa `Shared(H_Φi, H_Φj) = H_Φi ∩ H_Φj`. Operazione simmetrica.

**`get_edges_for_compliance_set(name) → list[tuple[str, str]]`**
Implementa `A(H_Φi) = {e=(u,v) | u ∈ H_Φi AND v ∈ H_Φi}`. Derivato dinamicamente dalla topologia.

**`get_interference_edges(target_cs, other_cs) → list[tuple[str, str]]`**
Implementa `M_interf`: archi `e=(u,v)` tali che `v ∈ Shared(target_cs, other_cs)` e `u ∉ target_cs`. Restituisce `[]` senza eccezioni quando M_interf = ∅. Solleva `ValueError` se `target_cs == other_cs` (auto-interferenza non definita semanticamente). **Nota su n > 2 compliance set**: la semantica parziale di M_interf considera solo la coppia `(target_cs, other_cs)`; con più compliance set le interferenze multi-sorgente vanno calcolate chiamando il metodo su ogni coppia rilevante.

---

## 3. Struttura del grafo prodotto

Il grafo `nx.DiGraph` restituito da `build()` ha 7 nodi e 6 archi.

### Nodi

| Indice | Node ID |
|---|---|
| 0 | `nginx-web-server` |
| 1 | `nginx-thrift` |
| 2 | `home-timeline-service` |
| 3 | `home-timeline-redis` |
| 4 | `post-storage-service` |
| 5 | `post-storage-memcached` |
| 6 | `post-storage-mongodb` |

### Archi con attributo `hyperedges`

| ID | Source | Target | `hyperedges` |
|---|---|---|---|
| e1 | `nginx-web-server` | `nginx-thrift` | `["H_crit"]` |
| e2 | `nginx-thrift` | `home-timeline-service` | `["H_crit"]` |
| e3 | `home-timeline-service` | `home-timeline-redis` | `["H_cache"]` |
| e4 | `home-timeline-service` | `post-storage-service` | `["H_crit", "H_cache"]` |
| e5 | `post-storage-service` | `post-storage-memcached` | `["H_cache"]` |
| e6 | `post-storage-service` | `post-storage-mongodb` | `["H_crit"]` |

L'arco e4 è l'unico annotato con entrambi i compliance set: `home-timeline-service` e `post-storage-service` appartengono sia a H_crit sia a H_cache.

---

## 4. Proprietà matematiche verificate

Calcolate sulla topologia DSB (topology.yaml), non hardcodate nel codice.

**A(H_crit) = {e1, e2, e4, e6}** — 4 archi interni a H_crit.

**A(H_cache) = {e3, e4, e5}** — 3 archi interni a H_cache.

**Shared(H_crit, H_cache) = {home-timeline-service, post-storage-service}** — 2 nodi esatti. `nginx-thrift` appartiene solo a H_crit, non a H_cache.

**M_interf(H_crit, H_cache) = ∅** — proprietà strutturale della topologia DSB: tutti gli archi che puntano verso i nodi condivisi `{home-timeline-service, post-storage-service}` hanno come sorgente nodi già interni a H_crit (`nginx-thrift` via e2, `home-timeline-service` via e4). Non esiste alcun arco esterno a H_crit che convoglia traffico verso un nodo condiviso.

**M_interf(H_cache, H_crit) = {e2: nginx-thrift → home-timeline-service}** — `nginx-thrift` è esterno a H_cache e punta a `home-timeline-service`, che è un nodo condiviso. Il throughput su e2 è la feature di interferenza da includere in `M_interf(H_cache)` durante la feature selection.

**H_crit**: `topology_type: linear`, `critical_path` definito (sequenza di 5 nodi). PAS applicabile.

**H_cache**: `topology_type: parallel`, nessun `critical_path`. PAS non applicabile — il monitoraggio strutturale usa la norma di Frobenius come fallback.

> **Archi cross-CS**: un arco `(u, v)` i cui endpoint appartengono a
> compliance set distinti non condivisi (es. `u ∈ H_crit` only,
> `v ∈ H_cache` only) produce `hyperedges = []`. Questo arco non
> viene incluso in `A(H_Φi)` per nessun compliance set né in
> `M_interf`, rendendolo strutturalmente invisibile al framework.
> `build()` emette `logger.warning` per questo caso. Sulla topologia
> DSB corrente questo scenario non si verifica (tutti gli archi hanno
> endpoint in compliance set sovrapposti o coincidenti).

---

## 5. Dipendenze

**Esterne:**
- `networkx` — rappresentazione e manipolazione del grafo H_cert.
- `PyYAML` (tramite ConfigLoader) — lettura di `topology.yaml`.

**Interne:**
- `ConfigLoader` — unico punto di accesso alla configurazione statica.

---

## 6. Test (38 test in tests/test_topology_builder.py)

### Struttura del grafo (3)

| Test | Comportamento verificato |
|---|---|
| `test_graph_node_count` | Il grafo ha esattamente 7 nodi. |
| `test_graph_edge_count` | Il grafo ha esattamente 6 archi. |
| `test_is_directed` | Il grafo è un'istanza di `nx.DiGraph`. |

### Annotazione semantica degli archi (3)

| Test | Comportamento verificato |
|---|---|
| `test_semantic_annotation_e4` | e4 ha `hyperedges` contenente sia `H_crit` sia `H_cache`. |
| `test_semantic_annotation_e3` | e3 ha `hyperedges == ["H_cache"]` — `home-timeline-redis` non è in H_crit. |
| `test_semantic_annotation_e1` | e1 ha `hyperedges == ["H_crit"]` — `nginx-web-server` e `nginx-thrift` non sono in H_cache. |

### Nodi condivisi — Shared(H_Φi, H_Φj) (2)

| Test | Comportamento verificato |
|---|---|
| `test_shared_nodes_correct` | `Shared(H_crit, H_cache)` restituisce esattamente `{home-timeline-service, post-storage-service}`. |
| `test_shared_nodes_symmetric` | `Shared(H_crit, H_cache) == Shared(H_cache, H_crit)`. |

### A(H_Φi) — archi interni (4)

| Test | Comportamento verificato |
|---|---|
| `test_edges_h_crit_count` | `A(H_crit)` ha esattamente 4 archi. |
| `test_edges_h_cache_count` | `A(H_cache)` ha esattamente 3 archi. |
| `test_edges_h_crit_content` | `A(H_crit)` contiene esattamente le coppie `(source, target)` di e1, e2, e4, e6. |
| `test_edges_h_cache_content` | `A(H_cache)` contiene esattamente le coppie `(source, target)` di e3, e4, e5. |

### Critical path (4)

| Test | Comportamento verificato |
|---|---|
| `test_critical_path_h_crit` | `get_critical_path("H_crit")` restituisce una sequenza di 5 nodi. |
| `test_critical_path_h_cache_empty` | `get_critical_path("H_cache")` restituisce `[]` (topologia parallela). |
| `test_critical_path_invalid_raises` | `get_critical_path("H_invalid")` solleva `KeyError`. |
| `test_critical_path_h_crit_sequence` | La sequenza di H_crit è esattamente `[nginx-web-server, nginx-thrift, home-timeline-service, post-storage-service, post-storage-mongodb]`. |

### M_interf — archi di interferenza (3)

| Test | Comportamento verificato |
|---|---|
| `test_interference_h_crit_empty` | `M_interf(H_crit, H_cache)` restituisce `[]` — proprietà strutturale della topologia DSB. |
| `test_interference_h_cache_has_e2` | `M_interf(H_cache, H_crit)` contiene esattamente 1 arco con target `home-timeline-service`. |
| `test_interference_h_cache_source_and_target` | `M_interf(H_cache, H_crit)` contiene esattamente 1 arco con `source="nginx-thrift"` e `target="home-timeline-service"`. |

### get_compliance_set_nodes (3)

| Test | Comportamento verificato |
|---|---|
| `test_compliance_set_nodes_h_crit` | `get_compliance_set_nodes("H_crit")` restituisce un insieme di cardinalità 5. |
| `test_compliance_set_nodes_h_cache` | `get_compliance_set_nodes("H_cache")` restituisce un insieme di cardinalità 4. |
| `test_unknown_compliance_set_raises` | `get_compliance_set_nodes("H_invalid")` solleva `KeyError`. |

### Validazione KeyError su input errati (5)

| Test | Comportamento verificato |
|---|---|
| `test_get_shared_nodes_invalid_raises` | `get_shared_nodes("H_invalid", "H_crit")` solleva `KeyError` (primo argomento invalido). |
| `test_get_shared_nodes_invalid_second_arg_raises` | `get_shared_nodes("H_crit", "H_invalid")` solleva `KeyError` (secondo argomento invalido). |
| `test_get_edges_invalid_raises` | `get_edges_for_compliance_set("H_invalid")` solleva `KeyError`. |
| `test_get_interference_edges_invalid_raises` | `get_interference_edges("H_invalid", "H_crit")` solleva `KeyError` (primo argomento invalido). |
| `test_get_interference_edges_invalid_second_arg_raises` | `get_interference_edges("H_crit", "H_invalid")` solleva `KeyError` (secondo argomento invalido). |

### build() idempotente e isolamento (3)

| Test | Comportamento verificato |
|---|---|
| `test_build_idempotent` | Due chiamate a `build()` restituiscono grafi strutturalmente identici (stessi nodi e archi). |
| `test_build_returns_independent_copy` | Modificare il grafo restituito da `build()` non corrompe la cache interna (deepcopy garantisce isolamento). |
| `test_build_warns_on_isolated_node` | `build()` emette `logger.warning` (verificato con `mock.patch` sul logger) se un nodo di V non appartiene ad alcun compliance set; la costruzione completa senza eccezioni e il nodo isolato è incluso nel grafo. |

### Validazione endpoint archi (1)

| Test | Comportamento verificato |
|---|---|
| `test_build_invalid_endpoint_raises` | `build()` solleva `ValueError` con messaggio "non presente in topology" quando un arco punta a un nodo non dichiarato in `topology["nodes"]`. |

### Attributi arco e validazione topologia (4)

| Test | Comportamento verificato |
|---|---|
| `test_edge_id_attribute_in_graph` | Ogni arco nel `DiGraph` ha attributo `id` corrispondente all'`edge_id` in `topology.yaml` (verifica su e1). |
| `test_compliance_set_node_not_in_v_raises` | `__init__` solleva `ValueError` se un nodo del compliance set non esiste in `topology['nodes']`. |
| `test_critical_path_invalid_arc_raises` | `get_critical_path` solleva `ValueError` se la sequenza contiene una coppia consecutiva senza arco reale in `topology.yaml`. |
| `test_critical_path_node_outside_cs_raises` | `get_critical_path` solleva `ValueError` se la sequenza del `critical_path` contiene un nodo non appartenente al compliance set dichiarato in `topology.yaml`. |

### Auto-interferenza e topology_type (3)

| Test | Comportamento verificato |
|---|---|
| `test_get_interference_edges_same_cs_raises` | `get_interference_edges("H_crit", "H_crit")` solleva `ValueError` (auto-interferenza non definita). |
| `test_critical_path_linear_without_path_warns` | `get_critical_path` su compliance set `linear` privo di `critical_path` restituisce `[]` ed emette warning. |
| `test_critical_path_unknown_topology_type_warns` | `get_critical_path` con `topology_type="hierarchical"` restituisce `[]` ed emette warning con il tipo non riconosciuto. |
