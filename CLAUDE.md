# CLAUDE.md — Hybrid Hypergraph-ATG Framework

## Leggi prima di tutto

Leggi `docs/theory/methodology.tex` nella sua interezza prima di scrivere
qualsiasi riga di codice. Quel file è la specifica formale del framework.
Ogni implementazione deve tradurre fedelmente le definizioni matematiche
che contiene.

---

## Contesto del progetto

Questo repository implementa il framework ibrido Ipergrafo-ATG per il
forecasting predittivo della non-compliance di proprietà non-funzionali
in sistemi distribuiti a microservizi.

**Substrato sperimentale:** dataset GAMMA (Somashekar et al., WWW 2024)
su DeathStarBench Social Network, flusso read-home-timeline (graph_2):
7 nodi, 6 archi, ~19.000 finestre temporali.

---

## Architettura del framework

### Layer 1 — Ipergrafo di Certificazione (H_cert)

Statico, design-time. Definito interamente in `config/topology.yaml`.

- `H_cert = (V, {H_Φ1, H_Φ2, ...})`: iperarchi = compliance sets
- `A(H_Φi) = {e=(u,v) ∈ E_t | u ∈ H_Φi AND v ∈ H_Φi}`: archi interni
- `Shared(H_i, H_j) = H_i ∩ H_j`: nodi di interferenza strutturale

### Layer 2 — Attributed Temporal Graph (ATG)

Dinamico, runtime.

- `G_t = (V, E_t, X_V,t, X_E,t)`
- Feature di nodo disponibili nel dataset DSB: `cpu_percent`, `mem_mb`,
  `net_rx_mb`, `net_tx_mb`
- Feature di arco: `latency_ms`, `error_rate`, `throughput_rps`
- Nota: `gc_v` e `pool_v` esistono solo nell'esempio telemedicina di
  methodology.tex — NON nel dataset GAMMA.

### PBO — Probabilistic Behavioral Overlay

- `w_uv(t) = throughput_uv(t) / Σ_k throughput_uk(t)` (stocastico per righe)
- Nodi terminali (sink nodes): riga di zeri nella matrice W_t
- `W_gold`: media di `W_t` sulle finestre con `label_trace == 0`
- `PA(P_cert, t) = Π w_{v_i, v_{i+1}}(t)`: Path Adherence Score
  (valido solo per topologie lineari; per topologie parallele si usa
  la norma di Frobenius come fallback)

### Pipeline a quattro fasi

- **Fase I:** Feature selection topologica + forecasting locale
- **Fase II:** Analisi causale (Pearson → Granger → Transfer Entropy)
- **Fase III:** Anomaly detection (threshold/z-score → IF → EWMA/CUSUM
  → validatore strutturale)
- **Fase IV:** Sintesi semantica + generazione alert

---

## Fonti di verità

`config/topology.yaml` è la fonte per la **struttura statica**:
- nomi e indici dei nodi (l'ordine determina gli indici 0-6 nel dataset)
- definizione degli archi (id, source, target)
- membership nei compliance set (H_crit, H_cache)
- percorso critico P_cert (dove applicabile)
- topology_type per compliance set (linear → PAS applicabile;
  parallel → fallback Frobenius)
- soglie SLA
- data_paths

`config/pipeline_params.yaml` è la fonte per tutti i **parametri algoritmici**:
- parametri PBO (ewma_alpha, gold_standard_label)
- parametri di forecasting (horizon_steps, soglie, configurazione LSTM)
- parametri causal_analysis (soglie Pearson, Granger, Transfer Entropy)
- parametri anomaly_detection (zscore, Isolation Forest, CUSUM, validatore)
- parametri alert_generation (soglie lead time)

**ZERO hardcoding.** Ogni costante arriva da `ConfigLoader`.

---

## Canonical Intermediate Format

Il confine di astrazione tra ETL e framework è il formato canonico dei
tre CSV in `data/converted/`:

| File | Contenuto |
|------|-----------|
| `node_metrics.csv` | timestamp, window_id, node_id, cpu_percent, mem_mb, net_rx_mb, net_tx_mb, source_file |
| `edge_metrics.csv` | timestamp, window_id, edge_id, source, target, latency_ms, error_rate, throughput_rps, source_file |
| `ground_truth.csv` | timestamp, window_id, fault_type, date, duration, rps, replica_idx, label_trace, anomaly_node_ids, source_file |

**Tutto il codice da `src/layer1/` in poi è completamente dataset-agnostic.**
Il `DSBConverter` è specifico per il dataset GAMMA/DeathStarBench. Per
integrare un dataset diverso è sufficiente implementare un converter dedicato
che produca lo stesso schema canonico — il resto del framework rimane invariato.

---

## Workflow obbligatorio per ogni prompt

1. Leggi il prompt e le sezioni di `methodology.tex` indicate
2. Leggi il codice esistente dei moduli da cui dipendi
3. Implementa il modulo (type hints completi, logging, no print())
4. Esegui `pytest` — **tutti i test devono passare**
5. Mostra l'output completo di pytest
6. Suggerisci il messaggio di commit di github per le modifiche svolte
7. **Attendi conferma esplicita** ("ok", "vai", "approvato")
8. Solo dopo la conferma: genera `docs/modules/module_XX.md`

Non procedere mai al passo successivo senza conferma.

---

## Standard di codice

```python
# Type hints obbligatori su tutti i metodi pubblici (PEP 484)
def compute_path_adherence(self, window_id: str) -> float:
    ...

# logging, mai print()
import logging
logger = logging.getLogger(__name__)
logger.info("Computing PA for window: %s", window_id)

# Docstring su tutti i metodi e classi pubblici
```

- Un file = una responsabilità
- Nessuna logica di analisi in `src/utils/`
- Import order: stdlib → third-party → internal (blank line tra gruppi)

---

## Standard di test

- File in `tests/` con prefisso `test_`
- **Tutti i test usano dati mock sintetici** — nessun test legge CSV reali
- Fixture condivise in `tests/conftest.py`
- Naming: `test_{modulo}_{cosa_si_testa}`
- Copertura richiesta: happy path + edge case + condizioni di errore

---

## Struttura del progetto

```
config/
  topology.yaml          ← struttura statica (grafo, compliance sets, SLA)
  pipeline_params.yaml   ← parametri algoritmici (forecasting, causal, ecc.)

data/
  raw/                   ← dataset GAMMA (gitignored)
  converted/             ← output DSBConverter (canonical format)

docs/
  theory/
    methodology.tex      ← specifica formale (LEGGI PER PRIMA COSA)
    background.tex       ← contesto
  modules/               ← .md generati per ogni prompt

src/
  utils/                 → ConfigLoader, LoggingSetup
  ingestion/             → DSBConverter (ETL specifico per GAMMA)
  layer1/                → TopologyBuilder
  layer2/                → ATGBuilder, PBOBuilder
  layer3/                → FeatureSelector
  phase1/                → Forecaster (StatForecaster + DeepForecaster)
  phase2/                → CausalAnalyzer
  phase3/                → AnomalyDetector
  phase4/                → AlertGenerator
  baseline/              → ATGOnlyPipeline

tests/
```

---

## Stato corrente (aggiornato ad ogni prompt completato)

| Modulo | File | Stato | Test |
|--------|------|-------|------|
| 00 — Setup | `src/utils/config_loader.py` | 🔲 | — |
| 01 — DSBConverter | `src/ingestion/converter.py` | ⚠️ da verificare | — |
| 02 — TopologyBuilder | `src/layer1/topology_builder.py` | 🔲 | — |
| 03 — ATGBuilder | `src/layer2/atg_builder.py` | 🔲 | — |
| 04 — FeatureSelector | `src/layer3/feature_selector.py` | 🔲 | — |
| 05 — StatForecaster | `src/phase1/stat_forecaster.py` | 🔲 | — |
| 06 — DeepForecaster | `src/phase1/deep_forecaster.py` | 🔲 | — |
| 07 — CausalAnalyzer | `src/phase2/causal_analyzer.py` | 🔲 | — |
| 08 — AnomalyDetector | `src/phase3/anomaly_detector.py` | 🔲 | — |
| 09 — AlertGenerator | `src/phase4/alert_generator.py` | 🔲 | — |
| 10 — ATGOnlyBaseline | `src/baseline/atg_only_pipeline.py` | 🔲 | — |

---

## Prompt di onboarding

Prima di scrivere una sola riga di codice, devi acquisire una comprensione
completa del framework che implementerai. Non produrre codice in questa fase.

### STEP 1 — Leggi i documenti teorici

Leggi docs/theory/methodology.tex nella sua interezza, parola per parola.
Questo è il documento più importante: contiene la specifica formale completa
del framework. Presta particolare attenzione a:

- §3.1: struttura di H_cert, definizione di A(H_Φi), funzione Shared,
  proprietà strutturali, blind spot, relazione di dominanza
- §3.1.2: ATG formale, PBO, matrice W_t, Gold Standard, Path Adherence Score
- §3.1.3: Mapping M e strategia di Annotazione Semantica
- §3.2: tutta la pipeline (Fase I, II, III, IV) inclusi i meccanismi
  di CUSUM, Isolation Forest, validatore strutturale, lead time,
  classificazione alert (Giallo/Arancione/Rosso)

Poi leggi docs/theory/background.tex. Concentrati su:
- La descrizione del sistema di telemedicina (§ scenario di riferimento)
- I 5 microservizi e le loro proprietà certificate
- Il dataset GAMMA e la sua struttura

**NOTA CRITICA — metriche telemedicina vs metriche DSB:**
background.tex usa un sistema di telemedicina (5 servizi: SGW, SIN, SDB,
SAL, SBL) come esempio illustrativo del framework. Quel sistema NON è il
dataset su cui lavoriamo. Le metriche gc_v(t) e pool_v(t) citate in
methodology.tex sono specifiche della JVM della telemedicina e non esistono
nel dataset GAMMA. Le metriche di nodo disponibili in DSB sono esclusivamente:
{cpu_percent, mem_mb, net_rx_mb, net_tx_mb}.

**PRINCIPIO DI MODULARITÀ:**
Il framework è completamente dataset-agnostic a partire dal Layer 2.
Il confine di astrazione è il canonical intermediate format (i tre CSV in
data/converted/). Il DSBConverter è l'unico componente specifico per
GAMMA/DeathStarBench. Tutto il codice da src/layer1/ in poi è generico
e deve rimanere tale: nessuna assunzione hardcoded sul dataset GAMMA.

### STEP 2 — Leggi i file di configurazione

Leggi config/topology.yaml e config/pipeline_params.yaml per intero.
Nota esattamente:
- i 7 nodi e il loro ordine nella lista (determina gli indici 0-6 nel dataset)
- i 6 archi e1-e6 con source e target
- la definizione di H_crit (topology_type: linear) e H_cache
  (topology_type: parallel)
- i parametri algoritmici in pipeline_params.yaml, separati dalla topologia

Se config/pipeline_params.yaml non è presente in repo, segnalalo nelle
DOMANDE senza crearlo autonomamente.

### STEP 3 — Leggi il codice esistente

Leggi src/ingestion/converter.py per intero. Capisci esattamente:
- come si costruisce _node_map da topology["nodes"]
- come si usa _edge_dest_idx per recuperare la colonna di latenza corretta
- come funzionano _compute_node_metrics, _compute_edge_metrics,
  _compute_ground_truth
- quali colonne produce nei tre CSV di output

Leggi CLAUDE.md per capire il workflow e gli standard attesi.

**ATTENZIONE:** converter.py importa src.utils.config_loader e
src.utils.logging_setup, che non esistono ancora nel repo. Il converter
NON è attualmente importabile. Questo è atteso e corretto: Prompt 0
creerà queste dipendenze. Non segnalarlo come errore.

### STEP 4 — Rispondi con un resoconto strutturato

Quando hai finito, non produrre codice. Rispondi con:

1. **FRAMEWORK:** spiega con parole tue (in italiano) cos'è H_cert,
   cos'è A(H_Φi), cos'è il PBO, cos'è il Path Adherence Score,
   e come le quattro fasi della pipeline si connettono tra loro.
   Spiega anche perché H_cache non ha un critical_path definito e
   quale meccanismo usa il framework in sostituzione del PAS.

2. **DATASET:** descrivi la struttura del dataset GAMMA come la capirebbe
   un ingegnere che deve implementarla — nodi, archi, colonne raw,
   trasformazioni applicate dal converter. Distingui esplicitamente
   tra metriche disponibili nel dataset reale e metriche citate solo
   nell'esempio telemedicina di methodology.tex.

3. **TOPOLOGIA:** elenca i 7 nodi con il loro indice (0-6), i 6 archi
   con source/target. Poi calcola esplicitamente, applicando la
   definizione formale di methodology.tex:
   - A(H_crit) e A(H_cache)
   - Shared(H_crit, H_cache) = H_crit ∩ H_cache
   - M_interf(H_crit): archi e=(u,v) con v ∈ Shared e u ∉ H_crit
   - M_interf(H_cache): archi e=(u,v) con v ∈ Shared e u ∉ H_cache
   - Spiega il risultato di M_interf(H_crit) e le sue implicazioni
     per i test del FeatureSelector.

4. **SEPARAZIONE YAML:** spiega con precisione quale informazione vive
   in topology.yaml e quale in pipeline_params.yaml, e perché questa
   separazione è architetturalmente importante.

5. **DOMANDE:** se noti ambiguità, salti logici o incongruenze tra i
   documenti, elencali in modo diretto e critico. Se tutto è chiaro,
   concludi con: "FASE 1 COMPLETATA — Attendo il Prompt 0."

Attendi la mia conferma che il tuo resoconto è corretto prima di
ricevere il Prompt 0.