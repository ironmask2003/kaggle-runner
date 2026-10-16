# Sandbox Kaggle per progetti Python

Questa sandbox permette di inviare un progetto Python a Kaggle ed eseguirlo con CPU o GPU, mantenendo la possibilità di eseguire gli stessi script sul computer. Il launcher raccoglie codice, moduli e dati, preserva le cartelle e avvia il file principale con gli argomenti scelti.

La configurazione di ciascun progetto è salvata in un file **TOML**. Il progetto può stare fuori dalla cartella della sandbox: non occorre copiare il launcher o aggiungere import Kaggle agli script.

È un sistema **batch**: invia un job, ne controlla lo stato e scarica i risultati. Non apre una sessione SSH o un notebook Jupyter interattivo. I progetti devono usare dipendenze e percorsi compatibili con il runtime remoto.

## Indice

- [Installazione e accesso a Kaggle](#1-installazione-e-accesso-a-kaggle)
- [Avvio rapido: MultiStyleImages](#2-avvio-rapido-multistyleimages)
- [Configurare un nuovo progetto](#3-configurare-un-nuovo-progetto)
- [Percorsi e directory di esecuzione](#4-percorsi-e-directory-di-esecuzione)
- [Riferimento delle opzioni TOML](#5-riferimento-delle-opzioni-toml)
- [Codice, immagini e dataset](#6-codice-immagini-e-dataset)
- [Dipendenze, Python e GPU](#7-dipendenze-python-e-gpu)
- [Eseguire, ripetere e monitorare i job](#8-eseguire-ripetere-e-monitorare-i-job)
- [Risultati e log](#9-risultati-e-log)
- [Errori e ripresa degli invii](#10-errori-e-ripresa-degli-invii)
- [Limiti di portabilità](#11-limiti-di-portabilità)

## 1. Installazione e accesso a Kaggle

Serve **Python 3.11 o successivo** sul computer. Su macOS/Linux, dalla cartella di questa sandbox:

```bash
cd /Users/lachithaperera/Documents/Notebooks
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
kaggle-sandbox --help
```

Se `.venv` è già installato, per l'uso quotidiano bastano:

```bash
cd /Users/lachithaperera/Documents/Notebooks
source .venv/bin/activate
```

L'installazione `-e .` collega il comando ai sorgenti locali: le modifiche al launcher sono disponibili senza reinstallarlo. Puoi usarlo da qualsiasi directory con il venv attivo. Per installarlo nel venv di un altro progetto:

```bash
python -m pip install /percorso/alla/cartella/Notebooks
```

`python -m sandbox` è equivalente a `kaggle-sandbox`. Su Windows l'attivazione del venv in PowerShell è `.venv\Scripts\Activate.ps1`; gli esempi multilinea seguenti usano la sintassi della shell macOS/Linux.

### Autenticazione

Prima di un invio remoto:

```bash
kaggle auth login
kaggle-sandbox doctor
```

`doctor` verifica che la CLI ufficiale sia disponibile e possa leggere i kernel dell'account. Non garantisce disponibilità GPU o quote sufficienti.

La CLI supporta anche `KAGGLE_API_TOKEN`, `~/.kaggle/access_token` e le credenziali legacy in `~/.kaggle/kaggle.json`. Le credenziali vanno configurate sul computer, **non nel TOML né nei file da caricare**. `owner` è lo username Kaggle, non l'email.

`prepare` e `local` non richiedono autenticazione Kaggle. La prova locale può comunque scaricare dipendenze o modelli se il progetto lo richiede.

## 2. Avvio rapido: MultiStyleImages

La configurazione esistente è `configs/multistyleimages.toml`. Presuppone questa disposizione:

```text
Documents/
├── Notebooks/
│   ├── configs/multistyleimages.toml
│   ├── sandbox/
│   └── runs/
└── MultiStyleImages/
    ├── requirements.txt
    └── src/
        ├── pipeline.py
        ├── segmentation.py
        ├── class_style_describer.py
        ├── prompt_builder.py
        └── test_images/
```

Dalla cartella `Notebooks`, con il venv attivo, avvia una nuova esecuzione GPU:

```bash
kaggle-sandbox run \
  --config configs/multistyleimages.toml \
  --owner lachithaperera \
  --wait
```

Se usi un altro account, sostituisci `lachithaperera` con il tuo username. `--wait` mantiene il terminale in attesa e scarica gli output quando il job termina con successo.

Per una nuova esecuzione CPU:

```bash
kaggle-sandbox run \
  --config configs/multistyleimages.toml \
  --owner lachithaperera \
  --no-gpu --wait
```

Per provarlo sul computer:

```bash
kaggle-sandbox local --config configs/multistyleimages.toml
```

La configurazione contiene:

```toml
[sandbox]
source = "../../MultiStyleImages/src/pipeline.py"
project_root = "../../MultiStyleImages"
requirements = "../../MultiStyleImages/requirements.txt"
cwd = "entrypoint"
name = "multistyleimages"
python = "native"
gpu = true
internet = true
transport = "auto"
runs_dir = "../runs"
exclude = ["src/test_pipeline_*", "src/test_segmentation_output.png"]
```

Questa configurazione riproduce l'esecuzione di `python3 pipeline.py` **dalla cartella `MultiStyleImages/src`**. `cwd = "entrypoint"` permette al programma di trovare `test_images/...` accanto allo script. Vengono inclusi anche gli altri moduli e le immagini; i risultati precedenti indicati in `exclude` vengono esclusi.

Per ripetere la pipeline, ripeti il comando `run`: raccoglierà i file aggiornati e creerà un nuovo run. Non usare `submit` per rilanciare un run già inviato.

## 3. Configurare un nuovo progetto

Per ogni progetto identifica:

1. Il file che avvii normalmente, ad esempio `train.py` oppure `src/pipeline.py`.
2. La cartella da cui lanci quel comando: determina `cwd`.
3. La radice che contiene i moduli e i dati da includere: determina `project_root`.
4. Il file delle dipendenze, gli eventuali dati esterni e gli argomenti del programma.

### Opzione A: TOML dentro il progetto

Per questa struttura:

```text
MioProgetto/
├── sandbox.toml
├── requirements.txt
├── src/
│   ├── train.py
│   └── helpers.py
└── data/
    └── immagini/
```

Crea `MioProgetto/sandbox.toml`:

```toml
[sandbox]
source = "src/train.py"
project_root = "."
requirements = "requirements.txt"
owner = "TUO_USERNAME"
name = "mio-progetto"
cwd = "root"
python = "native"
gpu = true
internet = true
transport = "auto"
runs_dir = "runs"
exclude = ["results", "checkpoints", "*.log"]
# Solo se train.py accetta questi argomenti:
script_args = ["--epochs", "10", "--input", "data/immagini"]
```

Adatta i percorsi e gli argomenti al progetto. Se non esiste un file requirements, ometti `requirements`; se lo script non accetta argomenti, ometti `script_args`. Il launcher non deduce automaticamente le dipendenze dagli import.

Con il venv della sandbox attivo, dalla radice di `MioProgetto`:

```bash
kaggle-sandbox prepare --config sandbox.toml
kaggle-sandbox run --config sandbox.toml --wait
```

Il primo comando è facoltativo e serve per ispezionare il pacchetto offline. Il secondo prepara e invia **un altro run**. Per inviare esattamente il pacchetto già preparato, usa `submit` come descritto nella sezione 8.

### Opzione B: tutti i TOML nella sandbox

Puoi tenere una configurazione per progetto in `Notebooks/configs/`:

```text
Documents/
├── Notebooks/configs/mio-progetto.toml
└── MioProgetto/
    ├── requirements.txt
    └── src/train.py
```

In `configs/mio-progetto.toml` i percorsi diventano:

```toml
[sandbox]
source = "../../MioProgetto/src/train.py"
project_root = "../../MioProgetto"
requirements = "../../MioProgetto/requirements.txt"
owner = "TUO_USERNAME"
name = "mio-progetto"
cwd = "root"
gpu = true
runs_dir = "../runs"
```

Dalla cartella `Notebooks`:

```bash
kaggle-sandbox run --config configs/mio-progetto.toml --wait
```

Il TOML non viene cercato automaticamente: passa sempre `--config`. Puoi omettere `owner` dal file e specificare `--owner TUO_USERNAME` nei comandi `prepare` e `run`.

## 4. Percorsi e directory di esecuzione

Ci sono due momenti diversi: **raccolta dei file sul computer** ed **esecuzione del programma nello snapshot**.

### Percorsi usati per raccogliere i file

- Nel TOML, `source`, `project_root`, `requirements`, `include`, `runs_dir` e l'origine di `mount` sono relativi alla cartella del TOML, oppure possono essere assoluti.
- Nella CLI, gli stessi percorsi sono relativi alla directory del terminale.
- `source` e `requirements` devono stare dentro `project_root`. Senza `project_root`, la radice è la cartella di `source`.
- Gli elementi di `include` sono percorsi di file o cartelle, non glob. I glob si usano in `exclude`.
- Scrivi percorsi espliciti o relativi: il TOML non espande `~`, `$HOME` o altre variabili d'ambiente.

Ad esempio, se il TOML è in `configs/`, `include = ["utils.py"]` indica `configs/utils.py`, non un file relativo a `project_root`.

### Percorsi usati dal programma

| Comando che usi normalmente | Impostazione |
|---|---|
| Dalla radice: `python src/train.py` | `cwd = "root"` |
| Dalla cartella `src`: `python train.py` | `cwd = "entrypoint"` |
| `python train.py` con lo script nella radice | Le due scelte coincidono |

Gli argomenti in `script_args` vengono passati **senza riscriverli**. Quindi `"data/input.png"` viene cercato rispetto al `cwd` scelto. Anche gli output con percorso relativo vengono scritti lì.

La sandbox aggiunge radice e `src/` al percorso degli import Python. Non riscrive i percorsi assoluti presenti nel codice: `/Users/.../foto.png` non esiste su Kaggle. Usa percorsi relativi e includi i dati nel punto atteso dal programma.

## 5. Riferimento delle opzioni TOML

Inserisci le chiavi sotto `[sandbox]`. Stringhe tra virgolette, booleani `true`/`false`, numeri senza virgolette e liste tra parentesi quadre.

| Chiave TOML | Default | Significato |
|---|---|---|
| `source` | Nessuno | File principale `.py` o `.ipynb`; richiesto qui o come argomento CLI. |
| `project_root` | Cartella di `source`, senza raccolta automatica | Se specificato, include ricorsivamente questa cartella. |
| `owner` | Nessuno | Username Kaggle richiesto da `prepare` e `run`; non serve a `local`. |
| `name` | `"sandbox"` | Prefisso del nome del job; viene aggiunto un suffisso univoco. |
| `cwd` | `"root"` | Directory di esecuzione: `"root"` oppure `"entrypoint"`. |
| `requirements` | Nessuno | File da installare con pip prima di eseguire il programma. |
| `python` | `"native"` | `"native"`, `"3.11"`, `"3.12"` o `"3.13"`. |
| `gpu` | `false` | Richiede una GPU su Kaggle. |
| `accelerator` | Nessuno | Tipo di acceleratore, ad esempio `"NvidiaTeslaT4"`; richiede `gpu = true`. |
| `internet` | `true` | Accesso Internet del job Kaggle. |
| `include` | `[]` | File/cartelle aggiuntivi dentro la radice del progetto. |
| `mount` | `[]` | Copie di file/cartelle esterni: `"ORIGINE=DESTINAZIONE"`. |
| `exclude` | `[]` | Glob esclusi dalla raccolta, oltre alle esclusioni integrate. |
| `script_args` | `[]` | Argomenti dello script, uno per elemento; non supportati per notebook. |
| `dataset` | `[]` | Dataset Kaggle esistenti, nel formato `"owner/slug"`. |
| `competition` | `[]` | Slug delle competizioni Kaggle da collegare. |
| `transport` | `"auto"` | `"auto"`, `"inline"` o `"dataset"`; vedi sezione 6. |
| `max_mib` | `512` | Limite positivo del pacchetto locale prima della compressione, in MiB. |
| `timeout` | `7200` | Durata massima richiesta al job Kaggle, in secondi. |
| `runs_dir` | `runs` rispetto al terminale | Directory locale dei run; se impostata nel TOML è relativa al TOML. |

Le opzioni CLI prevalgono sulle impostazioni singole del TOML:

```bash
kaggle-sandbox run --config sandbox.toml --owner ALTRO_USERNAME --no-gpu --wait
```

Le liste invece **si sommano**: `--include`, `--mount`, `--exclude`, `--arg`, `--dataset` e `--competition` aggiungono elementi a quelli salvati. Per sostituire o svuotare una lista, modifica il TOML o usa un altro file di configurazione.

I nomi CLI usano trattini, ad esempio `--project-root`, `--runs-dir`, `--max-mib`; `script_args` corrisponde a `--arg`. Per valori che iniziano con `-`, usa `=`:

```bash
kaggle-sandbox run --config sandbox.toml --arg=--epochs --arg=10 --wait
```

Il launcher esegue Python direttamente: `script_args` non è una riga di shell e non espande pipe, redirect o variabili. Non aggiungere `python3` o il nome dello script in questa lista.

Mantieni `--wait` e `--wait-timeout` nella riga di comando di `run`: non sono opzioni condivise con `prepare` e `local`. `--interval` è disponibile solo nel comando `wait`. Una chiave TOML non riconosciuta per il comando scelto produce un errore.

## 6. Codice, immagini e dataset

### Includere un progetto completo

Con `project_root` vengono raccolti tutti i file ammessi sotto quella cartella, non soltanto quelli individuati negli import. Per esempio, una cartella `data/` dentro la radice viene inclusa automaticamente.

Senza `project_root`, vengono raccolti soltanto `source`, il file `requirements` esplicito e i percorsi `include`/`mount`. Usa questa modalità per pacchetti selettivi. Con `project_root`, `include` non limita la raccolta: per rimuovere file usa `exclude`.

### Aggiungere immagini o dataset esterni

Esempio con un TOML nella radice del progetto:

```toml
[sandbox]
source = "src/train.py"
project_root = "."
owner = "TUO_USERNAME"
cwd = "root"
mount = [
  "../FotoEsperimento=data/images",
  "../etichette.csv=data/labels.csv",
]
```

I dati vengono copiati nello snapshot rispettivamente in `data/images/` e `data/labels.csv`. Il programma può leggerli con gli stessi percorsi relativi sia in locale sia su Kaggle. `mount` non è un collegamento live: modifiche successive ai file originali non cambiano un run già preparato.

La destinazione è sempre relativa alla radice del pacchetto. Se usi `cwd = "entrypoint"` con `source = "src/train.py"` e lo script cerca `test_images/...`, usa una destinazione come `src/test_images`.

Collisioni tra file diversi nella stessa destinazione e percorsi che escono dalla radice vengono rifiutati.

### Esclusioni

```toml
exclude = ["results", "checkpoints", "*.log", "src/test_pipeline_*"]
```

I pattern si applicano ai percorsi di destinazione nel pacchetto o ai loro singoli componenti. Escludere una cartella ne esclude il contenuto. Non escludere l'entrypoint o i requirements richiesti.

Sono già esclusi file/cartelle nascosti, credenziali note, chiavi `.pem`/`.key`, bytecode, `__pycache__`, `venv`, `env`, `node_modules`, `build`, `dist`, cartelle `runs`, directory `.egg-info` e la directory scelta per i run. I symlink nei percorsi visitati vengono rifiutati.

Il launcher non legge `.gitignore` e non rileva segreti scritti dentro codice o configurazioni. La cartella `.venv` locale non viene trasferita.

### Trasporto automatico

Lascia normalmente `transport = "auto"`:

- **Inline:** incorpora il pacchetto solo se il sorgente completo del runner resta sotto 1.000.000 byte, contando bootstrap, configurazione e codifica base64.
- **Dataset:** altrimenti carica il pacchetto come dataset Kaggle privato, attende che sia pronto e lo collega al kernel. Il runner ricostruisce il progetto sotto `/kaggle/working/sandbox_work`.

`transport = "inline"` forza l'incorporazione ma viene rifiutato se supera la soglia. `transport = "dataset"` forza il dataset anche per pacchetti piccoli. Il file compresso usa l'estensione `.payload`; viene estratto dal runner.

Il limite `max_mib` riguarda i file prima della compressione ed è distinto dal limite sul sorgente del kernel. L'archivio viene costruito in memoria: aumentare il limite richiede RAM disponibile sul computer e sul runtime.

Ogni nuovo run con trasporto dataset crea un nuovo dataset privato, con titolo distinto da quello del kernel. **Non è previsto il riuso automatico dei dataset tra nuovi run.** I dataset rimangono nell'account anche dopo il completamento; puoi gestirli dal sito Kaggle. `run.json` ne conserva l'ID in `payload_dataset`.

### Collegare dataset già su Kaggle

```toml
[sandbox]
source = "train.py"
owner = "TUO_USERNAME"
dataset = ["OWNER/DATASET"]
competition = ["COMPETITION_SLUG"]
```

Questi dati sono disponibili sotto `/kaggle/input`, non vengono copiati automaticamente nei percorsi relativi del tuo progetto. Lo script deve leggere il percorso remoto corretto. Per le competizioni serve l'accesso ai dati, inclusa l'accettazione delle regole quando richiesta.

`local` rifiuta `dataset` e `competition`: per la prova locale usa un TOML con file locali e `mount` al loro posto.

## 7. Dipendenze, Python e GPU

### Requirements

Dichiara esplicitamente `requirements = "requirements.txt"` se vuoi installarlo: la sola presenza del file nel progetto non attiva l'installazione. Il runner esegue pip prima del programma, dalla radice dello snapshot.

Vengono installate le dipendenze indicate nel file, non viene copiato il venv del computer. Se i requirements riferiscono altri file locali, includili mantenendo i percorsi. Per riprodurre gli esperimenti, specifica versioni compatibili delle librerie.

### Interprete

- `python = "native"`: usa l'interprete e le librerie dell'ambiente dove avviene l'esecuzione. Su Kaggle è il runtime Kaggle; in locale è l'interprete della sandbox.
- `python = "3.11"`, `"3.12"` o `"3.13"`: usa uv per creare un ambiente temporaneo separato e vi installa i requirements. Non eredita PyTorch e le altre librerie del runtime Kaggle. Il runner usa la struttura Unix del venv per questa modalità.

In locale, con `native`, pip installa nell'interprete attivo: usa un venv dedicato. L'ambiente Python alternativo non cambia il kernel di sistema Kaggle.

### GPU e CPU

```bash
# GPU, tipo scelto da Kaggle
kaggle-sandbox run --config sandbox.toml --gpu --wait

# GPU specifica
kaggle-sandbox run --config sandbox.toml --gpu --accelerator NvidiaTeslaT4 --wait

# CPU
kaggle-sandbox run --config sandbox.toml --no-gpu --wait
```

Se `accelerator` è già nel TOML, rimuovilo per passare a CPU: `--no-gpu` da solo non lo cancella. Quote, disponibilità e autorizzazioni dell'account dipendono da Kaggle.

Richiedere una GPU rende disponibile l'hardware, ma il tuo codice deve usarlo: la sandbox non converte automaticamente operazioni CPU in CUDA. Con `local`, le preferenze GPU Kaggle vengono ignorate e lo script vede le risorse del computer.

### Internet e notebook

Internet è abilitato per default. L'implementazione richiede Internet per requirements, Python alternativo ed esecuzione `.ipynb`; può servire anche al progetto per scaricare pesi o altri dati. `--no-internet` configura il job Kaggle, non blocca la rete del computer locale.

Per un notebook, imposta `source = "notebooks/analisi.ipynb"`. Viene eseguito con nbclient/ipykernel; gli output precedenti sono rimossi dal pacchetto. Il notebook eseguito viene salvato in `sandbox_artifacts/executed.ipynb`, anche parzialmente se una cella fallisce e il runner riesce a salvarlo. `script_args` non è supportato per i notebook.

## 8. Eseguire, ripetere e monitorare i job

### Esecuzione diretta su Kaggle

```bash
kaggle-sandbox run --config sandbox.toml --wait
```

Il comando prepara un nuovo snapshot, carica l'eventuale dataset, invia il kernel e attende i risultati. Senza `--wait` termina dopo l'invio: conserva il percorso stampato per controllare il job in seguito.

### Preparazione offline e invio separato

```bash
kaggle-sandbox prepare --config sandbox.toml
```

Stampa una cartella come `runs/mio-progetto-...`. Per i comandi seguenti, **sostituisci `NOME_RUN` con il nome effettivo**:

```bash
kaggle-sandbox submit runs/NOME_RUN
kaggle-sandbox wait runs/NOME_RUN
```

`prepare` non esegue il tuo programma e non usa rete o credenziali. Puoi ispezionare `run.json` per vedere i file raccolti. `submit` invia quello snapshot: se modifichi gli script dopo `prepare`, devi preparare un nuovo run per includere le modifiche.

### Nuova esecuzione oppure ripresa

| Obiettivo | Comando |
|---|---|
| Ripetere l'esperimento con i file attuali | `kaggle-sandbox run --config sandbox.toml --wait` |
| Inviare un pacchetto ancora nello stato `prepared` | `kaggle-sandbox submit runs/NOME_RUN` |
| Riprendere dopo upload riuscito e attesa dataset fallita | `submit` sullo stesso run in stato `dataset_uploaded` |
| Controllare una volta un job già inviato | `kaggle-sandbox status runs/NOME_RUN` |
| Riprendere l'attesa di un job già inviato | `kaggle-sandbox wait runs/NOME_RUN` |
| Scaricare di nuovo gli output disponibili | `kaggle-sandbox fetch runs/NOME_RUN` |

Ogni `run` crea un job separato: non modifica quello precedente e non lo arresta. Evita invii ripetuti se vuoi soltanto sapere se un job è terminato.

### Esecuzione locale

```bash
kaggle-sandbox local --config sandbox.toml
```

Crea uno snapshot in `runs/local-...` ed esegue il programma lì, senza invii a Kaggle. Gli output relativi non vengono scritti nel progetto originale. Vengono usati gli stessi file, argomenti e `cwd` della configurazione.

### Tempi e interruzioni

```bash
kaggle-sandbox run --config sandbox.toml --timeout 7200 --wait --wait-timeout 10800
kaggle-sandbox wait runs/NOME_RUN --wait-timeout 10800 --interval 30
```

- `--timeout`: durata massima richiesta al job remoto, default 7200 secondi; Kaggle può applicare altri limiti. Non limita il subprocess della modalità `local`.
- `--wait-timeout`: durata dell'attesa nel terminale, default 10800 secondi per la CLI.
- `--interval`: intervallo tra i controlli del comando `wait`, default 30 secondi.

Chiudere il terminale o interrompere il monitoraggio con Ctrl+C **non ferma il job su Kaggle**. Puoi riprendere con `wait`; per fermare il job usa la sua pagina Kaggle. Non è disponibile un comando `cancel` nella sandbox.

## 9. Risultati e log

Con `--wait` o `wait`, al completamento riuscito viene eseguito automaticamente `fetch`. In caso di errore remoto viene tentato il download dei soli log; per gli altri output eventualmente pubblicati usa `fetch`.

```bash
kaggle-sandbox logs runs/NOME_RUN
kaggle-sandbox fetch runs/NOME_RUN
```

La cartella locale contiene, a seconda delle fasi raggiunte:

```text
runs/NOME_RUN/
├── run.json                   # ID remoto, stato locale, configurazione, hash
├── kernel-metadata.json       # Risorse e dataset collegati
├── runner.py                  # Bootstrap inviato a Kaggle
├── dataset/                   # Solo con trasporto dataset
├── dataset-upload.log         # Risposta del caricamento dataset
├── submit.log                 # Conferma invio kernel
├── submit-error.log           # Errori RuntimeError intercettati nell'invio
├── status.log                 # Ultima risposta del controllo stato
├── logs/                      # Download richiesto da logs
└── outputs/                   # Download completo richiesto da fetch/wait
```

Sul runtime, il runner usa:

| Directory | Contenuto |
|---|---|
| `/kaggle/working/sandbox_work` | Progetto estratto e output scritti con percorsi relativi. |
| `/kaggle/working/sandbox_artifacts` | `execution.log`, `result.json`, notebook eseguito e output espliciti. |
| `/kaggle/input` | Dataset collegati al kernel, in sola lettura. |

Nel download cerca `sandbox_work` e `sandbox_artifacts`; il percorso esterno esatto dipende da come Kaggle restituisce gli output. Per `MultiStyleImages`, con `cwd = "entrypoint"`, gli output relativi dello script sono in `sandbox_work/src/`.

In locale trovi direttamente `runs/local-.../sandbox_work/` e `runs/local-.../sandbox_artifacts/`, senza il livello `outputs`.

Puoi continuare a salvare risultati con percorsi relativi nel tuo codice. Se preferisci raccoglierli nella cartella degli artifact, il launcher espone una variabile facoltativa:

```python
import os
from pathlib import Path

output = Path(os.environ.get("SANDBOX_OUTPUT_DIR", "results"))
output.mkdir(parents=True, exist_ok=True)
(output / "metriche.json").write_text('{"accuracy": 0.9}')
```

Il fallback `results` permette di eseguire lo script anche direttamente, senza launcher. I file scritti fuori dall'area di output Kaggle, ad esempio in `/tmp`, non sono raccolti automaticamente.

I log remoti non sono in streaming: Kaggle potrebbe renderli scaricabili solo alla fine. `fetch` non forza la sovrascrittura dei file già scaricati. Conserva la cartella del run per poter usare `status`, `wait` e `fetch`: questi comandi leggono `run.json` e non accettano direttamente un URL Kaggle.

## 10. Errori e ripresa degli invii

### Stati locali

Lo stato `state` in `run.json` descrive l'invio, non l'esito del programma. `submitted` significa che il kernel è stato inviato; per l'esecuzione consulta `status` e il campo `remote_status` aggiornato da quel comando.

| Stato locale | Significato e azione |
|---|---|
| `prepared` | Nessun invio ancora iniziato. Usa `submit`. |
| `uploading_dataset` | Upload iniziato senza conferma locale conclusiva. Controlla il dataset sul sito prima di nuovi invii. |
| `dataset_uploaded` | Dataset caricato; kernel non ancora inviato. `submit` riprende il controllo e poi invia, senza ricaricare il dataset. |
| `submitting` | Tentativo di invio kernel senza conferma locale conclusiva. Controlla il job su Kaggle e gli errori; non azzerare lo stato per forzare un reinvio. |
| `submitted` | Invio confermato. Usa `status`, `wait`, `logs` o `fetch`. |

La sandbox rifiuta `submit` negli stati ambigui per evitare duplicazioni. Un errore di rete non prova che Kaggle non abbia ricevuto la richiesta. Dopo aver chiarito l'esito, per una nuova esecuzione usa `run`.

### Problemi frequenti

| Problema | Cosa verificare |
|---|---|
| `kaggle-sandbox: command not found` | Attiva il venv e installa il progetto con `python -m pip install -e .`. |
| File TOML o script non trovato | Posizione del TOML, regole dei percorsi relativi e nome di `source`. |
| Immagine/dataset non trovato dentro lo script | `cwd`, inclusione dei dati e destinazione di `mount`. |
| `ModuleNotFoundError` | Moduli locali inclusi e dipendenze dichiarate nel file `requirements`. |
| Errore di pip o incompatibilità CUDA | Versioni delle librerie, interprete selezionato, accesso Internet e log di esecuzione. |
| `400` durante `SaveKernel` | Leggi il dettaglio del server in `submit-error.log`. I vecchi runner con immagini incorporate potevano essere troppo grandi; `transport = "auto"` controlla ora la dimensione completa. |
| `403`/`404` subito dopo l'upload dataset | Possono essere transitori: il launcher effettua fino a sei nuovi tentativi. Se persistono, verifica account e permessi. Con stato `dataset_uploaded`, puoi riprendere con `submit`. |
| `409` con titolo già usato da un dataset | I vecchi pacchetti potevano avere titoli uguali. I nuovi pacchetti assegnano al dataset un titolo distinto con suffisso `data`. Leggi comunque il messaggio: non tutti i 409 hanno questa causa. |
| GPU non disponibile | Impostazioni `gpu`/`accelerator`, autorizzazioni e quote dell'account; il launcher non aggira i limiti Kaggle. |
| `wait` scade | Il job può continuare. Riprendi con `wait` sullo stesso run. |
| Nessun log scaricabile mentre il job gira | Controlla la pagina Kaggle; i file potrebbero essere disponibili solo alla fine. |
| Run completato ma risultati assenti | Controlla `execution.log`, i percorsi di salvataggio e gli errori che lo script potrebbe aver gestito senza terminare con codice diverso da zero. |

Il launcher tenta di salvare traceback e stato anche quando lo script fallisce. Un arresto forzato da Kaggle per memoria, quota o timeout può impedire il salvataggio finale.

Codici di uscita principali: `0` successo, `1` errore, `2` attesa scaduta, `130` interruzione. Gli errori sintattici della CLI possono anch'essi terminare con codice `2`.

## 11. Limiti di portabilità

La sandbox preserva il progetto, ma non converte automaticamente:

- percorsi assoluti del computer in percorsi Kaggle;
- applicazioni interattive, richieste `input()` o GUI in job batch;
- dipendenze di sistema o codice specifico di macOS/Windows in codice Linux;
- un progetto che richiede `python -m pacchetto` o comandi shell in un entrypoint equivalente: l'interfaccia corrente esegue un file `.py` o `.ipynb`;
- variabili d'ambiente o credenziali del computer in segreti remoti.

La prova locale è utile per verificare raccolta, import e percorsi, ma non garantisce compatibilità con le librerie e l'hardware Kaggle. Il termine “sandbox” indica qui l'ambiente di lavoro: il launcher **non aggiunge isolamento di sicurezza per codice ostile**.

Per conoscere le opzioni disponibili nella versione installata:

```bash
kaggle-sandbox --help
kaggle-sandbox run --help
kaggle-sandbox local --help
kaggle-sandbox wait --help
```

Riferimenti ufficiali per le funzionalità del servizio: [autenticazione e CLI Kaggle](https://github.com/Kaggle/kaggle-cli/blob/main/docs/README.md), [metadati kernel e acceleratori](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md), [dataset](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md), [comandi kernel](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md).
