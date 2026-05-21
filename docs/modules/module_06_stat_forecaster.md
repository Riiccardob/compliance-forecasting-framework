# Module 06 — StatForecaster

## 1. Obiettivo del modulo

`StatForecaster` implementa il forecasting locale di Fase I (methodology.tex §3.2.1), orchestrando quattro modelli su routing configurato da `pipeline_params.yaml`.

---

## 2. Modelli implementati

| Modello | Tipo | Libreria | Incertezza (yhat_lower / yhat_upper) |
|---|---|---|---|
| **Prophet** | Reale | `prophet` | Intervallo di credibilità bayesiano (`interval_width=0.80`, default libreria — non passato esplicitamente nel costruttore; l'unico argomento usato è `changepoint_prior_scale=0.05`) |
| **LSTM** | Placeholder (Ridge) | `scikit-learn` | Margine simmetrico: `±(|yhat| × 0.05 + 1e-6)` |
| **ARIMA** | Reale | `statsmodels` (SARIMAX) | Intervallo di confidenza al 95% (`conf_int(alpha=0.05)`) |
| **Linear** | Reale | `scikit-learn` | `±1.96 × σ_residui` (residui calcolati sul training set) |

### Prophet
Attivato dal routing automatico per le feature non-nonlinear. I timestamp in µs vengono convertiti in `datetime64` con `pd.to_datetime(index, unit="us")`. I timestamp futuri sono generati manualmente come `last_ts + (i+1) × freq_us`, garantendo esattamente `horizon_steps` righe indipendentemente dall'irregolarità del dataset.

### LSTM (Ridge placeholder)
Attivato dal routing automatico per le feature in `forecasting.lstm.nonlinear_metrics` (default: `mem_mb`) quando il training set ha almeno `input_window × 2` campioni. Usa `Ridge` di scikit-learn su feature laggiate di larghezza `min(input_window, n-1)`.

**Nota:** Ridge è un placeholder computazionale per i test. Un TODO nel codice (`_fit_lstm_placeholder`, `_predict_lstm_placeholder`) indica dove sostituire con un LSTM PyTorch/Keras con Monte Carlo Dropout per la stima dell'incertezza in produzione.

### ARIMA
Attivato via `model_override`. Seleziona automaticamente l'ordine `(p, d, q)` minimizzando l'AIC (`information_criterion: aic` in `pipeline_params.yaml`) con ricerca esaustiva su `{0..max_p} × {0..max_d} × {0..max_q}`. I default sono `max_p=2, max_d=1, max_q=2` (letti da `arima_cfg.get()` come fallback rapido per i test); i valori del YAML (`max_p=5, max_d=2, max_q=5`) sono usati in produzione.

Dopo la selezione dell'ordine ottimale, i residui vengono testati con il **test di Ljung-Box** (`acorr_ljungbox` di statsmodels). Il test è puramente diagnostico: non modifica il modello selezionato, ma emette `logger.warning` se la p-value è `< 0.05` su un numero di lag pari a `max(1, min(10, n_residui // 5))`. Il warning include l'ordine `(p,d,q)` ottimale e la p-value minima. Se `acorr_ljungbox` non è disponibile nell'ambiente, viene emesso un warning alternativo e il modello viene restituito ugualmente.

### Linear Regression
Attivato via `model_override`. Modello baseline `y = a + b·t` su indice temporale. L'incertezza è stimata dalla deviazione standard dei residui di training, proiettata come intervallo `±1.96σ` sul futuro.
---

## 3. Routing

Il routing è determinato dal metodo privato `_route_model(key, metric_name, n_samples, model_override)`:

```
metric_name = feature_key.split(":")[-1]

1. Se key in model_override → usa il modello specificato (override esplicito)
2. Se metric_name in forecasting.lstm.nonlinear_metrics:
       Se n_samples < input_window × 2 → "prophet" + logger.warning (fallback)
       Altrimenti → "lstm"
3. Altrimenti → "prophet" (default)
```

**Sorgente dei parametri:** `forecasting.lstm.nonlinear_metrics` e `forecasting.lstm.input_window` sono letti da `pipeline_params.yaml` — nessun hardcoding.

**model_override:** dizionario opzionale `{feature_key: model_name}` passato a `fit()`. Sovrascrive il routing automatico per le chiavi specificate. Valori ammessi: `"prophet"`, `"lstm"`, `"arima"`, `"linear"`.

**NOTA:** Il routing automatico copre esclusivamente Prophet e LSTM. ARIMA e Linear Regression non vengono mai selezionati dal routing automatico — richiedono `model_override` esplicito. Questa è una scelta deliberata: Prophet gestisce nativamente serie irregolari, con trend, stagionalità e changepoint, rendendolo un default sicuro per la maggior parte delle metriche di sistema distribuito. ARIMA e Linear sono accessori configurabili per scenari specifici (ARIMA per serie stazionarie con forte componente MA, Linear come baseline). La spec di `methodology.tex §3.2.1` descrive le caratteristiche dei quattro modelli senza prescrivere il routing automatico tra tutti e quattro.

**Test gap documentati:**
- `_infer_freq_us` non è coperto da test unitari su serie con gap
    inter-campionamento irregolari. La correttezza del calcolo della
    mediana (vs media) è verificata dall'integrazione con il dataset DSB reale.
- `test_fit_ignores_anomalous_snapshots` verifica che l'orizzonte di predict
    sia invariato rispetto alla dimensione del training set, ma non verifica
    direttamente che il fitting sia avvenuto sui soli timestamp nominali.
    Il comportamento è verificato indirettamente dal fallback Prophet su
    training set ridotto.
---

## 4. Interfaccia pubblica

```python
class StatForecaster:
    def __init__(self, config: ConfigLoader) -> None

    def fit(
        self,
        features: dict[str, pd.DataFrame],
        nominal_snapshots: list[dict] | None = None,
        model_override: dict[str, str] | None = None,
    ) -> None

    def predict(
        self,
        horizon_steps: int | None = None,
    ) -> dict[str, pd.DataFrame]

    def get_model_routing(self) -> dict[str, str]
```

**`fit(features, nominal_snapshots, model_override)`**
Addestra un modello per ogni feature nel dizionario. Se `nominal_snapshots` è fornito, il training set è filtrato sui soli timestamp nominali (`label == 0`). `model_override` permette di forzare un modello specifico per singola feature, bypassando il routing automatico. Una seconda chiamata a `fit()` sovrascrive completamente lo stato interno: i modelli addestrati e il routing vengono rimpiazzati. `predict()` e `get_model_routing()` dopo una seconda chiamata riflettono esclusivamente l'ultimo `fit()`.

**`predict(horizon_steps) → dict[str, pd.DataFrame]`**
Genera previsioni per tutte le feature addestrate. `horizon_steps=None` usa `forecasting.horizon_steps` da `pipeline_params.yaml`. Ogni DataFrame ha index `timestamp` (int µs futuri) e colonne `yhat`, `yhat_lower`, `yhat_upper`. Solleva `RuntimeError` se chiamato prima di `fit()`.

**`get_model_routing() → dict[str, str]`**
Restituisce la mappa `feature_key → nome_modello` stabilita durante `fit()`. Solleva `RuntimeError` se chiamato prima di `fit()`.

---

## 5. Gestione dei timestamp irregolari (dataset DSB)

Il dataset DSB ha timestamp irregolari: all'interno di un singolo esperimento la frequenza è nominalmente 5 s, ma tra esperimenti contigui i gap possono raggiungere 915.112 s (15+ minuti). Questo non richiede resampling perché:

- **Prophet** accetta serie con date irregolari: il modello lavora su `ds` come `datetime64` e apprende la tendenza e la stagionalità indipendentemente dalla regolarità degli intervalli.
- **ARIMA e Ridge** operano sull'indice intero dei valori, non sull'asse temporale assoluto — la frequenza non entra nel fitting.
- **Linear Regression** usa il valore numerico del timestamp come regressore, quindi i gap si traducono direttamente in una pendenza corretta.

La frequenza di campionamento (`freq_us`) è stimata dalla mediana dei diff sull'indice del training set (`_infer_freq_us`). Questa stima è robusta agli outlier (i gap inter-esperimento) proprio perché usa la mediana. I timestamp futuri sono costruiti manualmente come `last_ts + (i+1) × freq_us`, garantendo una proiezione coerente con la finestra di raccolta dati nominale.

La conversione dei timestamp µs → `datetime64` avviene con `pd.to_datetime(index, unit="us")` nel solo `_fit_prophet` — gli altri modelli non richiedono conversione.

**Guard `_infer_freq_us`:** Per serie con meno di 2 campioni, `_infer_freq_us` restituisce il fallback `5_000_000` µs (5 s) senza calcolare diff. Per serie con tutti i timestamp identici (mediana dei diff = 0 µs), emette `logger.warning` e restituisce lo stesso fallback. Entrambi i guard prevengono divisioni per zero in `_predict_*` (Prophet, LSTM, ARIMA, Linear) quando `freq_us` sarebbe ≤ 0.

---

## 6. Dipendenze

**Esterne:**
- `prophet` — modello Prophet con intervallo di credibilità bayesiano.
- `statsmodels` (SARIMAX) — fitting ARIMA con selezione ordine via AIC.
- `scikit-learn` (Ridge, LinearRegression) — LSTM placeholder e modello baseline.
- `numpy` — operazioni vettoriali su serie temporali.
- `pandas` — DataFrame input/output e conversione timestamp.

**Interne:**
- `ConfigLoader` — lettura di `forecasting.*` da `pipeline_params.yaml` (`horizon_steps`, `lstm.input_window`, `lstm.nonlinear_metrics`, `arima.max_p/d/q`).
- `LoggingSetup` — logger nominato `src.phase1.stat_forecaster`.

---

## 7. Test (23 test in tests/test_stat_forecaster.py)

Mock costruiti direttamente in memoria. Due serie da 50 campioni (`_N=50 ≥ input_window×2=48`): `node:nginx-web-server:cpu_percent` (prophet routing) e `node:home-timeline-service:mem_mb` (lstm routing). Nessun CSV reale.

### Routing pre-fit (1)

| Test | Comportamento verificato |
|---|---|
| `test_get_model_routing_before_fit_raises` | `get_model_routing()` prima di `fit()` solleva `RuntimeError`. |

### Routing post-fit (3)

| Test | Comportamento verificato |
|---|---|
| `test_routing_cpu_percent_is_prophet` | `cpu_percent` non è in `nonlinear_metrics` → routing `"prophet"`. |
| `test_routing_mem_mb_is_lstm` | `mem_mb` è in `nonlinear_metrics` e `_N=50 ≥ 48` → routing `"lstm"`. |
| `test_get_model_routing_after_fit_returns_dict` | `get_model_routing()` restituisce `dict` con una chiave per ogni feature. |

### Fit (2)

| Test | Comportamento verificato |
|---|---|
| `test_fit_completes_without_exception` | `fit()` su mock_features non solleva eccezioni. |
| `test_predict_before_fit_raises` | `predict()` prima di `fit()` solleva `RuntimeError`. |

### Predict — struttura (4)

| Test | Comportamento verificato |
|---|---|
| `test_predict_returns_dict` | `predict()` restituisce `dict`. |
| `test_predict_keys_match_features` | Le chiavi di `predict()` coincidono con le chiavi di `fit()`. |
| `test_predict_columns_yhat_lower_upper` | Ogni DataFrame ha colonne `["yhat", "yhat_lower", "yhat_upper"]`. |
| `test_predict_horizon_default` | `predict()` senza argomenti produce `horizon_steps=12` righe (da `pipeline_params.yaml`). |

### Predict — correttezza (2)

| Test | Comportamento verificato |
|---|---|
| `test_predict_horizon_override` | `predict(horizon_steps=5)` produce esattamente 5 righe per ogni feature. |
| `test_yhat_lower_leq_yhat_leq_upper` | `yhat_lower ≤ yhat ≤ yhat_upper` per ogni riga e ogni feature (tolleranza `1e-9`). |

### Fallback (1)

| Test | Comportamento verificato |
|---|---|
| `test_fallback_to_prophet_on_short_series` | Con 3 campioni (`< input_window×2=48`), `mem_mb` usa Prophet come fallback e il routing risultante è `"prophet"`. |

### Training set (2)

| Test | Comportamento verificato |
|---|---|
| `test_fit_ignores_anomalous_snapshots` | Con `nominal_snapshots` di 10 righe, `predict()` produce comunque 12 righe (il training set viene filtrato, l'orizzonte no). |
| `test_fit_empty_train_after_nominal_filter_skips_gracefully` | `nominal_snapshots` con timestamp completamente diversi dalla feature: training set vuoto → feature esclusa con warning, non compare in `predict()`. |

### Robustezza (3)
| Test | Comportamento verificato |
|---|---|
| `test_fit_handles_nan_in_training_series` | `fit()` completa senza eccezioni quando il training set contiene NaN; i NaN vengono rimossi (dropna) prima del fitting e la previsione viene prodotta correttamente. |
| `test_linear_predict_interval_monotone` | `yhat_lower ≤ yhat ≤ yhat_upper` per ogni riga del modello linear (tolleranza `1e-9`). |
| `test_infer_freq_us_guard_on_identical_timestamps` | Con tutti i timestamp identici (mediana dei diff = 0), `_infer_freq_us` emette `logger.warning` e restituisce il fallback `5_000_000` µs (5 s). Guard contro frequenza ≤ 0 che causerebbe divisione per zero in `_predict_*`. |

### Override (4)

| Test | Comportamento verificato |
|---|---|
| `test_arima_fit_and_predict` | `model_override={"...cpu_percent": "arima"}` produce previsioni con colonne attese e `yhat_lower ≤ yhat ≤ yhat_upper`. |
| `test_linear_fit_and_predict` | `model_override={"...cpu_percent": "linear"}` produce previsioni con colonne attese. |
| `test_routing_reflects_override` | `get_model_routing()` riflette il `model_override` passato a `fit()`. |
| `test_model_override_invalid_model_name_raises` | `model_override` con nome non valido (`"garch"`) solleva `ValueError` con messaggio descrittivo. |

### Diagnostica ARIMA (1)

| Test | Comportamento verificato |
|---|---|
| `test_arima_ljungbox_warning_on_correlated_residuals` | Serie AR(1)-al-lag-5 (`y[t] = 0.95·y[t-5] + ε`) con `max_p=2, max_d=1, max_q=2` forzati: i residui rimangono autocorrelati (Ljung-Box p ≈ 10⁻⁶²), il warning viene emesso via module-level `logger`. |
