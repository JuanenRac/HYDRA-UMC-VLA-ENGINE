<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-VLA-ENGINE banner" width="100%">
</p>

# 👁️ HYDRA-UMC-VLA-ENGINE

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | 🇵🇹 <b>Português</b></p>

### 🤖 Framework multimodal de visão-linguagem-ação para robótica

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Model-OpenVLA%20%2F%20RT--2-orange.svg" alt="VLA">
  <img src="https://img.shields.io/badge/Acceleration-Hailo--10-green.svg" alt="Hailo-10">
</p>

**Verificação de honestidade - o que realmente funciona hoje:** a discretização de codificação/descodificação de tokens de ação (`action_tokens.py`), a integração de trajetórias com passagem de ângulo real (`trajectory.py`), o contrato de forma/confiança do manifesto de modelo (`model_manifest.py`), a verificação honesta do estado do hardware `status` (`hardware.py`), a superfície JSON/HTTP (`api.py`) e a fronteira de integração com o HailoRT (`hailo_runtime.py`) são reais e testados - 98 testes a passar (`pytest tests/`). Nada disto precisa de um modelo VLA nem de um NPU Hailo-10 para correr ou ser testado - `tokens encode`/`tokens decode`/`trajectory integrate`/`status` funcionam hoje contra dados sintéticos, e o `status` reporta deliberadamente `no_accelerator`/`no_model_weights`/`hardware_ready_no_inference` em vez de um "pronto" falso. O novo `Dockerfile` reutiliza as mesmas opções de CLI já verificadas em direto na unidade systemd real do CM5, mas ele próprio não foi testado em compilação - não há runtime Docker nesta máquina de desenvolvimento. A inferência real de um modelo VLA, o controlo semântico e a generalização zero-shot continuam a ser pura aspiração: ainda não foi escolhido nenhum modelo, e este ambiente não tem um módulo Hailo-10 físico onde o correr. Veja o `CHANGELOG.md` para saber exatamente o que já foi entregue, e a lista de funcionalidades da secção 1 abaixo para a distinção real/futuro por funcionalidade.

**Limites conhecidos:** uma trajetória é uma proposta: `POST /trajectory/integrate` (e a CLI) recusam qualquer delta fora do espaço de ação (0,05 m, 0,1 rad por passo, pinça entre 0 e 1) e mais de 1000 passos, em vez de os integrar. O token decodificado «sem movimento» é exatamente 0,0 nos eixos simétricos (um vocabulário par não tem um bin centrado em zero, o que acrescentava uma pequena deriva a cada passo). Os deltas de rotação continuam a ser somados a ângulos de Euler, o que só é uma boa aproximação para ângulos pequenos longe de um pitch de 90 graus; não há inferência, pelo que nada na família consome ainda esta saída além do proxy genérico do servidor. O serviço mantém `/dev` visível sob o systemd (`DevicePolicy=closed` com `/dev/hailo0` permitido), lê o seu workspace de `HYDRA_UMC_WORKSPACE` no contentor, só aceita um `?workspace=` dentro do seu próprio workspace e só conta um modelo quando existe um ficheiro `.hef` não vazio.

---

## 📋 Num relance

| | |
|---|---|
| Versão | `0.1.6` |
| Maturidade | Estabelecido |
| Testes | 98 (`pytest tests/`) |
| Tecnologia | Python / Vision-Language-Action model |
| Destino | O Raspberry Pi CM5 de uma célula HYDRA-UMC |
| Em hardware real | Ainda não: não há registo de execução em hardware real para esta versão |

## 1. 🛠️ VISÃO TÉCNICA GERAL

O **HYDRA-UMC-VLA-ENGINE** é a ponte multimodal que traduz contexto visual e linguagem natural em ações robóticas diretas. Implementa versões quantizadas de modelos VLA de última geração (como o OpenVLA ou variantes especializadas do RT-2) para correr localmente no NPU Hailo-10.

Este motor permite ao robô compreender comandos como "pegue no componente azul e coloque-o no tabuleiro vermelho" analisando a imagem da câmara em direto e gerando a sequência cinemática correspondente.

### Funcionalidades principais:
* ✅ **Real v0 - tokens de ação e trajetória:** `action_tokens.py` implementa o esquema de discretização de 256 intervalos ao estilo OpenVLA/RT-2 (ação contínua <-> token discreto, segundo o espaço de ação de 7 GDL de delta de pose + garra), e `trajectory.py` integra uma sequência de ações descodificada numa trajetória de poses absolutas. Exposto por `tokens encode`/`tokens decode`/`trajectory integrate` abaixo - não precisa de um modelo VLA nem de um NPU Hailo-10 para correr ou ser testado.
* 🧯 **Algo que não é um número nunca se converte num movimento:** `encode_action` rejeita NaN e infinito (limitar um NaN escolhia o limite superior, pelo que uma saída NaN do modelo se codificava como o movimento máximo em todos os eixos), um `vocab_size` fora de 2-65536 é recusado, e a API HTTP rejeita com `400` os literais JSON `NaN`/`Infinity` e as cadeias `"nan"`/`"inf"`. *(implementado)*
* 📜 **Manifesto de modelo + validação de saída:** Um contrato real e versionado (`model_manifest.py`) que qualquer futura integração de modelo tem de cumprir - forma de ação/vocabulário coincidente e uma família de chips Hailo conhecida - mais a validação de forma/confiança da saída de inferência em bruto de um modelo. *(implementado)*
* 🔌 **Fronteira de integração com o HailoRT, preparada antes do módulo:** `hailo_runtime.py` está escrito contra a API real e confirmada de `hailo_platform` (`VDevice`, `HEF`, `ConfigureParams`, `InputVStreamParams`/`OutputVStreamParams`) - importada só quando é preciso, para que este repositório se instale/teste sem problemas sem o pacote `hailort` nem um módulo Hailo-10, e `hailo_output_to_tokens()` (a peça que mapeia um resultado de inferência real para o contrato de tokens deste motor) está totalmente testada hoje. *(implementado, apenas fronteira de integração - veja abaixo)*
* 🩺 **Subcomando `status` honesto:** Reporta a disponibilidade real do acelerador/pesos do modelo - `no_accelerator`, `no_model_weights` ou `hardware_ready_no_inference` - nunca um estado "pronto" falso. *(implementado)*
* 🌉 **Controlo semântico (planeado):** Mapeamento direto de píxeis e texto para posições de articulação ou comandos de ferramenta. *(precisa de um modelo VLA real - trabalho futuro.)*
* ⚡ **Raciocínio em tempo real (planeado):** Inferência acelerada por Hailo-10 para geração de ações de baixa latência. *(precisa do NPU Hailo-10 real que este ambiente não tem.)*
* 🔄 **Generalização zero-shot (planeada):** Capaz de tratar objetos nunca vistos com base em descrições semânticas. *(precisa de um modelo VLA treinado real.)*
* 🛠️ **Planeamento de tarefas (planeado):** Decompõe objetivos complexos em primitivas robóticas atómicas. *(precisa de um modelo VLA real.)*
* 👨‍👩‍👧 **Filho do Cognitive AI Node:** Corre como um de quatro serviços irmãos sob o [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE) (ao lado do Voice-UI, do Semantic-Planner e do Docs-QA), partilhando a imagem HydraOS e os pesos do modelo do seu pai em vez de manter cópias próprias.
* 📦 **Versionamento em odómetro:** Cada compilação real sobe automaticamente a versão do `pyproject.toml` (`bump_version.py`) - sem edições manuais de versão.

---

## 2. 🔄 FLUXO DE INFERÊNCIA VLA

```mermaid
flowchart LR
    IMG["Image Frame"] --> VLA["VLA-ENGINE (Hailo-10)"]
    TXT["Text Instruction"] --> VLA
    VLA --> ACTION["Action Tokens"]
    ACTION --> TRAJ["Trajectory Generator"]
    TRAJ --> MOTOR["Motor Commands"]
```

---

## 3. 🧱 ARQUITETURA E DECISÕES DE DESENHO

Este repositório é um **filho** da família Cognitive AI Node - o seu pai, o [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE), é dono da imagem HydraOS partilhada e dos pesos de modelo quantizados, e liga este serviço ao `docker-compose.yml` junto dos seus três irmãos (Voice-UI, Semantic-Planner, Docs-QA):

* **Porque este filho não tem hardware/firmware/`os/`/`models/` próprios.** Corre inteiramente no CM5 + módulo M.2 Hailo-10 que o pai já possui - manter os pesos do modelo e a imagem HydraOS centralizados num só sítio evita quatro cópias divergentes de vários gigabytes em toda a família.
* **Porque uma disposição `src/`.** Mantém o pacote instalável (`hydra_umc_vla_engine`) separado das ferramentas da raiz do repositório (`bump_version.py`), em linha com a disposição usada por todos os outros projetos Python do ecossistema.
* **Porque a tokenização de ações chega antes da inferência de modelos.** Converter uma ação contínua em tokens discretos (e vice-versa) é matemática fixa, definida pelos limites do espaço de ação e pelo tamanho do vocabulário - não precisa de um modelo VLA nem de um NPU Hailo-10 para ser escrita ou testada, pelo que a v0 entrega primeiro essa peça (`action_tokens.py`, `trajectory.py`). A inferência VLA real precisa dos pesos do modelo e do hardware Hailo-10 que este ambiente não tem, e chega mais tarde.
* **Porque o `hailo_runtime.py` importa `hailo_platform` só quando é preciso, dentro de apenas duas funções.** O `hailort` não está no PyPI e não está instalado nesta máquina de desenvolvimento - importá-lo ao carregar o módulo faria todo este pacote falhar ao instalar/importar em qualquer lado exceto numa máquina com um módulo Hailo real ligado. Só `open_vdevice()` e `load_hailo_vla_model()` (as duas funções que genuinamente precisam do HailoRT real) o importam, e só quando são chamadas; ambas levantam um `HailoNotAvailableError` claro em vez de um `ImportError` simples quando falta. O mesmo padrão que este ecossistema já usa em todos os outros transportes de hardware reais (série GRBL, MAVLink, SPI-OTA, ...).
* **Como isto se encaixa no resto do ecossistema.** Este motor converte perceção em bruto (imagens da câmara, encaminhadas conceptualmente desde o HYDRA-UMC-VISION-NODE a montante) e instruções em linguagem natural em tokens de ação que o HYDRA-UMC-SEMANTIC-PLANNER, o seu irmão, converte em decisões ao nível da missão para o HYDRA-UMC-ORCHESTRATOR.
* **Porque o `model_manifest.py` não nomeia uma variante concreta de OpenVLA/RT-2.** Ainda não foi escolhido nenhum modelo (veja o Roteiro deste README) - o `EXPECTED_MODEL_MANIFEST` é honestamente um contrato de forma/destino derivado diretamente das constantes reais do próprio `action_tokens.py`, e não um carregador para um modelo que não existe. O `hailo_arch` reutiliza o mesmo conjunto fechado e real de famílias de chips que o `HYDRA-UMC-DETECTION-HEF` já valida no seu próprio registo de modelos.
* **Porque o `status` reporta `hardware_ready_no_inference` em vez de "pronto".** Mesmo quando um dispositivo Hailo-10 real e pesos de modelo reais estiverem presentes, esta v0 continua sem código de inferência real - alegar prontidão nesse ponto seria uma mentira real sobre uma capacidade que ainda não existe. O `determine_mode()` de `hardware.py` verifica primeiro o acelerador (uma sonda barata do nó de dispositivo) e só depois os pesos do modelo, a mesma ordem de pré-condição mais barata primeiro que o `safe_load()` do `HYDRA-UMC-DETECTION-HEF` já usa.
* **Porque o `model_weights_available()` verifica o `models/` do pai e não um local.** Este filho não tem `models/` próprio (removido - veja o ponto acima) - os pesos partilhados reais vivem no `models/` do próprio pai `HYDRA-UMC-COGNITIVE-NODE`, um nível acima no espaço de trabalho de irmãos, o mesmo diretório real que o `check_shared_models()` desse repositório já verifica.

---

## 📂 ESTRUTURA DE DIRETÓRIOS

```text
HYDRA-UMC-VLA-ENGINE/
├── src/hydra_umc_vla_engine/   # Código-fonte
│   ├── action_tokens.py        # Discretização ação <-> token (ao estilo OpenVLA/RT-2)
│   ├── trajectory.py           # Integração sequência de ações -> trajetória de poses
│   ├── model_manifest.py       # Contrato real de forma do modelo + validação da saída de inferência
│   ├── hardware.py             # Sondas reais de disponibilidade do acelerador/pesos do modelo
│   ├── hailo_runtime.py        # Fronteira real de integração com o HailoRT (hailo_platform), importada só quando é preciso
│   ├── api.py                  # Superfície JSON/HTTP simples (stdlib http.server) sobre tokens/trajetória/estado
│   └── main.py                 # Ponto de entrada da CLI (invocação simples + `tokens`/`trajectory`/`status`)
├── tests/                      # Suite pytest real (action_tokens, trajectory, manifest, hardware, hailo_runtime, api, CLI)
├── docs/                       # Documentação e benchmarks
├── images/                     # Multimédia e diagramas
├── systemd/
│   └── hydra-umc-vla-engine.service  # Unidade systemd local do CM5 para a API de tokenização de ações/trajetórias
├── build/                      # Saída de compilação local (ignorada pelo git)
├── pyproject.toml              # Metadados do pacote (versão subida em odómetro)
├── bump_version.py             # Subida de versão nativa em odómetro (usada por build.sh/.bat)
├── bump_manifest_version.py    # Sincroniza a versão de hydra-umc.project.json com a nativa (--sync)
├── build.sh / build.bat        # Cria o venv, instala (com extras de desenvolvimento), verifica a importação, executa os testes
└── run.sh / run.bat            # Executa o ponto de entrada
```

> **Nota:** `hardware/` e `firmware/` foram removidos - este nó corre num CM5 + módulo M.2 Hailo-10 já existentes, sem desenho próprio de hardware/firmware. `os/` e `models/` também foram removidos - a imagem HydraOS e os pesos partilhados do modelo Hailo-10 vivem no pai `HYDRA-UMC-COGNITIVE-NODE`, a que este projeto se liga como serviço (veja o seu `docker-compose.yml`).

---

## ⚙️ GUIA DE COMPILAÇÃO E EXECUÇÃO

Requer Python >= 3.10.

```bash
# Linux / macOS / Git Bash
./build.sh   # cria o .venv, instala o pacote (editável, com extras de
             # desenvolvimento), verifica a importação, executa a suite de testes real
./run.sh     # executa o ponto de entrada

# Windows (cmd)
build.bat
run.bat
```

O `build.sh`/`build.bat` sobem a versão (em odómetro, veja `bump_version.py`) antes de cada compilação real. Saída esperada de `run.sh` (invocação simples):

```text
HYDRA-UMC-VLA-ENGINE v0.1.6
Vision-Language-Action engine (Hailo-10) - translates camera frames and text instructions into robotic action sequences.
```

Exemplo real - codificar uma ação em tokens, descodificá-la de volta e integrar uma curta sequência de ações numa trajetória:

```bash
./run.sh tokens encode --action "0.02,-0.03,0.01,0.05,-0.04,0.02,0.7"
# 179,51,153,192,76,153,179

./run.sh tokens decode --tokens "179,51,153,192,76,153,179"
# 0.020117,-0.029883,0.009961,0.050391,-0.040234,0.019922,0.701172
# (não idêntico à entrada da codificação acima - a discretização de 256
# intervalos tem perdas por desenho, a descodificação recupera o ponto médio
# do intervalo, não o valor original exato)

echo '[[0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5], [0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 1.0]]' > actions.json
./run.sh trajectory integrate --start "0,0,0,0,0,0" --actions actions.json
# step 0: x=0.000000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.000000
# step 1: x=0.010000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.500000
# step 2: x=0.010000 y=0.010000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=1.000000
```

O `status` reporta a disponibilidade real e honesta do acelerador/pesos do modelo - nunca um estado pronto falso:

```text
$ ./run.sh status
accelerator (Hailo-10):    MISSING
model weights (parent):    MISSING
mode: no_accelerator - no Hailo-10 NPU device node on this machine - real inference cannot run here.
```

### 🩺 Resolução de problemas

* **`python: command not found` / a compilação falha no passo 1.** Requer Python >= 3.10 no `PATH`. No Windows, instale a partir de [python.org](https://python.org) e confirme que "Add to PATH" foi marcado durante a instalação; `python3` é o nome habitual em Linux/macOS.
* **O `build.sh` não consegue ativar o venv.** `python3 -m venv .venv` dispõe o script de ativação de forma diferente por plataforma: `.venv/bin/activate` em Linux/macOS, `.venv/Scripts/activate` no Windows (também verdade para um venv de Python do Windows usado a partir do Git Bash). O `build.sh` já verifica os dois caminhos - se mesmo assim falhar, apague o `.venv/` e execute de novo `./build.sh` para o recriar do zero.
* **`pip install -e .` falha.** Normalmente um `.venv/` antigo. Apague a pasta `.venv/` e execute de novo `./build.sh`/`build.bat` para o recriar.
* **O `import OK` nunca aparece.** Significa que o próprio `python -c "import hydra_umc_vla_engine"` falhou - execute de novo com o venv ativo para ver o traceback real.

---

## ✅ Estado atual e próximos passos

**Real hoje:** codificação/descodificação de tokens de ação e geração de trajetórias (`action_tokens.py`, `trajectory.py`) - os passos "Action Tokens" e "Trajectory Generator" do diagrama de fluxo acima - mais uma fronteira real de integração com o HailoRT (`hailo_runtime.py`) pronta para um `.hef` real e um módulo Hailo-10 no momento em que existirem. 98 testes e uma CLI real.

**Ainda por fazer, e bloqueado por hardware real/um modelo real:** executar inferência precisa de um modelo VLA `.hef` compilado real (OpenVLA/RT-2 quantizado para Hailo-10 - ainda sem modelo concreto escolhido) e de um módulo Hailo-10 físico ligado, dois bloqueios reais e inevitáveis que o `hailo_runtime.py` não consegue remover sozinho - mas carregar e descodificar um, quando existir, já não é código por escrever.

---

## 🚀 ROTEIRO
* **Fase 1:** Implantação do motor VLA e processamento de entradas multimodais no Hailo-10.
* **Fase 2:** Integração do planeador semântico com modelos comportamentais do enxame e memória de longo prazo.
* **Fase 3:** Execução local de baixa latência da Voice UI e cancelamento de ruído industrial.
* **Fase 4:** Suporte da geração de ações coordenadas de braço duplo e auditorias de tomada de decisão autónoma.

---

## 🔗 Projetos relacionados

Este projeto faz parte do ecossistema de robótica HYDRA-UMC do mesmo autor (JuanenRac / Electro Hobby 3D). Vale a pena conhecê-los, porque um pedido pode ser, na verdade, sobre um destes e não sobre este repositório.

**Projeto-mãe**
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — hub de integração para o pipeline cognitivo Hailo-10 (orquestração de LLM/VLA/voz); o pai de que este repositório é uma etapa ou consumidor específico, dentro do seu próprio pipeline cognitivo.

**Projetos irmãos** — as outras etapas/consumidores do próprio pipeline cognitivo Hailo-10 do HYDRA-UMC-COGNITIVE-NODE
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — front-end de voz real (VAD + analisador de intenções) com um relé para o relógio limitado e protegido por confirmação.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — decomposição real de tarefas baseada em regras e recuperação semântica de erros sobre os códigos de erro do MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — pesquisa real de documentos TF-IDF só com a biblioteca padrão sobre a documentação Markdown deste ecossistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — técnico de manutenção de IA local, protegido por políticas, para o próprio ecossistema: observa, diagnostica e propõe correções; os dois níveis de maior risco não estão implementados de propósito.

**Também fazem parte do ecossistema**

*Hardware e plataforma centrais*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — a placa-mãe física do braço robótico: anfitrião CM5 + STM32H745 de dois núcleos, que orquestra até 8 braços de ferramenta por CAN-OTA/SPI-OTA.
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — camada de produto reproduzível do Raspberry Pi OS para o CM5: agente só de leitura, configuração/perfis validados, aprovisionamento Wi-Fi de primeiro contacto.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — o contrato JSON-Schema partilhado e a fronteira de portas de segurança contra a qual cada bridge valida os seus comandos.
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registo declarativo de manifestos de adaptador e validador para conectores de máquinas externas; estende a ideia de contrato do SDK a máquinas externas sem substituir os projetos de gateway industrial.

*Backend central e clientes*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — o back-end headless real (REST/WebSocket) com que todos os clientes de controlo realmente comunicam.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — painel web de controlo com visualização 3D em tempo real de vários robôs.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro de comando de enxame para desktop (PySide6) para vários servidores ao mesmo tempo, empacotado como executável independente.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — aplicação Android nativa de controlo, com início de sessão biométrico e um companheiro Wear OS emparelhado.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — aplicação de controlo para iOS/iPadOS (Flutter) com sincronização WebSocket em tempo real.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interface tátil nativa para o ecrã tátil DSI de 7" integrado, executada no próprio CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — criador/editor gráfico de URDF para desktop que envia os modelos concluídos para o catálogo do STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor de modelos STL para desktop que transforma/substitui/remove/adiciona peças reais no mesmo catálogo de modelos que o HYDRA-UMC-EDITOR-URDF também edita.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — fronteira de coordenação para frotas AGV/AMR através de um publicador MQTT VDA 5050 real.
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordenador de células CNC de alto nível com acesso real ao estado GRBL e aos bytes de controlo.
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — fronteira de coordenação para droides com patas/humanoides, com um emissor real de comandos para o Boston Dynamics Spot.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordenador de segurança de células laser que lê 3 proteções reais por GPIO (chave, caixa e interlock).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordenador seguro de fluxo de placa de alto nível para pick-and-place com OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — fronteira de coordenação segura para impressoras 3D Moonraker/Klipper, com comandos de trabalho reais protegidos por portas.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordenador de segurança com um transporte ROS 2 real baseado em rclpy importado sob demanda.
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — fronteira de coordenação para UAV com câmara, com um emissor real de comandos MAVLink.

*Plataforma de ferramentas URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware da placa física Universal Robot Tool Controller, mais de 25 perfis de ferramenta por barramento CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — ferramenta gráfica de gravação para desktop das placas URTC, por CAN-OTA e também SWD/JTAG de chip completo.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — ferramenta de diagnóstico CAN em tempo real para desktop das placas URTC, com um painel por perfil de ferramenta.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa no navegador ao URTC-TESTER através da Web Serial API, sem instalação local.

*Nó de IA de visão (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — centro de integração do pipeline de visão Hailo-8, com uma verificação real de prontidão de hardware por fase.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registo real de modelos compilados com verificação segura de carga por arquitetura Hailo e soma de verificação.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — pipeline GStreamer real e gerador de configuração MediaMTX com uma fronteira de integração HailoRT real.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — lei de correção real de servovisão baseada em posição, protegida pelo estado da zona a montante.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — verificação real de violação de zonas e pedido de E-STOP, com exigência de calibração recente.

*Orquestração e enxame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — centro de integração com um contrato real de relatório de saúde gRPC/Protobuf e uma máquina de estados de missões.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — fila real de trabalhos por prioridade com deduplicação, sobre uma API HTTP real.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vigilante real de saúde da frota por gRPC com repetição/recuo e deteção de identidade incoerente.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — planeador real de trajetórias 3D baseado em RRT com validação real de colisões com obstáculos e espaço de trabalho.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — sincronização real de estado CRDT LWW-Element-Map, testada por propriedades para a convergência de várias células.

*Gémeo digital e simulação*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — centro de integração do motor de gémeo digital, com um contrato real de sincronização de compatibilidade de versões.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — interlock de segurança real de hardware-in-the-loop que encaminha comandos entre a simulação e o hardware real.
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — cinemática direta real e validação de limites de juntas sobre um subconjunto real de URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — gerador procedural real de cenas 2D com exportação de anotações YOLO/COCO.

*Dados e análise*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — armazém real de séries temporais sobre sqlite3 com uma API HTTP real de ingestão/consulta.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — detetor real de anomalias por FFT e linha de base estatística, com monitorização de deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — cálculo real de OEE/disponibilidade sobre o histórico do DATALAKE, com exportação CSV reprodutível.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — pipeline real de ingestão CAN/WebSocket para o DATALAKE, com deduplicação por sequência.

*Gateway industrial*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — centro de integração que retransmite para protocolos industriais, com uma camada real de lista de comandos permitidos e contrapressão.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — espaço de endereços OPC-UA real, verificado com uma sessão de cliente real do protocolo binário.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — broker MQTT real com autenticação opcional por cliente e ACL de tópicos.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — endpoints XML MTConnect `/probe` e `/current` reais com saída em modo degradado.

*Ferramentas complementares e operações do ecossistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — painéis de Resumos Inteligentes e Realce de Anomalias sobre o DATALAKE/ANOMALY-DETECTOR, com um recurso estatístico honesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI da frota com um contrato de códigos de saída real e estável, um cliente vivo genuíno da API do HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — aplicação companheira WearOS com alertas hápticos reais e um relé de voz para o telemóvel emparelhado.
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware de um rack de montagem de placas com descodificação real do ID da ferramenta e lógica de pré-aquecimento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware mais um companheiro de visão em Python real para uma cabeça de ferramenta de inspeção térmica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — ferramenta administrativa de desktop que descobre, clona e atualiza todos os repositórios deste ecossistema.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — ferramenta de desktop para Windows/Linux que constrói uma imagem do CM5 pronta a gravar com as versões mais recentes do ecossistema, com configuração de primeiro arranque de Wi-Fi/utilizador/SSH ao estilo do Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordenador de incidentes de manutenção: um papel de borda de poucos privilégios recolhe um inventário/estado higienizado, um papel de plano de controlo mostra-o só de leitura e pede a um fornecedor de IA que sugira um diagnóstico; nunca aplica um patch nem implanta nada.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — anfitrião de desenvolvimento reproduzível (Raspberry Pi 5 / CM5) que guarda o código-fonte do ecossistema e executa tarefas limitadas de compilação/teste numa fila durável; um papel de desenvolvimento dedicado, explicitamente não um CM5 operacional.

---

## 📚 Documentação e comunidade

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — pilha tecnológica e diretrizes de código para um pull request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — as normas de comportamento esperadas nesta comunidade.
- **[SECURITY.md](SECURITY.md)** — como comunicar uma vulnerabilidade e as áreas de segurança em que este projeto se concentra.
- **[SUPPORT.md](SUPPORT.md)** — onde fazer perguntas e comunicar erros.
- **[LICENSE.md](LICENSE.md)** — a licença deste projeto.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENÇA
GPL-3.0 - consulte LICENSE para mais detalhes.

