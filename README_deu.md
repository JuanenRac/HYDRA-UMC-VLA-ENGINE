<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VLA-ENGINE banner" width="100%">
</p>

# 👁️ HYDRA-UMC-VLA-ENGINE

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | 🇩🇪 <b>Deutsch</b> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🤖 Multimodales Vision-Language-Action Framework für Robotik

<p align="left">
  <img src="https://img.shields.io/badge/Lizenz-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Modell-OpenVLA%20%2F%20RT--2-orange.svg" alt="VLA">
  <img src="https://img.shields.io/badge/Beschleunigung-Hailo--10-green.svg" alt="Hailo-10">
</p>

---

## 1. 🛠️ TECHNISCHER ÜBERBLICK

**HYDRA-UMC-VLA-ENGINE** ist die multimodale Brücke, die visuellen Kontext und natürliche Sprache in direkte Roboteraktionen übersetzt. Es implementiert quantisierte Versionen modernster VLA-Modelle (wie OpenVLA oder spezialisierte RT-2-Varianten), um lokal auf der Hailo-10 NPU zu laufen.

Diese Engine ermöglicht es dem Roboter, Befehle wie "nimm die blaue Komponente und lege sie auf das rote Tablett" zu verstehen, indem er den Live-Kamera-Feed analysiert und die entsprechende kinematische Sequenz generiert.

### Hauptmerkmale:
* ✅ **Echtes v0 - Aktions-Token & Trajektorie:** `action_tokens.py` implementiert das OpenVLA/RT-2-artige 256-Bin-Diskretisierungsschema (kontinuierliche Aktion <-> diskretes Token, gemäß dem 7-Freiheitsgrad-Aktionsraum - Pose-Delta + Greifer), und `trajectory.py` integriert eine dekodierte Aktionssequenz zu einer absoluten Posen-Trajektorie. Über `tokens encode`/`tokens decode`/`trajectory integrate` unten verfügbar - kein VLA-Modell oder Hailo-10-NPU nötig, um es auszuführen oder zu testen.
* 📜 **Modell-Manifest + Ausgabevalidierung:** Ein echter, versionierter Vertrag (`model_manifest.py`), den jede zukünftige Modellintegration erfüllen muss - passende Aktions-/Vokabularform und eine bekannte Hailo-Chipfamilie - plus Form-/Konfidenzvalidierung für die rohe Inferenzausgabe eines Modells. *(implementiert)*
* 🔌 **HailoRT-Integrationsgrenze, dem Modul vorausgehend vorbereitet:** `hailo_runtime.py` ist gegen die echte, bestätigte `hailo_platform`-API (`VDevice`, `HEF`, `ConfigureParams`, `InputVStreamParams`/`OutputVStreamParams`) geschrieben - lazy importiert, sodass dieses Repository ohne installiertes `hailort`-Paket oder vorhandenes Hailo-10-Modul sauber installiert/getestet wird, und `hailo_output_to_tokens()` (der Teil, der ein echtes Inferenzergebnis auf den eigenen Token-Vertrag dieser Engine abbildet) ist heute vollständig unit-getestet. *(implementiert, nur Integrationsgrenze - siehe unten)*
* 🩺 **Ehrlicher `status`-Subbefehl:** Meldet die tatsächliche Verfügbarkeit von Beschleuniger/Modellgewichten - `no_accelerator`, `no_model_weights`, oder `hardware_ready_no_inference` - niemals einen falschen "bereit"-Zustand. *(implementiert)*
* 🌉 **Semantische Steuerung (geplant):** Direktes Mapping von Pixeln und Text auf Gelenkpositionen oder Werkzeugbefehle. *(benötigt ein echtes VLA-Modell - zukünftige Arbeit.)*
* ⚡ **Echtzeit-Denken (geplant):** Hailo-10 beschleunigte Inferenz für die Aktionsgenerierung mit niedriger Latenz. *(benötigt die echte Hailo-10-NPU, die diese Umgebung nicht hat.)*
* 🔄 **Zero-Shot-Generalisierung (geplant):** Fähigkeit, ungesehene Objekte basierend auf semantischen Beschreibungen zu handhaben. *(benötigt ein echtes trainiertes VLA-Modell.)*
* 🛠️ **Aufgabenplanung (geplant):** Zerlegt komplexe Ziele in atomare Roboter-Primitive. *(benötigt ein echtes VLA-Modell.)*
* 👨‍👩‍👧 **Kind des Cognitive AI Node:** Läuft als einer von vier
  Schwesterdiensten unter [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)
  (neben Voice-UI, Semantic-Planner und Docs-QA) und teilt sich das
  HydraOS-Image und die Modellgewichte des Elternteils, statt eigene
  Kopien vorzuhalten.
* 📦 **Kilometerzähler-Versionierung:** Jeder echte Build erhöht
  automatisch die Version in `pyproject.toml` (`bump_version.py`) - keine
  manuellen Versionsänderungen.

---

## 2. 🔄 VLA-INFERENZABLAUF

```mermaid
flowchart LR
    IMG["Bild-Frame"] --> VLA["VLA-ENGINE (Hailo-10)"]
    TXT["Textanweisung"] --> VLA
    VLA --> ACTION["Aktions-Token"]
    ACTION --> TRAJ["Trajektoriengenerator"]
    TRAJ --> MOTOR["Motorbefehle"]
```

---

## 3. 🧱 ARCHITEKTUR & DESIGNENTSCHEIDUNGEN

Dieses Repository ist ein **Kind** der Cognitive AI Node-Familie - sein
Elternteil, [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE),
besitzt das gemeinsam genutzte HydraOS-Image und die quantisierten
Modellgewichte und bindet diesen Dienst in seiner `docker-compose.yml`
neben seinen drei Geschwistern (Voice-UI, Semantic-Planner, Docs-QA) ein:

* **Warum dieses Kind keine eigene Hardware/Firmware/`os/`/`models/`
  hat.** Es läuft vollständig auf dem CM5 + Hailo-10 M.2-Modul, das
  bereits dem Elternteil gehört - Modellgewichte und HydraOS-Image an
  einer zentralen Stelle zu halten vermeidet vier abweichende, mehrere
  Gigabyte große Kopien innerhalb der Familie.
* **Warum ein `src/`-Layout.** Trennt das installierbare Paket
  (`hydra_umc_vla_engine`) vom Tooling im Repo-Root (`bump_version.py`)
  und entspricht dem Layout aller anderen Python-Projekte im Ökosystem.
* **Warum die Aktions-Tokenisierung vor der Modellinferenz kommt.**
  Eine kontinuierliche Aktion in diskrete Token umzuwandeln (und
  zurück) ist feste Mathematik, definiert durch die Grenzen des
  Aktionsraums und die Vokabulargröße - dafür braucht es weder ein
  VLA-Modell noch eine Hailo-10-NPU zum Schreiben oder Testen, daher
  liefert v0 dieses Stück (`action_tokens.py`, `trajectory.py`) zuerst.
  Die echte VLA-Inferenz benötigt die Modellgewichte und die
  Hailo-10-Hardware, die diese Umgebung nicht hat, und folgt später.
* **Warum `hailo_runtime.py` `hailo_platform` lazy importiert, innerhalb nur zweier Funktionen.** `hailort` ist nicht auf PyPI und nicht auf dieser Entwicklungsmaschine installiert - es beim Modul-Laden zu importieren würde dazu führen, dass dieses gesamte Paket überall außer auf einer Maschine mit einem echten angeschlossenen Hailo-Modul nicht installiert/importiert werden könnte. Nur `open_vdevice()` und `load_hailo_vla_model()` (die beiden Funktionen, die wirklich echtes HailoRT brauchen) importieren es, und zwar lazy; beide werfen einen klaren `HailoNotAvailableError` statt eines bloßen `ImportError`, wenn es fehlt. Dasselbe Muster, das dieses Ökosystem bereits für jeden anderen echten Hardware-Transport verwendet (GRBL seriell, MAVLink, SPI-OTA, ...).
* **Wie sich das in den Rest des Ökosystems einfügt.** Diese Engine
  wandelt rohe Wahrnehmung (Kameraframes, konzeptionell von
  HYDRA-UMC-VISION-NODE vorgelagert weitergeleitet) und
  Sprachanweisungen in Aktions-Token um, die ihr Geschwister
  HYDRA-UMC-SEMANTIC-PLANNER in Missionsentscheidungen für
  HYDRA-UMC-ORCHESTRATOR umwandelt.
* **Warum `model_manifest.py` keine bestimmte OpenVLA/RT-2-Variante
  benennt.** Es wurde noch tatsächlich kein Modell ausgewählt (siehe die
  Roadmap dieses READMEs) - `EXPECTED_MODEL_MANIFEST` ist ehrlich gesagt
  ein Form-/Ziel-Vertrag, der direkt aus den echten Konstanten von
  `action_tokens.py` abgeleitet ist, kein Loader für ein Modell, das
  nicht existiert. `hailo_arch` verwendet dieselbe echte, geschlossene
  Menge an Chip-Familien wieder, gegen die `HYDRA-UMC-DETECTION-HEF`
  bereits sein eigenes Modellregister validiert.
* **Warum `status` `hardware_ready_no_inference` statt "bereit" meldet.**
  Selbst wenn ein echtes Hailo-10-Gerät und echte Modellgewichte beide
  vorhanden sind, hat dieses v0 immer noch keinen echten Inferenzcode -
  an diesem Punkt Bereitschaft zu behaupten wäre eine echte Lüge über
  eine Fähigkeit, die noch nicht existiert. `determine_mode()` in
  `hardware.py` prüft zuerst den Beschleuniger (eine günstige
  Geräteknoten-Prüfung), bevor es die Modellgewichte prüft - dieselbe
  Reihenfolge "billigste Voraussetzung zuerst", die `safe_load()` von
  `HYDRA-UMC-DETECTION-HEF` bereits verwendet.
* **Warum `model_weights_available()` das `models/` des Elternteils
  prüft, nicht ein lokales.** Dieses Kind hat kein eigenes `models/`
  (entfernt - siehe den Punkt oben) - die echten gemeinsamen Gewichte
  liegen im eigenen `models/` des Elternteils
  `HYDRA-UMC-COGNITIVE-NODE`, eine Geschwister-Workspace-Ebene höher,
  dasselbe echte Verzeichnis, das `check_shared_models()` dieses Repos
  bereits prüft.

---

## 📂 VERZEICHNISSTRUKTUR

```text
HYDRA-UMC-VLA-ENGINE/
├── src/hydra_umc_vla_engine/   # Quellcode
│   ├── action_tokens.py        # Aktion <-> Token Diskretisierung (OpenVLA/RT-2-Stil)
│   ├── trajectory.py           # Aktionssequenz -> Posen-Trajektorie Integration
│   ├── model_manifest.py       # Echter Modellformvertrag + Inferenzausgabe-Validierung
│   ├── hardware.py             # Echte Beschleuniger-/Modellgewicht-Verfügbarkeitsprüfungen
│   ├── hailo_runtime.py        # Echte HailoRT-Integrationsgrenze (hailo_platform), lazy importiert
│   ├── api.py                  # Einfache JSON/HTTP-Oberfläche (stdlib http.server) über tokens/trajectory/status
│   └── main.py                 # CLI-Einstiegspunkt (nackter Aufruf + `tokens`/`trajectory`/`status`)
├── tests/                      # Echte pytest-Suite (action_tokens, trajectory, manifest, hardware, hailo_runtime, api, CLI)
├── docs/                       # Dokumentation und Benchmarks
├── images/                     # Medien und Diagramme
├── systemd/
│   └── hydra-umc-vla-engine.service  # systemd-Unit der lokalen CM5-API für Tokenisierung/Trajektorie
├── build/                      # Lokale Build-Ausgabe (von git ignoriert)
├── pyproject.toml              # Paket-Metadaten (Kilometerzähler-Version)
├── bump_version.py             # Native Versionserhöhung im Kilometerzähler-Stil (von build.sh/.bat verwendet)
├── bump_manifest_version.py    # Synchronisiert die Version von hydra-umc.project.json mit der nativen (--sync)
├── build.sh / build.bat        # Erstellt das venv, installiert (mit dev-Extras), prüft den Import, führt Tests aus
└── run.sh / run.bat            # Führt den Einstiegspunkt aus
```

> **Hinweis:** `hardware/` und `firmware/` wurden entfernt - dieser Knoten
> läuft auf einem bereits vorhandenen CM5 + Hailo-10 M.2 Modul ohne
> eigenes Hardware-/Firmware-Design. Auch `os/` und `models/` wurden
> entfernt - das HydraOS-Image und die gemeinsam genutzten
> Hailo-10-Modellgewichte befinden sich im übergeordneten Projekt
> `HYDRA-UMC-COGNITIVE-NODE`, an das dieses Projekt als Dienst angebunden
> wird (siehe dessen `docker-compose.yml`).

---

## ⚙️ BUILD UND AUSFÜHRUNG

Erfordert Python >= 3.10.

```bash
# Linux / macOS / Git Bash
./build.sh   # erstellt .venv, installiert das Paket (editable, mit
             # dev-Extras), prüft den Import, führt die echte Test-Suite aus
./run.sh     # führt den Einstiegspunkt aus

# Windows (cmd)
build.bat
run.bat
```

`build.sh`/`build.bat` erhöhen die Version (Kilometerzähler-Stil, siehe
`bump_version.py`) vor jedem echten Build. Erwartete Ausgabe von `run.sh`
(nackter Aufruf):

```text
HYDRA-UMC-VLA-ENGINE v0.1.0
Vision-Language-Action engine (Hailo-10) - translates camera frames and text instructions into robotic action sequences.
```

Echtes Beispiel - eine Aktion in Token kodieren, zurück dekodieren, und eine kurze Aktionssequenz zu einer Trajektorie integrieren:

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

`status` meldet die echte, ehrliche Verfügbarkeit von
Beschleuniger/Modellgewichten - niemals einen falschen "bereit"-Zustand:

```text
$ ./run.sh status
accelerator (Hailo-10):    MISSING
model weights (parent):    MISSING
mode: no_accelerator - no Hailo-10 NPU device node on this machine - real inference cannot run here.
```

### 🩺 Fehlerbehebung

* **`python: Befehl nicht gefunden` / der Build schlägt bei Schritt 1
  fehl.** Erfordert Python >= 3.10 im `PATH`. Unter Windows von
  [python.org](https://python.org) installieren und bei der Installation
  "Add to PATH" ankreuzen; unter Linux/macOS heißt es meist `python3`.
* **`build.sh` kann das venv nicht aktivieren.** `python3 -m venv .venv`
  legt das Aktivierungsskript je nach Plattform an anderer Stelle ab:
  `.venv/bin/activate` unter Linux/macOS, `.venv/Scripts/activate` unter
  Windows (auch bei einem Windows-Python-venv, das aus Git Bash heraus
  verwendet wird). `build.sh` prüft bereits beide Pfade - schlägt es
  weiterhin fehl, `.venv/` löschen und `./build.sh` erneut ausführen, um
  es von Grund auf neu zu erstellen.
* **`pip install -e .` schlägt fehl.** Meist wegen eines veralteten
  `.venv/`. Den Ordner `.venv/` löschen und `./build.sh`/`build.bat`
  erneut ausführen, um ihn neu zu erstellen.
* **`import OK` erscheint nie.** Bedeutet, dass `python -c "import
  hydra_umc_vla_engine"` selbst fehlgeschlagen ist - mit aktivem venv
  erneut ausführen, um den echten Traceback zu sehen.

---

## ✅ Aktueller Status & Nächste Schritte

**Heute real:** die Aktions-Token-Kodierung/-Dekodierung und die Trajektoriengenerierung (`action_tokens.py`, `trajectory.py`) - die Schritte "Aktions-Token" und "Trajektoriengenerator" im obigen Ablaufdiagramm - plus eine echte HailoRT-Integrationsgrenze (`hailo_runtime.py`), bereit für ein echtes `.hef`-Modell und ein Hailo-10-Modul, sobald diese existieren. 64 Tests und eine echte CLI.

**Noch offen, und blockiert durch echte Hardware/ein echtes Modell:** tatsächlich Inferenz auszuführen braucht ein echtes, kompiliertes VLA-`.hef`-Modell (OpenVLA/RT-2 quantisiert für Hailo-10 - noch kein konkretes Modell gewählt) und ein angeschlossenes physisches Hailo-10-Modul, beides echte, unvermeidliche Blocker, die `hailo_runtime.py` allein nicht beseitigen kann - aber ein Modell zu laden und zu dekodieren, sobald es existiert, ist kein ungeschriebener Code mehr.

---

## 🚀 FAHRPLAN
* **Phase 1:** VLA-Engine-Bereitstellung und multimodale Eingabeverarbeitung auf Hailo-10.
* **Phase 2:** Integration des semantischen Planers mit Schwarmverhaltensmodellen und Langzeitgedächtnis.
* **Phase 3:** Lokale Ausführung der Voice-UI mit niedriger Latenz und industrielle Geräuschunterdrückung.
* **Phase 4:** Unterstützung für die Generierung koordinierter Aktionen mit zwei Armen und Audits zur autonomen Entscheidungsfindung.

---

## 🔗 Verwandte Projekte

Dieses Projekt ist Teil des HYDRA-UMC-Robotik-Ökosystems desselben Autors (JuanenRac / Electro Hobby 3D). Gut zu wissen, da eine Anfrage eigentlich eines dieser Projekte betreffen könnte statt dieses Repositorys.

**Übergeordnetes Projekt**
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Integrationsknoten für die Hailo-10-Cognitive-Pipeline (LLM-/VLA-/Sprach-Orchestrierung); das übergeordnete Projekt, dessen spezifische Stufe bzw. Verbraucher dieses Repository innerhalb seiner eigenen Cognitive-Pipeline ist.

**Geschwisterprojekte** — die übrigen Stufen/Verbraucher der eigenen Hailo-10-Cognitive-Pipeline von HYDRA-UMC-COGNITIVE-NODE
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — echtes Sprach-Frontend (VAD + Intent-Parser) mit einem begrenzten, bestätigungsgesicherten Watch-Relay.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — echte regelbasierte Aufgabenzerlegung und semantische Fehlerbehebung über MCU-Fehlercodes.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — echte, nur auf der Standardbibliothek basierende TF-IDF-Dokumentensuche über die eigenen Markdown-Dokumente dieses Ökosystems.

**Ebenfalls Teil des Ökosystems**

*Kern-Hardware & Plattform*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — das physische Motherboard des Roboterarms: CM5-Host + Dual-Core-STM32H745, koordiniert bis zu 8 Werkzeugarme über CAN-OTA/SPI-OTA.
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — reproduzierbare Raspberry-Pi-OS-Produktschicht für den CM5: schreibgeschützter Agent, validierte Konfiguration/Profile, WiFi-Ersteinrichtung.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — der gemeinsame JSON-Schema-Vertrag und die Sicherheitsschranke, gegen die jede Bridge ihre Befehle validiert.

*Kern-Backend & Clients*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — das reale Headless-Backend (REST/WebSocket), mit dem jeder Steuerungsclient tatsächlich spricht.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — Web-Steuerungs-Dashboard mit Echtzeit-3D-Visualisierung mehrerer Roboter.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — Desktop-Schwarmleitstand (PySide6) für mehrere Server gleichzeitig, verpackt als eigenständige ausführbare Datei.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — native Android-Steuerungs-App mit biometrischem Login und einer gekoppelten Wear-OS-Begleit-App.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — iOS/iPadOS-Steuerungs-App (Flutter) mit Echtzeit-WebSocket-Synchronisierung.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — native Touch-UI für das eingebaute 7"-DSI-Touchscreen, direkt auf dem CM5 eingebettet.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — grafischer Desktop-URDF-Ersteller/-Editor, der fertige Modelle in STUDIOs eigenen Katalog überträgt.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — Koordinationsschranke für AGV-/AMR-Flotten über einen echten VDA-5050-MQTT-Publisher.
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — High-Level-Koordinator für CNC-Zellen mit echtem GRBL-Status-/Steuerbyte-Zugriff.
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — Koordinationsschranke für laufende/humanoide Droiden, mit einem echten Boston-Dynamics-Spot-Befehlssender.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — Sicherheitskoordinator für Laserzellen, liest 3 echte Schlüssel-/Gehäuse-/Verriegelungs-GPIO-Sicherungen.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — sicherer High-Level-Koordinator für den Leiterplattenfluss von OpenPnP Pick-and-Place.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — sichere Koordinationsschranke für Moonraker/Klipper-3D-Drucker, mit echten gesicherten Job-Befehlen.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — Sicherheitskoordinator mit einem echten, träge importierten rclpy-ROS-2-Transport.
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — Koordinationsschranke für kameraausgestattete UAVs, mit einem echten MAVLink-Befehlssender.

*URTC-Werkzeugplattform*
- **[URTC](https://github.com/JuanenRac/URTC)** — Firmware für die physische Universal-Robot-Tool-Controller-Platine, 25+ Werkzeugprofile über CAN-Bus.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — Desktop-GUI-Flash-Tool für URTC-Platinen, CAN-OTA plus Full-Chip-SWD/JTAG.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — Desktop-Live-CAN-Bus-Diagnosetool für URTC-Platinen, ein Panel pro Werkzeugprofil.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — browserbasierte Alternative zu URTC-TESTER über die Web-Serial-API, ohne lokale Installation.

*Vision-KI-Knoten (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Integrationsknoten für die Hailo-8-Vision-Pipeline, mit einer echten stufenweisen Hardware-Bereitschaftsprüfung.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — echte Registry für kompilierte Modelle mit Hailo-Architektur-/Prüfsummen-Safe-Load-Verifizierung.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — echter GStreamer-Pipeline- + MediaMTX-Konfigurationsgenerator mit einer echten HailoRT-Integrationsschranke.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — echtes Position-Based-Visual-Servoing-Korrekturgesetz, sicherheitsgesteuert nach vorgelagertem Zonenstatus.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — echte Zonenverletzungsprüfung und E-STOP-Anforderung, mit erzwungener Kalibrierungsaktualität.

*Orchestrierung & Schwarm*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — Integrationsknoten mit einem echten gRPC/Protobuf-Health-Report-Vertrag und einer Missions-Zustandsmaschine.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — echte prioritätsbasierte Job-Queue mit Deduplizierung, über eine echte HTTP-API.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — echter gRPC-basierter Flotten-Health-Watchdog mit Retry/Backoff und Identitäts-Mismatch-Erkennung.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — echter RRT-basierter 3D-Pfadplaner mit echter Hindernis-/Arbeitsraum-Kollisionsvalidierung.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — echte CRDT-LWW-Element-Map-Zustandssynchronisation, eigenschaftsgetestet auf Multi-Zellen-Konvergenz.

*Digitaler Zwilling & Simulation*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — Integrationsknoten für die Digital-Twin-Engine, mit einem echten Versionskompatibilitäts-Sync-Vertrag.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — echte Hardware-in-the-Loop-Sicherheitsverriegelung, die Befehle zwischen Simulation und echter Hardware routet.
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — echte Vorwärtskinematik und Gelenkgrenzenvalidierung über eine echte URDF-Teilmenge.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — echter prozeduraler 2D-Szenengenerator mit YOLO/COCO-Annotationsexport.

*Daten & Analytik*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — echter sqlite3-gestützter Zeitreihenspeicher mit einer echten Ingest-/Abfrage-HTTP-API.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — echter FFT- + statistischer Basislinien-Anomaliedetektor mit Drift-Überwachung.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — echte OEE-/Verfügbarkeitsberechnung über den DATALAKE-Verlauf, mit reproduzierbarem CSV-Export.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — echte CAN/WebSocket-Ingestion-Pipeline in DATALAKE, mit Sequenz-Deduplizierung.

*Industrie-Gateway*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — Integrationsknoten, der zu Industrieprotokollen weiterleitet, mit einer echten Befehls-Allowlist-/Backpressure-Schicht.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — echter OPC-UA-Adressraum, verifiziert mit einer echten Binärprotokoll-Client-Session.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — echter MQTT-Broker mit optionaler Pro-Client-Authentifizierung und Topic-ACLs.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — echte MTConnect-`/probe`- und `/current`-XML-Endpunkte mit Degraded-Mode-Ausgabe.

*Ergänzende Tools & Ökosystembetrieb*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — Smart-Summaries- und Anomaly-Highlighting-Panels über DATALAKE/ANOMALY-DETECTOR, mit einem ehrlichen statistischen Fallback.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — Flotten-CLI mit einem echten, stabilen Exit-Code-Vertrag, ein echter Live-Client der eigenen API von HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — WearOS-Begleit-App mit echten haptischen Alarmen und einem Sprach-Relay zum gekoppelten Telefon.
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — Firmware für ein Platinenmontagegestell mit echter Werkzeug-ID-Dekodierung und Smart-Idle-Vorheizlogik.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — Firmware plus ein echter Python-Vision-Begleiter für einen Thermal-/RGB-Inspektionswerkzeugkopf.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — administratives Desktop-Tool, das jedes Repository in diesem Ökosystem entdeckt, klont und aktualisiert.

---

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LIZENZ
GPL-3.0 - Siehe LICENSE für Details.
