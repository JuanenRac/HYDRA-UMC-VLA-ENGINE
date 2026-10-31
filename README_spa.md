<!-- =============================================================================
HYDRA-UMC-VLA-ENGINE - Vision-language-action engine contracts
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VLA-ENGINE banner" width="100%">
</p>

# 🤖 HYDRA-UMC-VLA-ENGINE

<p align="center"><a href="README.md">🇺🇸 English</a> | 🇪🇸 <b>Español</b> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### 🤖 Framework Multimodal Vision-Language-Action para Robótica

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Model-OpenVLA%20%2F%20RT--2-orange.svg" alt="Model">
  <img src="https://img.shields.io/badge/Acceleration-Hailo--10-green.svg" alt="Acceleration">
  <img src="https://img.shields.io/badge/Tests-221%20passing-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Version-0.2.0-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-functional-0F6CBD.svg" alt="Maturity">
</p>

---

> **Estado de seguridad física y de ciberseguridad:** este ecosistema no es un sistema de seguridad certificado. Todavía no existe una ruta de E-STOP por hardware, ni límites ni enclavamientos aplicados por el firmware, ni un comando de movimiento verificado; las imágenes de firmware se comprueban con CRC-32 y una firma Ed25519, y una compilación de versión rechaza las claves de desarrollo publicadas (los cabezales de herramienta y las placas de expansión detrás del relé siguen con cargadores de URTC, que usan un HMAC-SHA256 de clave compartida en lugar de una firma); TLS y TLS mutuo son opcionales y están desactivados por defecto; aún no se ha poblado ni probado ninguna placa propia. Lee la [línea base de seguridad](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) y el [modelo de amenazas](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) antes de fiarte de cualquier afirmación de aquí para la seguridad de una persona.

---

## 📋 De un vistazo

| | |
|---|---|
| Versión | `0.2.0` |
| Madurez | Funcional |
| Tests | 221 (`python -m pytest -q tests`) |
| Tecnología | Python / Vision-Language-Action model |
| Destino | La Raspberry Pi CM5 de una celda HYDRA-UMC |
| En hardware real | Todavía no: no consta ninguna ejecución en hardware real para esta versión |

**Ir a:** [Resumen](#-resumen) · [Arquitectura](#-arquitectura) · [Seguridad y protección](#-seguridad-y-protección) · [Inicio rápido](#-inicio-rápido) · [Pruebas](#-pruebas) · [Estructura del repositorio](#-estructura-del-repositorio) · [Proyectos relacionados](#-proyectos-relacionados)

## 🚦 Estado del proyecto

Cada línea es una parte de este repositorio y la luz dice hasta dónde llega hoy. Se escribe con lo que el repositorio puede demostrar (pruebas, compilaciones, ejecuciones), no con lo previsto.

🟢 Hecho y verificado · 🟡 Funciona, con límites conocidos · 🟠 Hecho a medias o sin verificar · 🔴 Sin hacer o sin funcionar

| Área | Estado | Qué significa aquí |
|---|---|---|
| Software | 🟡 | Funciona para su propósito principal; la comprobación de honestidad de arriba lista lo que aún falta |
| Pruebas | 🟢 | 221 pruebas automáticas, ejecutadas en cada cambio |
| Hardware real | 🔴 | Todavía no: no consta ninguna ejecución en hardware real para esta versión |
| Documentación | 🟢 | README en ocho idiomas, comprobado contra el manifiesto en cada cambio |

## 🎯 Resumen

**HYDRA-UMC-VLA-ENGINE** está pensado para ser el puente multimodal que traduce contexto visual y lenguaje natural en acciones robóticas directas. Se prevé que ejecute versiones cuantizadas de modelos VLA de última generación (como OpenVLA o variantes especializadas de RT-2) localmente en la NPU Hailo-10 (previsto: no hay modelo elegido ni inferencia en Hailo-10 todavía).

El objetivo es que el robot entienda órdenes como «coge el componente azul y colócalo en la bandeja roja» analizando la imagen de la cámara y generando la secuencia cinemática correspondiente. Hoy el motor codifica y decodifica tokens de acción e integra trayectorias dentro de límites fijos; no entiende lenguaje ni imágenes.

### Características Clave:
* 🔑 **Token Bearer opcional:** en loopback la API no necesita token; fuera de loopback se niega a arrancar sin uno (`--token-file` o `HYDRA_UMC_VLA_ENGINE_TOKEN`). Con un token configurado, toda petición debe enviar `Authorization: Bearer <token>` (comparación en tiempo constante); solo `GET /health`, la ruta de salud del manifiesto, queda abierta. *(implementado)*
* ✅ **Real v0 - tokens de acción y trayectoria:** `action_tokens.py` implementa el esquema de discretización de 256 bins estilo OpenVLA/RT-2 (acción continua <-> token discreto, según el espacio de acción de 7 grados de libertad - delta de pose + gripper), y `trajectory.py` integra una secuencia de acciones decodificadas en una trayectoria de poses absolutas. Expuesto vía `tokens encode`/`tokens decode`/`trajectory integrate` más abajo - no hace falta modelo VLA ni NPU Hailo-10 para ejecutarlo ni testearlo.
* 🧯 **Algo que no es un número nunca se convierte en un movimiento:** `encode_action` rechaza NaN e infinito (al acotar un NaN se elegía el límite superior, así que una salida NaN del modelo se codificaba como el movimiento máximo en todos los ejes), se rechaza un `vocab_size` fuera de 2-65536 y la API HTTP rechaza con `400` los literales JSON `NaN`/`Infinity` y las cadenas `"nan"`/`"inf"`. *(implementado)*
* 📜 **Manifiesto de modelo + validación de salida:** Un contrato real y versionado (`model_manifest.py`) que cualquier futura integración de modelo debe cumplir - haciendo coincidir la forma de acción/vocabulario y una familia de chip Hailo conocida - además de validación de forma/confianza para la salida cruda de inferencia de un modelo. *(implementado)*
* 🚧 **Guarda de trayectoria:** `guard.py` comprueba una trayectoria contra los límites de la celda antes de pedir a nadie que la apruebe: un volumen de trabajo, el paso más largo (metros y radianes), cuánto puede diferir un paso del anterior, el rango de la pinza y las zonas de HYDRA-UMC-SAFETY-ZONES en su propio JSON (un movimiento que entra o cruza una zona `danger` rechaza la trayectoria, un paso dentro de una zona `warning` se limita a una fracción). El resultado es `ok`, `clamped` (se recortó un paso y el resto se reintegró desde el recorte) o `rejected` (no se ofrece ninguna pose, `422`). `serve --guard-file FICHERO` (o `HYDRA_UMC_VLA_GUARD_FILE`) la activa para `POST /trajectory/integrate`, `--require-guard` no ofrece nada sin ella, y `trajectory integrate --guard-file` hace lo mismo por línea de órdenes. Una propuesta nunca autoriza nada. *(probado con trayectorias sintéticas; sin modelo ni máquina)*
* 🔌 **Límite de integración con HailoRT, preparado antes que el módulo:** `hailo_runtime.py` está escrito contra la API real y confirmada de `hailo_platform` (`VDevice`, `HEF`, `ConfigureParams`, `InputVStreamParams`/`OutputVStreamParams`) - importada de forma perezosa para que este repositorio se instale/testee limpiamente sin el paquete `hailort` ni un módulo Hailo-10 presente, y `hailo_output_to_tokens()` (la pieza que mapea un resultado de inferencia real al propio contrato de tokens de este motor) está completamente cubierta por tests unitarios hoy. *(implementado, solo límite de integración - ver más abajo)*
* 🩺 **Subcomando `status` honesto:** Reporta la disponibilidad real de acelerador/pesos de modelo - `no_accelerator`, `no_model_weights`, o `hardware_ready_no_inference` - nunca un falso estado "listo". *(implementado)*
* 🌉 **Control Semántico (previsto):** Mapeo directo desde píxeles y texto a posiciones de articulaciones o comandos de herramienta. *(necesita un modelo VLA real - trabajo futuro.)*
* ⚡ **Razonamiento en Tiempo Real (previsto):** Inferencia acelerada por Hailo-10 para generación de acciones de baja latencia. *(necesita la NPU Hailo-10 real que este entorno no tiene.)*
* 🔄 **Generalización Zero-Shot (previsto):** Capaz de manejar objetos no vistos basados en descripciones semánticas. *(necesita un modelo VLA real entrenado.)*
* 🛠️ **Planificación de Tareas (previsto):** Descompone objetivos complejos en primitivas robóticas atómicas. *(necesita un modelo VLA real.)*
* 👨‍👩‍👧 **Hijo del Cognitive AI Node:** Corre como uno de los cuatro
  servicios hermanos bajo [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)
  (junto a Voice-UI, Semantic-Planner y Docs-QA), compartiendo la imagen
  HydraOS y los pesos de modelos de su padre en vez de mantener copias
  propias.
* 📦 **Versionado Cuentakilómetros:** La versión de `pyproject.toml` solo la sube el comando `bump` explícito (`python tools/hydra_project_tool.py bump`, que ejecuta `bump_version.py`) - compilar nunca la cambia.

* 🧪 **Predicciones consistentes, modo sombra, filtro de confianza y rotaciones exactas (todo desactivado por defecto, nada mueve nada):** en `configs/vla-engine.json`, `consistency.predictions` mayor que 1 hace que `POST /trajectory/integrate` exija N-1 `alternatives` y no ofrezca ninguna trayectoria (HTTP 422) cuando un valor difiere de `actions` en más de `consistency.tolerance`; `shadow.enabled` activa `POST /shadow/compare`, que responde la diferencia entre las acciones que propone un modelo y las que dio el operador (por paso, media y máximo); `confidence.minimum` mayor que 0 exige un valor de `confidences` por acción y rechaza una trayectoria con una acción dudosa. Los tres valores de rotación de una acción son un vector de rotación compuesto como cuaterniones, correcto con ángulos grandes y cerca de cabeceo de 90 grados. Véase `docs/CLI_REFERENCE.md`.

## 🧩 Papel en HYDRA-UMC

**HYDRA-UMC-VLA-ENGINE** contiene las partes de un motor visión-lenguaje-acción que no necesitan un modelo: convertir acciones en tokens discretos y viceversa, integrar los pasos predichos en una trayectoria y una guarda que recorta o rechaza una trayectoria según el volumen de trabajo, los límites de velocidad, las zonas de seguridad y el rango de la pinza. Aún no se ejecuta ningún modelo; la frontera con Hailo-10 solo informa de lo que hay.

## 🏛️ Arquitectura

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-VLA-ENGINE architecture" width="100%">
</p>

<details>
<summary>Versión en texto del diagrama (Mermaid)</summary>

```mermaid
flowchart LR
    IMG["Frame de Imagen"] --> VLA["VLA-ENGINE (Hailo-10)"]
    TXT["Instrucción de Texto"] --> VLA
    VLA --> ACTION["Tokens de Acción"]
    ACTION --> TRAJ["Generador de Trayectorias"]
    TRAJ --> MOTOR["Comandos de Motores"]
```

</details>

### ARQUITECTURA Y DECISIONES DE DISEÑO

Este repositorio es un **hijo** de la familia Cognitive AI Node - su
padre, [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE),
posee la imagen HydraOS compartida y los pesos de modelos cuantizados, y
conecta este servicio en su `docker-compose.yml` junto a sus tres
hermanos (Voice-UI, Semantic-Planner, Docs-QA):

* **Por qué este hijo no tiene hardware/firmware/`os/`/`models/`
  propios.** Corre por completo sobre el módulo CM5 + Hailo-10 M.2 que ya
  posee el padre - centralizar los pesos de modelos y la imagen HydraOS
  en un solo lugar evita cuatro copias divergentes de varios gigabytes
  dentro de la familia.
* **Por qué una estructura `src/`.** Mantiene el paquete instalable
  (`hydra_umc_vla_engine`) separado del tooling en la raíz del repo
  (`bump_version.py`), igual que el resto de proyectos Python del
  ecosistema.
* **Por qué la tokenización de acciones llega antes que la inferencia del modelo.**
  Convertir una acción continua en tokens discretos (y viceversa) es
  matemática fija definida por los límites del espacio de acción y el
  tamaño del vocabulario - no necesita modelo VLA ni NPU Hailo-10 para
  escribirse ni testearse, así que v0 entrega esa pieza (`action_tokens.py`,
  `trajectory.py`) primero. La inferencia VLA real necesita los pesos del
  modelo y el hardware Hailo-10 que este entorno no tiene, y llega después.
* **Por qué `hailo_runtime.py` importa `hailo_platform` de forma perezosa, dentro de solo dos funciones.** `hailort` no está en PyPI y no está instalado en esta máquina de desarrollo - importarlo en el momento de cargar el módulo haría que todo este paquete fallara al instalarse/importarse en cualquier lugar excepto en una máquina con un módulo Hailo real conectado. Solo `open_vdevice()` y `load_hailo_vla_model()` (las dos funciones que realmente necesitan HailoRT real) lo importan, y de forma perezosa; ambas lanzan un `HailoNotAvailableError` claro en vez de un `ImportError` a secas cuando falta. Mismo patrón que este ecosistema ya usa para cualquier otro transporte de hardware real (serial GRBL, MAVLink, SPI-OTA, ...).
* **Cómo encaja en el resto del ecosistema.** Este motor convierte la
  percepción bruta (frames de cámara, conceptualmente reenviados desde
  HYDRA-UMC-VISION-NODE aguas arriba) e instrucciones en lenguaje natural
  en tokens de acción que su hermano HYDRA-UMC-SEMANTIC-PLANNER convierte
  en decisiones de misión para HYDRA-UMC-ORCHESTRATOR. *(Previsto: hoy el motor no recibe fotogramas de cámara ni texto, y ningún módulo consume su salida salvo el proxy genérico de HYDRA-UMC-SERVER.)*
* **Por qué `model_manifest.py` no nombra una variante específica de
  OpenVLA/RT-2.** Todavía no se ha elegido ningún modelo (ver la Hoja de
  Ruta de este mismo README) - `EXPECTED_MODEL_MANIFEST` es honestamente
  un contrato de forma/objetivo derivado directamente de las constantes
  reales de `action_tokens.py`, no un cargador para un modelo que no
  existe. `hailo_arch` reutiliza el mismo conjunto real y cerrado de
  familias de chip que `HYDRA-UMC-DETECTION-HEF` ya usa para validar su
  propio registro de modelos.
* **Por qué `status` reporta `hardware_ready_no_inference` en vez de
  "listo".** Incluso una vez que un dispositivo Hailo-10 real y los
  pesos de modelo reales estén ambos presentes, este v0 todavía no
  tiene código de inferencia real - afirmar que está listo en ese punto
  sería una mentira real sobre una capacidad que aún no existe.
  `determine_mode()` de `hardware.py` comprueba primero el acelerador
  (una prueba barata de nodo de dispositivo) antes que los pesos del
  modelo, el mismo orden de precondición-más-barata-primero que ya usa
  `safe_load()` de `HYDRA-UMC-DETECTION-HEF`.
* **Por qué `model_weights_available()` comprueba el `models/` del
  padre, no uno local.** Este hijo no tiene su propio `models/` (podado
  - ver el punto anterior) - los pesos compartidos reales viven en el
  propio `models/` del padre `HYDRA-UMC-COGNITIVE-NODE`, un nivel de
  espacio de trabajo hermano más arriba, el mismo directorio real que ya
  comprueba `check_shared_models()` de ese repositorio.

## 🔒 Seguridad y protección

Las propuestas de trayectoria pueden firmarse (apagado por defecto): `serve --proposal-key-file FICHERO --robot-id ROBOT [--proposal-valid-seconds N]` añade `robot_id`, `issued_at_ms`, `expires_at_ms` y una `signature` HMAC-SHA256 a lo que devuelve `POST /trajectory/integrate` (válida 60 segundos por defecto, 600 como máximo), y `verify_proposal()` rechaza una propuesta alterada, caducada, con fecha futura o de otro robot. Una propuesta sigue sin ser nunca una orden. La clave (al menos 16 bytes) vive en un fichero de la instalación, nunca en el repositorio.

## 🚀 Inicio rápido

Requiere Python 3.10 o superior.

```bash
./build.sh  # Linux, macOS (build.bat on Windows)
./run.sh tokens encode --action 0.02,0.00,-0.01,0.0,0.0,0.05,1.0
./run.sh trajectory integrate --start 0,0,0,0,0,0 --actions actions.json
./run.sh status
./run.sh serve --port 8098
```

## 🧪 Pruebas

221 pruebas automáticas se ejecutan con `python -m pytest -q tests`. No necesitan hardware ni nada fuera de esta máquina.

El CI ejecuta `HYDRA_UMC_CI=1 python tools/ci_validate.py`, que comprueba el manifiesto, los documentos, los ocho README y las imágenes.

## 🏗️ Compilación y publicación

Requiere Python >= 3.10.

```bash
# Linux / macOS / Git Bash
./build.sh   # crea .venv, instala el paquete (editable, con extras dev),
             # verifica la importación, ejecuta la suite de tests real
./run.sh     # ejecuta el punto de entrada

# Windows (cmd)
build.bat
run.bat
```

`build.sh`/`build.bat` nunca cambian la versión (solo `python tools/hydra_project_tool.py bump` la sube). Salida esperada de `run.sh`
(invocación desnuda):

```text
HYDRA-UMC-VLA-ENGINE v0.2.0
Vision-Language-Action engine (Hailo-10) - translates camera frames and text instructions into robotic action sequences.
```

Ejemplo real - codificar una acción en tokens, decodificarla de vuelta, e integrar una secuencia corta de acciones en una trayectoria:

```bash
./run.sh tokens encode --action "0.02,-0.03,0.01,0.05,-0.04,0.02,0.7"
# 179,51,153,192,76,153,179

./run.sh tokens decode --tokens "179,51,153,192,76,153,179"
# 0.020117,-0.029883,0.009961,0.050391,-0.040234,0.019922,0.701172
# (no es idéntico a la entrada de encode de arriba - la discretización de
# 256 bins es deliberadamente lossy (con pérdida), decode recupera el
# punto medio del bin, no el valor original exacto)

echo '[[0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5], [0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 1.0]]' > actions.json
./run.sh trajectory integrate --start "0,0,0,0,0,0" --actions actions.json
# step 0: x=0.000000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.000000
# step 1: x=0.010000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.500000
# step 2: x=0.010000 y=0.010000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=1.000000
```

`status` reporta la disponibilidad real y honesta de acelerador/pesos de
modelo - nunca un estado "listo" falso:

```text
$ ./run.sh status
accelerator (Hailo-10):    MISSING
model weights (parent):    MISSING
mode: no_accelerator - no Hailo-10 NPU device node on this machine - real inference cannot run here.
```

### 🩺 Solución de problemas

* **`python: comando no encontrado` / el build falla en el paso 1.**
  Requiere Python >= 3.10 en el `PATH`. En Windows, instálalo desde
  [python.org](https://python.org) y marca "Add to PATH" durante la
  instalación; en Linux/macOS suele llamarse `python3`.
* **`build.sh` no consigue activar el venv.** `python3 -m venv .venv`
  coloca el script de activación en una ruta distinta según la
  plataforma: `.venv/bin/activate` en Linux/macOS, `.venv/Scripts/activate`
  en Windows (también con un venv de Python de Windows usado desde Git
  Bash). `build.sh` ya comprueba ambas rutas - si sigue fallando, borra
  `.venv/` y vuelve a ejecutar `./build.sh` para reconstruirlo desde cero.
* **`pip install -e .` falla.** Normalmente por un `.venv/` obsoleto.
  Borra la carpeta `.venv/` y vuelve a ejecutar `./build.sh`/`build.bat`
  para recrearla.
* **`import OK` nunca se imprime.** Significa que `python -c "import
  hydra_umc_vla_engine"` falló - vuelve a ejecutarlo con el venv activo
  para ver el traceback real.

## 📂 Estructura del repositorio

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-VLA-ENGINE" width="100%">
</p>

<details>
<summary>Versión en texto del árbol</summary>

```text
HYDRA-UMC-VLA-ENGINE/
├── src/hydra_umc_vla_engine/   Código fuente
│   ├── __init__.py             Descripción y versión del paquete
│   ├── access.py               Token Bearer opcional para la API HTTP (no hace falta en loopback, obligatorio fuera de él)
│   ├── action_tokens.py        Discretizacion accion <-> token (estilo OpenVLA/RT-2)
│   ├── trajectory.py           Integracion de secuencia de acciones -> trayectoria de poses
│   ├── guard.py                Guarda de trayectoria: volumen de trabajo, límites de paso, zonas
│   ├── model_manifest.py       Contrato real de forma de modelo + validación de salida de inferencia
│   ├── hardware.py             Sondas reales de disponibilidad de acelerador/pesos de modelo
│   ├── hailo_runtime.py        Limite real de integracion HailoRT (hailo_platform), importada de forma perezosa
│   ├── api.py                  Superficie JSON/HTTP plana (http.server de stdlib) sobre tokens/trayectoria/estado
│   └── main.py                 Entry point CLI (invocacion desnuda + `tokens`/`trajectory`/`status`)
├── tests/                      Suite pytest real (action_tokens, trajectory, manifest, hardware, hailo_runtime, api, CLI)
├── docs/                       Documentación y benchmarks
├── images/                     Medios y diagramas
├── configs/                    configuración de los deltas de rotación
├── systemd/                    unidad de servicio
├── tools/                      herramientas del proyecto y comprobaciones del CI
├── .github/                    flujo de CI y plantillas de incidencias
├── pyproject.toml              Metadatos del paquete (versión con incremento cuentakilómetros)
├── bump_version.py             Incremento de versión tipo cuentakilómetros (solo lo ejecuta el comando `bump` explícito)
├── bump_manifest_version.py    Sincroniza la versión de hydra-umc.project.json con la nativa (--sync)
├── build.sh / build.bat        Crea el venv, instala (con extras dev), verifica la importación, ejecuta tests
├── run.sh / run.bat            Ejecuta el punto de entrada
├── CHANGELOG.md                qué cambió en cada versión
├── Dockerfile                  imagen de contenedor
├── build-test.sh               comprobación de compilación sin cambios
├── hydra-umc.project.json      manifiesto: versión, madurez, familia
└── test.sh                     ejecuta las pruebas
```

</details>

## 🗺️ Hoja de ruta y límites conocidos

**Límites conocidos hoy**

### Estado Actual y Próximos Pasos

**Real hoy:** la codificación/decodificación de tokens de acción y la generación de trayectoria (`action_tokens.py`, `trajectory.py`) - los pasos "Tokens de Acción" y "Generador de Trayectorias" del diagrama de flujo de arriba - más un límite de integración con HailoRT real (`hailo_runtime.py`) listo para un modelo `.hef` real y un módulo Hailo-10 en el momento en que existan. 221 tests y un CLI real.

**Todavía por delante, bloqueado por hardware real/un modelo real:** ejecutar de verdad la inferencia necesita un modelo VLA `.hef` realmente compilado (OpenVLA/RT-2 cuantizado para Hailo-10 - aún no se ha elegido un modelo concreto) y un módulo Hailo-10 físico conectado, ambos bloqueadores reales e inevitables que `hailo_runtime.py` no puede eliminar por sí solo - pero cargar y decodificar uno, una vez que exista, ya no es código sin escribir.

### HOJA DE RUTA

* **Fase 1:** Despliegue del motor VLA y procesamiento de entrada multi-modal en Hailo-10.
* **Fase 2:** Integración del planificador semántico con modelos de comportamiento de enjambre y memoria a largo plazo.
* **Fase 3:** Ejecución local de baja latencia de Voice UI y cancelación de ruido industrial.
* **Fase 4:** Soporte para generación de acciones coordinadas de doble brazo y auditorías de toma de decisiones autónomas.

## 🌍 Idiomas

Este README y los documentos del repositorio existen en ocho idiomas: inglés, español, alemán, francés, italiano, japonés, chino y portugués (Portugal). Se escriben a la vez y el CI comprueba que los ocho ficheros tengan las mismas secciones y los mismos enlaces. Este repositorio no tiene pantalla ni catálogo de mensajes propios, así que no hay cadenas de interfaz que traducir.

## 🔗 Proyectos relacionados

Este proyecto es parte del ecosistema de robótica HYDRA-UMC del mismo autor (JuanenRac / Electro Hobby 3D). Vale la pena conocerlo, ya que una petición podría en realidad ser sobre alguno de estos en vez de sobre este repositorio.

**Proyecto Padre**
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — nodo de integración para el pipeline cognitivo Hailo-10 (orquestación de LLM/VLA/voz); el padre del que este repositorio es una etapa o consumidor específico, dentro de su propio pipeline cognitivo.

**Proyectos Hermanos** — las demás etapas/consumidores del propio pipeline cognitivo Hailo-10 de HYDRA-UMC-COGNITIVE-NODE
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — front-end de voz real (VAD + analizador de intención) con un relé a Watch acotado y con confirmación.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — descomposición real de tareas basada en reglas y recuperación semántica de errores sobre códigos de error del MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — búsqueda real de documentos TF-IDF (solo librería estándar) sobre los propios documentos Markdown de este ecosistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — técnico de mantenimiento con IA local y con puertas de política para el propio ecosistema - observa, diagnostica y propone arreglos; los dos niveles de riesgo más altos están deliberadamente sin implementar todavía.

**También Forma Parte del Ecosistema**

*Hardware y Plataforma Base*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — el diseño de la placa madre del brazo robótico: host CM5 + coprocesador STM32H745 de doble núcleo, pensado para coordinar hasta 8 brazos herramienta por CAN-OTA/SPI-OTA (firmware en fase temprana; todavía no hay ninguna placa poblada).
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — capa de producto reproducible sobre Raspberry Pi OS para el CM5: agente de solo lectura, config/perfiles validados, aprovisionamiento WiFi de primer contacto.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — el contrato JSON-Schema compartido y la barrera de software de puerta de trabajos contra la que cada bridge valida sus comandos (no es una función de seguridad certificada).
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registro declarativo y validador de manifiestos de adaptador para conectores de máquinas externas; extiende la propia idea de contrato del SDK a máquinas externas sin sustituir a los proyectos de pasarela industrial.

*Backend Central y Clientes*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — el backend headless real (REST/WebSocket) con el que habla de verdad cada cliente de control.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — panel de control web con visualización 3D multi-robot en tiempo real.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro de mando de enjambre de escritorio (PySide6) para varios servidores a la vez, empaquetado como ejecutable independiente.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app nativa de control para Android con inicio de sesión biométrico y un compañero Wear OS emparejado.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app de control para iOS/iPadOS (Flutter) con sincronización en tiempo real por WebSocket.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaz táctil nativa para la pantalla táctil DSI de 7" a bordo, embebida en el propio CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creador/editor gráfico de URDF de escritorio que envía los modelos terminados al propio catálogo de STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor de escritorio de modelos STL, que transforma/reemplaza/quita/añade piezas reales en el mismo catálogo de modelos que también edita HYDRA-UMC-EDITOR-URDF.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barrera de coordinación para flotas AGV/AMR mediante un publicador MQTT VDA 5050 (probado solo contra una flota emulada).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinador de alto nivel para celdas CNC con acceso a estado/bytes de control GRBL (probado solo contra un emulador).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barrera de coordinación para droides con patas/humanoides, con un emisor de comandos para Boston Dynamics Spot (probado solo contra un emulador).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinador de celdas láser que lee 3 señales GPIO de llave/carcasa/enclavamiento (probado solo contra un chip simulado; no puede armar ni disparar un láser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinador de alto nivel seguro para el flujo de placas de pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — barrera de coordinación segura para impresoras 3D Moonraker/Klipper, con comandos de trabajo reales y controlados.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinador con un transporte ROS 2 rclpy importado de forma perezosa (todavía no ejecutado contra una instalación de ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barrera de coordinación para UAV equipados con cámara, con un emisor de comandos MAVLink (probado solo contra un emulador).

*Plataforma de Herramientas URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware para la placa física del Universal Robot Tool Controller, más de 25 perfiles de herramienta por bus CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — herramienta de escritorio con GUI para flashear placas URTC, CAN-OTA más SWD/JTAG de chip completo.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — herramienta de escritorio de diagnóstico CAN-bus en vivo para placas URTC, un panel por perfil de herramienta.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basada en navegador a URTC-TESTER mediante la Web Serial API, sin instalación local.
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — pasarela delante del bus CAN de URTC: lista de identificadores permitidos, límite de tasa y clave de sesión; software probado en ordenador, aún no en un bus real.

*Nodo IA de Visión (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — nodo de integración para el pipeline de visión Hailo-8, con una comprobación real de disponibilidad de hardware por etapa.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro real de modelos compilados con verificación de carga segura por arquitectura Hailo/checksum.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generador real de pipeline GStreamer + config MediaMTX, con una frontera de integración HailoRT real.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — ley de corrección Position-Based Visual Servoing con autorización condicionada al estado de zona; todavía sin estimación de pose por cámara.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — lógica v0 de invasión de zona, vigencia de calibración y solicitud de E-STOP que toma las posiciones de los objetos de un fichero; ningún detector la alimenta y todavía no hay un E-STOP físico conectado.

*Orquestación y Enjambre*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — nodo de integración con un contrato real de informe de salud gRPC/Protobuf y una máquina de estados de misión.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — cola de trabajos real basada en prioridad con deduplicación, sobre una API HTTP real.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — watchdog de salud de flota real basado en gRPC, con reintento/backoff y detección de discrepancia de identidad.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — planificador de rutas 3D real basado en RRT, con validación real de colisión de obstáculos/espacio de trabajo.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — sincronización de estado real mediante CRDT LWW-Element-Map, con pruebas de propiedades para convergencia multi-celda.

*Gemelo Digital y Simulación*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — nodo de integración para el motor de gemelo digital, con un contrato real de sincronización por compatibilidad de versión.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — enrutador hardware-in-the-loop con un enclavamiento de software por colisión entre simulación y hardware real (probado sin hardware real).
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — cinemática directa real y validación de límites articulares sobre un subconjunto real de URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — generador real de escenas 2D procedurales con exportación de anotaciones YOLO/COCO.

*Datos y Analítica*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — almacén de series temporales real respaldado por sqlite3, con una API HTTP real de ingesta/consulta.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — detector de anomalías real basado en FFT + línea base estadística, con monitorización de deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — cálculo real de OEE/disponibilidad sobre el histórico de DATALAKE, con exportación CSV reproducible.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — pipeline real de ingesta CAN/WebSocket hacia DATALAKE, con deduplicación por secuencia.

*Pasarela Industrial*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — nodo de integración que retransmite a protocolos industriales, con una capa real de lista blanca de comandos/contrapresión.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — espacio de direcciones OPC-UA real, verificado con una sesión de cliente real del protocolo binario.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — broker MQTT real con autenticación por cliente opcional y ACL de tópicos.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — endpoints XML reales `/probe` y `/current` de MTConnect, con salida en modo degradado.

*Herramientas Complementarias y Operaciones del Ecosistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — paneles de Resúmenes Inteligentes y Resaltado de Anomalías sobre DATALAKE/ANOMALY-DETECTOR, con un respaldo estadístico honesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI de flota con un contrato real y estable de códigos de salida, cliente real y en vivo de la propia API de HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app compañera de WearOS con patrones de alerta háptica y un relé de voz al teléfono emparejado (todavía no ejecutada en un reloj físico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware para un rack de montaje de placas con decodificación real de ID de herramienta y lógica de precalentamiento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware más un compañero de visión real en Python para un cabezal de inspección térmica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — herramienta administrativa de escritorio que descubre, clona y actualiza cada repositorio de este ecosistema.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — herramienta de escritorio Windows/Linux que construye una imagen de la CM5 lista para grabar, precargada con las versiones más actuales del ecosistema, con configuración de primer arranque de Wi-Fi/usuario/SSH al estilo de Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordinador de incidencias de mantenimiento: un rol edge de bajo privilegio recopila un snapshot de inventario/salud saneado, un rol control-plane lo renderiza de solo lectura y pide a un proveedor de IA que sugiera un diagnóstico - nunca aplica un parche ni despliega nada.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — host de desarrollo reproducible (Raspberry Pi 5 / CM5) que almacena el código del ecosistema y ejecuta tareas acotadas de compilación/pruebas bajo una cola duradera; un rol de desarrollo dedicado, explícitamente distinto de un CM5 operativo.

## 📚 Documentación

Dónde leer más:

* [Base de seguridad del ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [Modelo de amenazas del ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [Historial de cambios de este repositorio](CHANGELOG.md)
* [Licencia de este repositorio](LICENSE.md)

## 🤝 Contribuir y comunidad

* Antes de un pull request ejecuta `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py` (o `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`): debe imprimir `CI_VALIDATION=PASS`. No ejecutes `build.sh` ni `build.bat` para esta comprobación; compilar no es comprobar.
* Los ocho README se escriben desde una sola fuente en HYDRA-UMC-DOCS; no los edites a mano. Cambia la fuente y vuelve a escribirlos con `tools/make_readmes.py`.
* No afirmes en un README lo que no se ha ejecutado: di «simulado» o «sin probar en hardware» cuando esa sea la verdad.
* Mira [CONTRIBUTING.md](CONTRIBUTING.md), el [código de conducta](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md) y [SUPPORT.md](SUPPORT.md).

## 👤 AUTOR

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENCIA

GPL-3.0-or-later - [LICENSE](LICENSE).
