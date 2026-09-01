<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VLA-ENGINE banner" width="100%">
</p>

# 👁️ HYDRA-UMC-VLA-ENGINE

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🤖 Framework Multimodale Vision-Language-Action per la Robotica

<p align="left">
  <img src="https://img.shields.io/badge/Licenza-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Modello-OpenVLA%20%2F%20RT--2-orange.svg" alt="VLA">
  <img src="https://img.shields.io/badge/Accelerazione-Hailo--10-green.svg" alt="Hailo-10">
</p>

---

## 1. 🛠️ PANORAMICA TECNICA

**HYDRA-UMC-VLA-ENGINE** è il ponte multimodale che traduce il contesto visivo e il linguaggio naturale in azioni robotiche dirette. Implementa versioni quantizzate di modelli VLA all'avanguardia (come OpenVLA o varianti specializzate RT-2) da eseguire localmente sulla NPU Hailo-10.

Questo motore consente al robot di comprendere comandi come "prendi il componente blu e posizionalo sul vassoio rosso" analizzando il flusso video in diretta e generando la sequenza cinematica corrispondente.

### Caratteristiche principali:
* ✅ **Reale v0 - token di azione e traiettoria:** `action_tokens.py` implementa lo schema di discretizzazione a 256 bin in stile OpenVLA/RT-2 (azione continua <-> token discreto, secondo lo spazio di azione a 7 gradi di libertà - delta di posa + gripper), e `trajectory.py` integra una sequenza di azioni decodificate in una traiettoria di pose assolute. Esposto tramite `tokens encode`/`tokens decode`/`trajectory integrate` più sotto - non serve un modello VLA né una NPU Hailo-10 per eseguirlo o testarlo.
* 📜 **Manifest del modello + validazione dell'output:** Un contratto reale e versionato (`model_manifest.py`) che qualsiasi futura integrazione di modello deve soddisfare - facendo corrispondere la forma azione/vocabolario e una famiglia di chip Hailo nota - oltre alla validazione di forma/confidenza per l'output di inferenza grezzo di un modello. *(implementato)*
* 🩺 **Sottocomando `status` onesto:** Riporta la disponibilità reale di acceleratore/pesi del modello - `no_accelerator`, `no_model_weights`, o `hardware_ready_no_inference` - mai un falso stato "pronto". *(implementato)*
* 🌉 **Controllo semantico (previsto):** Mappatura diretta da pixel e testo a posizioni dei giunti o comandi dello strumento. *(richiede un vero modello VLA - lavoro futuro.)*
* ⚡ **Ragionamento in tempo reale (previsto):** Inferenza accelerata da Hailo-10 per la generazione di azioni a bassa latenza. *(richiede la vera NPU Hailo-10 che questo ambiente non ha.)*
* 🔄 **Generalizzazione Zero-Shot (previsto):** In grado di gestire oggetti mai visti prima basandosi su descrizioni semantiche. *(richiede un vero modello VLA addestrato.)*
* 🛠️ **Pianificazione dei compiti (previsto):** Decompone obiettivi complessi in primitive robotiche atomiche. *(richiede un vero modello VLA.)*
* 👨‍👩‍👧 **Figlio del Cognitive AI Node:** Gira come uno dei quattro
  servizi fratelli sotto [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)
  (insieme a Voice-UI, Semantic-Planner e Docs-QA), condividendo
  l'immagine HydraOS e i pesi dei modelli del padre invece di mantenere
  copie proprie.
* 📦 **Versionamento Contachilometri:** Ogni build reale incrementa
  automaticamente la versione di `pyproject.toml` (`bump_version.py`) -
  nessuna modifica manuale della versione.

---

## 2. 🔄 FLUSSO DI INFERENZA VLA

```mermaid
flowchart LR
    IMG["Frame immagine"] --> VLA["VLA-ENGINE (Hailo-10)"]
    TXT["Istruzione testuale"] --> VLA
    VLA --> ACTION["Token di azione"]
    ACTION --> TRAJ["Generatore di traiettoria"]
    TRAJ --> MOTOR["Comandi motore"]
```

---

## 3. 🧱 ARCHITETTURA E DECISIONI DI PROGETTAZIONE

Questo repository è un **figlio** della famiglia Cognitive AI Node - il
suo padre, [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE),
possiede l'immagine HydraOS condivisa e i pesi dei modelli quantizzati, e
collega questo servizio nel suo `docker-compose.yml` insieme ai suoi tre
fratelli (Voice-UI, Semantic-Planner, Docs-QA):

* **Perché questo figlio non ha hardware/firmware/`os/`/`models/`
  propri.** Gira interamente sul modulo CM5 + Hailo-10 M.2 già posseduto
  dal padre - centralizzare i pesi dei modelli e l'immagine HydraOS in un
  unico posto evita quattro copie divergenti di più gigabyte all'interno
  della famiglia.
* **Perché una struttura `src/`.** Mantiene il pacchetto installabile
  (`hydra_umc_vla_engine`) separato dal tooling nella radice del repo
  (`bump_version.py`), coerentemente con il resto dei progetti Python
  dell'ecosistema.
* **Perché la tokenizzazione delle azioni arriva prima dell'inferenza del modello.**
  Trasformare un'azione continua in token discreti (e viceversa) è
  matematica fissa definita dai limiti dello spazio di azione e dalla
  dimensione del vocabolario - non serve un modello VLA né una NPU
  Hailo-10 per scriverla o testarla, quindi v0 consegna prima questo
  pezzo (`action_tokens.py`, `trajectory.py`). La vera inferenza VLA
  richiede i pesi del modello e l'hardware Hailo-10 che questo ambiente
  non ha, e arriverà più avanti.
* **Come si inserisce nel resto dell'ecosistema.** Questo motore
  converte la percezione grezza (frame della camera, concettualmente
  inoltrati da HYDRA-UMC-VISION-NODE a monte) e le istruzioni in
  linguaggio naturale in token di azione che il suo fratello
  HYDRA-UMC-SEMANTIC-PLANNER trasforma in decisioni di missione per
  HYDRA-UMC-ORCHESTRATOR.
* **Perché `model_manifest.py` non nomina una variante specifica di
  OpenVLA/RT-2.** Nessun modello è stato ancora effettivamente scelto
  (vedi la Roadmap di questo stesso README) - `EXPECTED_MODEL_MANIFEST`
  è onestamente un contratto di forma/target derivato direttamente
  dalle costanti reali di `action_tokens.py`, non un loader per un
  modello che non esiste. `hailo_arch` riutilizza lo stesso insieme
  reale e chiuso di famiglie di chip che `HYDRA-UMC-DETECTION-HEF` già
  usa per validare il proprio registro dei modelli.
* **Perché `status` riporta `hardware_ready_no_inference` invece di
  "pronto".** Anche quando un vero dispositivo Hailo-10 e i veri pesi
  del modello sono entrambi presenti, questo v0 non ha ancora codice di
  inferenza reale - dichiararsi pronto a quel punto sarebbe una vera
  bugia su una capacità che non esiste ancora. `determine_mode()` di
  `hardware.py` controlla prima l'acceleratore (un controllo economico
  del nodo dispositivo) prima dei pesi del modello, lo stesso ordine
  precondizione-più-economica-prima già usato da `safe_load()` di
  `HYDRA-UMC-DETECTION-HEF`.
* **Perché `model_weights_available()` controlla il `models/` del
  padre, non uno locale.** Questo figlio non ha un proprio `models/`
  (potato - vedi il punto sopra) - i veri pesi condivisi risiedono nel
  `models/` del padre `HYDRA-UMC-COGNITIVE-NODE`, un livello di
  workspace fratello più in alto, la stessa directory reale che
  `check_shared_models()` di quel repository già controlla.

---

## 📂 STRUTTURA DELLE CARTELLE

```text
HYDRA-UMC-VLA-ENGINE/
├── src/hydra_umc_vla_engine/   # Codice sorgente
│   ├── action_tokens.py        # Discretizzazione azione <-> token (stile OpenVLA/RT-2)
│   ├── trajectory.py           # Integrazione sequenza di azioni -> traiettoria di pose
│   ├── model_manifest.py       # Contratto reale di forma del modello + validazione output di inferenza
│   ├── hardware.py             # Sonde reali di disponibilità acceleratore/pesi del modello
│   └── main.py                 # Entry point CLI (invocazione nuda + `tokens`/`trajectory`/`status`)
├── tests/                      # Suite pytest reale (action_tokens, trajectory, manifest, hardware, CLI)
├── docs/                       # Documentazione e benchmark
├── images/                     # Media e diagrammi
├── scripts/                    # Script di utilità
├── build/                      # Output di build locale (ignorato da git)
├── pyproject.toml              # Metadati del pacchetto (versione a incremento contachilometri)
├── bump_version.py             # Incremento versione stile contachilometri (usato da build.sh/.bat)
├── build.sh / build.bat        # Crea il venv, installa (con extra dev), verifica l'import, esegue i test
└── run.sh / run.bat            # Esegue il punto di ingresso
```

> **Nota:** `hardware/` e `firmware/` sono stati potati - questo nodo
> funziona su un modulo CM5 + Hailo-10 M.2 già esistente, senza un
> progetto hardware/firmware proprio. Sono stati potati anche `os/` e
> `models/` - l'immagine HydraOS e i pesi dei modelli Hailo-10 condivisi
> risiedono nel progetto padre `HYDRA-UMC-COGNITIVE-NODE`, a cui questo
> progetto si collega come servizio (vedi il suo `docker-compose.yml`).

---

## ⚙️ BUILD ED ESECUZIONE

Richiede Python >= 3.10.

```bash
# Linux / macOS / Git Bash
./build.sh   # crea .venv, installa il pacchetto (editable, con extra
             # dev), verifica l'import, esegue la suite di test reale
./run.sh     # esegue il punto di ingresso

# Windows (cmd)
build.bat
run.bat
```

`build.sh`/`build.bat` incrementano la versione (stile contachilometri,
vedi `bump_version.py`) prima di ogni build reale. Output atteso di
`run.sh` (invocazione nuda):

```text
HYDRA-UMC-VLA-ENGINE v0.0.4
Vision-Language-Action engine (Hailo-10) - translates camera frames and text instructions into robotic action sequences.
```

Esempio reale - codificare un'azione in token, decodificarla, e integrare una breve sequenza di azioni in una traiettoria:

```bash
./run.sh tokens encode --action "0.02,-0.03,0.01,0.05,-0.04,0.02,0.7"
# 179,51,153,192,76,153,179

./run.sh tokens decode --tokens "179,51,153,192,76,153,179"
# 0.020117,-0.030273,0.005273,0.050977,-0.037891,0.019922,0.699219

./run.sh trajectory integrate --start "0,0,0,0,0,0" --actions actions.json
# step 0: x=0.000000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.000000
# step 1: x=0.010000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.500000
# step 2: x=0.010000 y=0.010000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=1.000000
```

`status` riporta la disponibilità reale e onesta di acceleratore/pesi del
modello - mai un falso stato "pronto":

```text
$ ./run.sh status
accelerator (Hailo-10):    MISSING
model weights (parent):    MISSING
mode: no_accelerator - no Hailo-10 NPU device node on this machine - real inference cannot run here.
```

### 🩺 Risoluzione dei problemi

* **`python: comando non trovato` / il build fallisce al passo 1.**
  Richiede Python >= 3.10 nel `PATH`. Su Windows, installalo da
  [python.org](https://python.org) e spunta "Add to PATH" durante
  l'installazione; su Linux/macOS di solito si chiama `python3`.
* **`build.sh` non riesce ad attivare il venv.** `python3 -m venv .venv`
  posiziona lo script di attivazione in un percorso diverso a seconda
  della piattaforma: `.venv/bin/activate` su Linux/macOS,
  `.venv/Scripts/activate` su Windows (anche per un venv Python Windows
  usato da Git Bash). `build.sh` verifica già entrambi i percorsi - se
  continua a fallire, elimina `.venv/` e riesegui `./build.sh` per
  ricrearlo da zero.
* **`pip install -e .` fallisce.** Di solito per un `.venv/` obsoleto.
  Elimina la cartella `.venv/` e riesegui `./build.sh`/`build.bat` per
  ricrearla.
* **`import OK` non viene mai stampato.** Significa che `python -c
  "import hydra_umc_vla_engine"` è fallito - riesegui con il venv attivo
  per vedere il traceback reale.

---

## ✅ Stato Attuale e Prossimi Passi

**Reale oggi:** la codifica/decodifica dei token di azione e la generazione di traiettoria (`action_tokens.py`, `trajectory.py`) - i passaggi "Token di azione" e "Generatore di traiettoria" del diagramma di flusso sopra - con 19 test e una CLI reale.

**Ancora da fare, e bloccato da vero hardware/pesi del modello:** la vera inferenza del modello VLA (OpenVLA/RT-2 quantizzato per Hailo-10) che produrrebbe i token che questo v0 sa già decodificare.

---

## 🚀 TABELLA DI MARCIA
* **Fase 1:** Distribuzione del motore VLA e elaborazione dell'input multi-modale su Hailo-10.
* **Fase 2:** Integrazione del pianificatore semantico con modelli comportamentali di sciame e memoria a lungo termine.
* **Fase 3:** Esecuzione locale a bassa latenza dell'interfaccia vocale e cancellazione del rumore industriale.
* **Fase 4:** Supporto per la generazione di azioni coordinate a doppio braccio e audit del processo decisionale autonomo.

---

## 🔗 PROGETTI CORRELATI

Questo progetto fa parte di un ecosistema robotico più ampio dello stesso autore (JuanenRac / Electro Hobby 3D), che copre firmware, software di controllo, nodi AI e strumenti di flotta.

### Famiglia

**Genitore:** **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — l'Hub di Integrazione che possiede l'immagine/i pesi HydraOS condivisi di questo motore e lo collega al flusso cognitivo.

**Fratelli:**
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — gateway STT/TTS per lo stesso planner che questo motore alimenta anch'esso.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — il planner LLM alimentato dai token di azione di questo motore.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — assistente RAG che fonda lo stesso planner su manuali tecnici.

Questo motore non ha relazioni al di fuori della propria famiglia oltre a quanto già coperto sopra.

### Resto dell'ecosistema

**Piattaforma HYDRA-UMC** — la micro-fabbrica multi-robot
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — la scheda madre stessa: host Raspberry Pi CM5 + coprocessore real-time STM32H745 dual-core, che orchestra fino a 8 bracci robotici distribuiti via CAN-OTA/SPI-OTA.
- **[HYDRA-UMC SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — backend Express/WebSocket headless che possiede lo stato dei robot.
- **[HYDRA-UMC STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app Android di controllo per HYDRA-UMC.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app iOS/iPadOS di controllo per HYDRA-UMC.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro di comando desktop per lo sciame.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creatore/editor grafico desktop per modelli URDF.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — UI touch nativa per HYDRA-UMC.

**Piattaforma URTC** — il controller della testa utensile che ogni braccio HYDRA-UMC porta
- **[URTC](https://github.com/JuanenRac/URTC)** — Universal Robot Tool Controller, firmware.
- **[URTC Flasher](https://github.com/JuanenRac/URTC-FLASHER)** — strumento desktop di flashing CAN-OTA + SWD/JTAG.
- **[URTC Tester](https://github.com/JuanenRac/URTC-TESTER)** — strumento desktop di diagnostica CAN live.
- **[URTC Web Studio](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basata su browser ai 2 strumenti desktop sopra.

**👁️ Nodo di Visione IA (Hailo-8)**
- [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)
- [HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)
- [HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)
- [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)
- [HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)

**🐝 Orchestrazione e Sciame**
- [HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)
- [HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)
- [HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)
- [HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)
- [HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)

**🎮 Gemello Digitale e Simulazione**
- [HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)
- [HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)
- [HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)
- [HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)

**📊 Dati e Analisi**
- [HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)
- [HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)
- [HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)
- [HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)

**🏭 Gateway Industriale**
- [HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)
- [HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)
- [HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)
- [HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)

**🛠️ Strumenti Complementari**
- [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)
- [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)
- [HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)
- [HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)
- [HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)

---

## 👤 AUTORE
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENZA
GPL-3.0 - Vedere LICENSE per i dettagli.
