# JARVIS · Hermes med lokal stemme

Et stemmestyret JARVIS-dashboard oven på din [Hermes Agent](https://github.com/NousResearch/hermes-agent). Du taler, Jarvis svarer højt. Dashboardet er en grænseflade til din eksisterende Hermes-profil, ikke en ekstra agent, så det har de samme tools, skills, hukommelse, browser-automatisering og MCP-servere som Hermes i forvejen har.

Stemmen kører helt lokalt på din egen GPU: **Hearing** (din tale → tekst) med Parakeet TDT 0.6B v3 og **Speaking** (Jarvis' svar → lyd) med Kokoro-82M og en britisk mandlig **Voice**. Ingen lyd forlader maskinen, og der er ingen API-nøgler. Samtalen foregår på engelsk. Begreberne står i [GLOSSARY.md](GLOSSARY.md), og valget er begrundet i [ADR 0001](docs/adr/0001-local-voice-service-in-wsl.md).

![JARVIS Hermes dashboard](docs/screenshot.png)

## Sådan hænger det sammen

```text
Windows                                          WSL2 (Ubuntu, samme maskine)
───────────────────────────────────────          ─────────────────────────────────────
Browser  http://localhost:8730                   voice-service  127.0.0.1:8731
  │  mikrofon → optagelse                          ├─ /hear   Parakeet (Hearing)  ┐
  ▼                                                ├─ /speak  Kokoro (Speaking)   ├ CUDA
Dashboard  python server.py  ── localhost ──────▶  └─ /health                     ┘ RTX-kortet
  │
  ▼
Hermes CLI (din profil, dine tools)
```

- **Dashboardet** og **Hermes** kører native på Windows, som de altid har gjort. Dashboardet er ren Python uden afhængigheder.
- **Voice-servicen** kører i WSL2 i sit eget Python-miljø med torch, NeMo og Kokoro. Den indlæser begge modeller én gang ved start og holder dem varme.
- De taler sammen over localhost. WSL2 sender som standard `127.0.0.1` videre fra Windows til WSL.
- Der er ingen fallback. Er voice-servicen nede, viser dashboardet **VOICE OFFLINE**, og du kan stadig skrive til Jarvis.

En **Turn** er én udveksling: du taler, Jarvis hører det, Hermes svarer, og Jarvis siger svaret.

## Forudsætninger

- Windows 10 eller 11 med et NVIDIA-kort (udviklet til RTX 4070 med 12 GB) og en nyere NVIDIA-driver installeret **i Windows**.
- [Git for Windows](https://git-scm.com/download/win) og Python 3 på Windows (`python --version` i PowerShell).
- En Chromium-browser: Chrome, Edge eller Brave.
- Ca. 20 GB fri disk på C: til WSL: torch med CUDA, NeMo, Kokoro, pip-cache og modellerne. Tallet er et skøn.
- Internet første gang, til at hente pakker og modeller.

## 1. Hermes og dashboardet på Windows

### Hermes

Dashboardet starter Hermes' CLI direkte fra Windows, så Hermes skal være installeret **native på Windows** og kunne køres fra PowerShell. Det er ikke nok at have Hermes i WSL. Har du allerede en fungerende Hermes, kan du springe installationen over. Ellers installerer du Hermes Agent efter [Hermes' egen vejledning](https://hermes-agent.nousresearch.com/docs/) og kører `hermes setup`. Tjek i PowerShell, at Hermes svarer, før du går videre:

```powershell
hermes chat -q "Say online"
```

Ligger `hermes` ikke på PATH, så find den fulde sti med `where.exe hermes`. Den skal i `HERMES_CMD` nedenfor, **med `/` i stedet for `\`** (fx `HERMES_CMD=C:/Users/<dig>/AppData/Local/hermes/hermes.exe`). Dashboardet deler værdien op som en shell-kommando, så backslashes forsvinder, og en sti med mellemrum bliver delt op. Står Hermes i en mappe med mellemrum, så flyt den, eller læg mappen på PATH i stedet.

### Dashboardet

Klon repoet på Windows-siden, fx i din brugermappe. WSL bruger den samme mappe senere, så `.env` deles af dashboardet og voice-servicen.

```powershell
cd $HOME
git clone https://github.com/hidrow1337/jarvis-simon.git
cd jarvis-simon
copy .env.example .env
```

Åbn `.env` i en editor, og sæt `HERMES_CMD` hvis Hermes ikke ligger på PATH. Alle indstillinger er beskrevet under [Indstillinger](#indstillinger-env).

Start dashboardet for at se, at det kører:

```powershell
python server.py
```

Det skriver et banner og åbner <http://localhost:8730> i browseren:

```text
  JARVIS · Hermes Live HUD
  ──────────────────────────────────────────────
  brain        Hermes Agent (profile tools, skills, memory, MCP, browser integrations live)
  profile      default
  workdir      C:\Users\<dig>
  permission   normal
  voice        VOICE OFFLINE — start the voice-service · http://127.0.0.1:8731
  open         http://localhost:8730
```

`VOICE OFFLINE` er forventet indtil videre. Står der `brain  MOCK — Hermes CLI not reachable`, kan dashboardet ikke starte Hermes; se [Fejlsøgning](#hermes-svarer-ikke). Stop dashboardet med `Ctrl+C`.

Upstreams `install.sh` og `start.sh` i roden er bash-scripts til macOS og Linux. På Windows starter du dashboardet med `python server.py` som ovenfor.

## 2. WSL2 med CUDA og ffmpeg

### Installér WSL2 og Ubuntu

I PowerShell **som administrator**:

```powershell
wsl --install -d Ubuntu-24.04
```

Genstart, hvis Windows beder om det. Åbn derefter "Ubuntu 24.04" fra startmenuen, og opret en Linux-bruger. Tjek at distributionen kører som WSL **2**:

```powershell
wsl -l -v
```

`VERSION` skal være `2`. Hold WSL opdateret med `wsl --update`.

### GPU'en i WSL

Installér **ikke** en NVIDIA-driver inde i Ubuntu. I WSL2 kommer driveren fra Windows, og CUDA-delen af torch følger med voice-servicens installation. Tjek i Ubuntu-terminalen, at GPU'en kan ses:

```bash
nvidia-smi
```

Den skal vise dit kort (fx `NVIDIA GeForce RTX 4070`) og en CUDA-version. Får du `command not found` eller ingen GPU, så opdatér NVIDIA-driveren i Windows, kør `wsl --shutdown` i PowerShell, og prøv igen.

### ffmpeg og byggeværktøjer

I Ubuntu-terminalen:

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv python3-dev build-essential
ffmpeg -version
python3 --version
```

Voice-servicen bruger ffmpeg til at omkode browserens optagelse. NeMo kræver Python 3.10–3.12; Ubuntu 24.04 har 3.12.

## 3. Voice-servicen i WSL

### Installation

Windows-drevet ligger under `/mnt/c` i WSL. Gå til den samme mappe som dashboardet, og kør installationen. Har dit Windows-brugernavn et mellemrum, så sæt stien i anførselstegn: `cd "/mnt/c/Users/Fornavn Efternavn/jarvis-simon"`.

```bash
cd /mnt/c/Users/<dig>/jarvis-simon
voice_service/install.sh
```

Scriptet:

1. tjekker for `python3`, `ffmpeg` og byggeværktøjer og siger præcis hvilken `apt`-kommando der mangler,
2. viser hvilken GPU `nvidia-smi` ser,
3. opretter voice-servicens eget venv i `~/.venvs/jarvis-voice` (uden for `/mnt/c`, som er langsomt),
4. installerer torch med CUDA, NeMo og Kokoro. Det tager en del minutter,
5. henter Hearing model (Parakeet, ca. 2,5 GB) og Speaking model (Kokoro, ca. 330 MB) plus din Voice.

Når det er gået godt, slutter det med noget i retning af:

```text
  voice-service install · torch 2.x.x+cu128, CUDA available: NVIDIA GeForce RTX 4070
  ...
  voice-service install · done. Start it with: voice_service/start.sh
```

Står der `CUDA NOT available`, så se [CUDA ikke fundet](#cuda-ikke-fundet). Scriptet kan køres igen uden problemer; det genbruger venv'et.

### Start

```bash
voice_service/start.sh
```

Loggen viser hvert trin:

```text
  voice-service · loading Hearing model parakeet
  voice-service · device cuda (NVIDIA GeForce RTX 4070)
  voice-service · Hearing model parakeet-tdt-0.6b-v3 ready on cuda in … s
  voice-service · loading Speaking model kokoro (bm_george)
  voice-service · Speaking model Kokoro-82M ready on cuda in … s
  voice-service · GPU memory … of … GB in use
  voice-service · ready on http://127.0.0.1:8731 · device cuda
```

Servicen er klar, når linjen **`ready on http://127.0.0.1:8731`** kommer. Indtil da svarer den ikke, og dashboardet viser VOICE OFFLINE. Servicen nægter at starte uden CUDA, medmindre du selv har slået CPU til (se `JARVIS_VOICE_ALLOW_CPU`). Den lytter kun på `127.0.0.1`. `Ctrl+C` stopper den.

Tjek fra **PowerShell**, at Windows kan nå den:

```powershell
curl.exe http://127.0.0.1:8731/health
```

```json
{"ready": true, "hearing_model": "parakeet-tdt-0.6b-v3", "speaking_model": "Kokoro-82M", "voice": "bm_george", "device": "cuda"}
```

Virker det i WSL (`curl http://127.0.0.1:8731/health`) men ikke fra PowerShell, så se [WSL localhost-forwarding](#wsl-localhost-forwarding).

## 4. Smoke-testen

Smoke-testen tjekker begge rigtige modeller på GPU'en i én kørsel: Kokoro siger en sætning, og Parakeet hører lyden igen. Den indlæser sine egne modeller, så stop voice-servicen først (`Ctrl+C`), ellers ligger modellerne to gange i GPU-hukommelsen.

```bash
voice_service/start.sh roundtrip
voice_service/start.sh roundtrip "Shall I prepare the suit, sir?"
```

Uden tekst bruger den `Good evening, sir. All systems are online and ready.` Output:

```text
  voice-service · loading Hearing model parakeet
  ...
  voice-service · GPU memory 3.4 of 12.0 GB in use

  said:  'Good evening, sir. All systems are online and ready.'
  heard: 'Good evening, sir. All systems are online and ready.'
  Speaking 0.41 s · ffmpeg 0.05 s · Hearing 0.18 s
  match: heard word for word what was said
```

(Tallene er eksempler.) Sådan læser du det:

- **`GPU memory X of Y GB in use`**: hvor meget af kortet der er i brug med begge modeller indlæst. Tallet tæller alt på GPU'en, også fx browseren. Er der god luft op til `Y`, kan begge modeller ligge samtidig.
- **`said` / `heard`**: det Kokoro sagde, og det Parakeet hørte.
- **`Speaking … · ffmpeg … · Hearing …`**: tiden for hvert trin. Speaking og Hearing er størstedelen af ventetiden i en Turn; resten er Hermes' egen svartid.
- **`match`**: Parakeet hørte ord for ord det, der blev sagt (store og små bogstaver og tegnsætning tæller ikke). Exit-kode 0.
- **`MISMATCH`**: ordene er forskellige. Exit-kode 1. Små forskelle som `12` mod `twelve` kan give MISMATCH uden at noget er galt, så brug sætninger uden tal.

Vil du kun teste Hearing på en optagelse, du selv har lavet:

```bash
voice_service/start.sh hear min-optagelse.webm
```

Den printer transskriptionen og tiden for ffmpeg og Hearing. Filen kan være alt, ffmpeg kan læse.

## Daglig brug

Du skal bruge to vinduer: et WSL-terminalvindue til voice-servicen og et PowerShell-vindue til dashboardet. Rækkefølgen er ligegyldig; dashboardet opdager voice-servicen inden for 4 sekunder, uden reload.

**1. WSL (Ubuntu-terminalen):**

```bash
cd /mnt/c/Users/<dig>/jarvis-simon
voice_service/start.sh
```

Vent på `ready on http://127.0.0.1:8731`.

**2. Windows (PowerShell):**

```powershell
cd $HOME\jarvis-simon
python server.py
```

Browseren åbner <http://localhost:8730>. Øverst står `Local voice: Parakeet-tdt-0.6b-v3 / Kokoro-82M · bm_george`, og knappen hedder **◉ VOICE**.

**3. En samtale:**

1. Tryk **◉ VOICE**. Første gang spørger browseren om mikrofonen; tillad den for `localhost`.
2. Knappen skifter til **● VOICE LIVE**. Tal på engelsk.
3. Hold en kort pause, når du er færdig. Jarvis opdager stilheden, sender optagelsen til Hearing og viser i loggen `heard in …ms: "…"`.
4. Teksten går til Hermes, og svaret bliver sagt højt. Mens Jarvis taler, lytter den ikke, så den ikke hører sig selv. Lange svar bliver afkortet, før de bliver sagt.
5. Bagefter lytter Jarvis igen. Bliver der ikke hørt noget (støj, for kort optagelse), lytter den bare videre.
6. Tryk på knappen igen, eller tryk `Esc`, for at lukke samtalen. Kører Hermes stadig, afbryder `Esc` først det kørende svar.

🔊-knappen slår Speaking fra og til. Du kan altid skrive i feltet og sende med `Ctrl+Enter`, også mens voice-servicen er offline.

**4. Stop:** `Ctrl+C` i begge vinduer.

### Kommandoer

Alle knapper i kommandomatricen kører deres kommando med det samme. Kommandoer, der tager et argument, bliver stående klar, så den næste skrevne eller sagte sætning bliver til `/kommando argument`.

| Kommando | Gør |
|---|---|
| `/new` | Start en ny Hermes-tråd |
| `/clear` | Ryd svarpanelet (Hermes-sessionen fortsætter) |
| `/goal <text\|status\|clear>` | Sæt, læs eller ryd det stående mål |
| `/tools` | Kør `hermes tools list` |
| `/browser <task>` | Bed Hermes bruge sine browser-/Chrome-tools |
| `/background <mission>` | Kør en mission i baggrunden |
| `/mission [task]` | Læs eller tilføj til den lokale missionskø (`/kanban` gør det samme) |
| `/profile [note]` | Læs eller tilføj noter om dig, som Jarvis husker |
| `/personality <tone>` | Læs eller skift JARVIS' tone |
| `/commands` | Vis alle dashboard-kommandoer |
| `/toolsets` | Opsummér de aktive Hermes-toolsets |
| `/connectors` | Forklar hvordan integrationer arves fra Hermes |
| `/connect <name>` | Bed Hermes om vejledning til at forbinde en integration |
| `/status` | Vis runtime, profil og voice-servicens status |

Almindelig tekst og tale går direkte til Hermes.

### Hermes-profil og tools

Dashboardet bruger Hermes-profilen `default`, medmindre `HERMES_PROFILE` siger andet. Integrationer (Gmail, Notion, Slack osv.) forbindes i Hermes selv, ikke i dashboardet:

```powershell
hermes skills browse       # Gmail, Notion, Airtable, Google Workspace osv.
hermes tools               # indbyggede toolsets
hermes mcp list            # eksterne MCP-servere
hermes gateway setup       # Telegram, Slack, Discord, WhatsApp osv.
```

Genstart dashboardet eller brug `/new`, når du har ændret tools eller integrationer i Hermes.

## Indstillinger (`.env`)

`.env` ligger i repoets rod og læses af både dashboardet og voice-servicen (de bruger samme mappe). En variabel, der allerede er sat i miljøet, vinder over `.env`. Ændringer slår igennem, når du genstarter det, der bruger dem.

### Voice

| Indstilling | Default | Bruges af | Betydning |
|---|---|---|---|
| `JARVIS_VOICE_URL` | `http://127.0.0.1:8731` | begge | Hvor dashboardet finder voice-servicen. Voice-servicen lytter på portens nummer herfra, så skift porten her, hvis 8731 er optaget. |
| `JARVIS_VOICE` | `bm_george` | voice-service | Jarvis' Voice i Kokoro. Kun engelske Voices: `af_*`, `am_*` (amerikansk), `bf_*`, `bm_*` (britisk); `f` er kvinde, `m` er mand. Fx `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`. Se [Kokoros liste](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md). |
| `JARVIS_VOICE_ALLOW_CPU` | `0` | voice-service | `1` lader voice-servicen køre på CPU, når CUDA mangler. Det er langsomt og kun til fejlsøgning. |

**Skift Voice:** sæt fx `JARVIS_VOICE=bm_lewis` i `.env`, og genstart voice-servicen. En ny Voice hentes ved første start (kræver internet). En ukendt eller ikke-engelsk Voice stopper opstarten med en fejl, der siger hvorfor. Du kan prøve en Voice uden at ændre `.env`: `voice_service/start.sh roundtrip --voice bm_daniel`.

Til installation og start af voice-servicen kan du desuden sætte, i WSL-terminalen før kommandoen:

| Variabel | Default | Betydning |
|---|---|---|
| `JARVIS_VOICE_VENV` | `~/.venvs/jarvis-voice` | Hvor voice-servicens venv ligger. |
| `JARVIS_TORCH_CUDA` | `cu128` | Hvilket CUDA-build af torch `install.sh` installerer. |

### Dashboard og Hermes

| Indstilling | Default | Betydning |
|---|---|---|
| `HERMES_PROFILE` | `default` | Hermes-profilen, hvis tools, skills, hukommelse, browser og MCP-servere bruges. (`JARVIS_PROFILE` virker også.) |
| `HERMES_CMD` | `hermes` på PATH | Fuld kommando til Hermes, hvis den ikke ligger på PATH. Brug `/` i Windows-stier og ingen mellemrum (se [Hermes](#hermes)). |
| `JARVIS_WORKDIR` | `~` (i `.env.example`) | Hermes' arbejdsmappe. `~` er din brugermappe. Uden indstillingen er det mappen, dashboardet startes fra. |
| `JARVIS_PORT` | `8730` | Dashboardets port. |
| `JARVIS_OPEN` | `1` | `0` åbner ikke browseren ved start. |
| `JARVIS_TIMEOUT` | `120` | Sekunder Hermes må være tavs, før kørslen stoppes. |
| `JARVIS_PERMISSION` | `normal` | Vises i HUD'en og banneret. Hvad Hermes må uden at spørge, styres i Hermes selv. (`HERMES_PERMISSION` virker også.) |
| `JARVIS_MODEL` | Hermes' default | Model, der gives videre til Hermes med `--model`. |
| `HERMES_TOOLSETS` | alle | Begræns Hermes til bestemte toolsets (`--toolsets`). |
| `HERMES_SOURCE` | `jarvis-dashboard` | Kilden, Hermes registrerer kørsler under. |
| `JARVIS_RUNTIME` | `auto` | `auto` bruger Hermes, hvis den kan startes, ellers en mock. `hermes` eller `mock` tvinger det ene. |
| `JARVIS_STATE` | `state.json` i repoet | Fil til missionskø og mål. |
| `JARVIS_RAW_LOG` | (slået fra) | Sti til en log over rå prompts. Kun når du selv slår det til. Oprettes med rettigheder `0600`. |
| `JARVIS_VERBOSE` | (slået fra) | Sæt til noget for at logge hver HTTP-request i dashboardets terminal. |

## Fejlsøgning

### Hvor er problemet?

Tjek de tre dele hver for sig, i denne rækkefølge:

1. **Dashboardet:** kører `python server.py` stadig i PowerShell, og åbner <http://localhost:8730>? Svarer `curl.exe http://127.0.0.1:8730/api/status` med JSON? Hvis ikke, er det dashboardet (eller porten; se `JARVIS_PORT`).
2. **Hermes:** banneret siger `brain  Hermes Agent (…)`, og `/api/status` siger `"runtime": "hermes"`. Står der `MOCK` i banneret eller `Hermes offline` i HUD'en, er det Hermes; se [Hermes svarer ikke](#hermes-svarer-ikke).
3. **Voice-servicen:** står der `ready on http://127.0.0.1:8731` i WSL-terminalen, og svarer `curl.exe http://127.0.0.1:8731/health` fra PowerShell med `"ready": true`? Hvis ikke, er det voice-servicen eller forbindelsen mellem Windows og WSL.

Fejl i en Turn står i HUD'ens log: `Hearing failed: …` eller `Speaking failed: …` med voice-servicens egen begrundelse. Mere står i voice-servicens terminal.

### "VOICE OFFLINE"

Dashboardet kan ikke nå voice-servicens `/health`. Mulige årsager:

- Voice-servicen er ikke startet, eller den er ved at indlæse modellerne. Vent på `ready on …`.
- Den stoppede ved opstart. Læs den sidste linje i WSL-terminalen (`cannot start: …`).
- `JARVIS_VOICE_URL` peger på en anden port end den, servicen lytter på. Begge læser den samme `.env`; har du sat den i miljøet ét sted, så tjek begge.
- Windows kan ikke nå WSL på localhost; se næste afsnit.

Dashboardet tjekker igen hvert 4. sekund og når du trykker VOICE, så knappen bliver aktiv af sig selv, når servicen er oppe.

### WSL localhost-forwarding

Virker `curl http://127.0.0.1:8731/health` inde i WSL, men ikke `curl.exe http://127.0.0.1:8731/health` i PowerShell, så videresender WSL ikke localhost til Windows. Det styres af `%UserProfile%\.wslconfig`. Åbn filen, hvis den findes, og se på linjen `networkingMode` under `[wsl2]`:

- **Ingen `networkingMode`, eller `networkingMode=nat`** (standard): her virker localhost kun med `localhostForwarding`, som er slået til, medmindre filen slår den fra. Sørg for, at filen indeholder:

```ini
[wsl2]
localhostForwarding=true
```

- **Enhver anden værdi end `nat` eller `mirrored`**: localhost når ikke WSL. Fjern linjen (så bruges NAT med forwarding), eller skift til mirrored.
- **Mirrored** (Windows 11 22H2 og nyere): WSL deler Windows' netværk direkte, og `localhostForwarding` bruges ikke:

```ini
[wsl2]
networkingMode=mirrored
```

Kør derefter `wsl --shutdown` i PowerShell, åbn Ubuntu igen, og start voice-servicen på ny.

### CUDA ikke fundet

Voice-servicen stopper med `cannot start: CUDA is not available: torch sees no GPU`.

1. Kør `nvidia-smi` i WSL. Ser den ikke kortet: opdatér NVIDIA-driveren **i Windows**, kør `wsl --update` og `wsl --shutdown`, og prøv igen. Installér ikke en Linux-driver i Ubuntu.
2. Ser `nvidia-smi` kortet, men torch ikke, så tjek venv'et:

   ```bash
   ~/.venvs/jarvis-voice/bin/python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
   ```

   Står der `False`, eller mangler `+cu` i versionen, så installér venv'et forfra: `rm -rf ~/.venvs/jarvis-voice` og `voice_service/install.sh`. Er driveren for gammel til `cu128`, så opdatér den, eller vælg et andet build, fx `JARVIS_TORCH_CUDA=cu126 voice_service/install.sh`.
3. Vil du bare se servicen køre uden GPU, kan du sætte `JARVIS_VOICE_ALLOW_CPU=1`. Det bliver for langsomt til en rigtig samtale.

### Hermes svarer ikke

Banneret siger `MOCK — Hermes CLI not reachable`, eller HUD'en siger `Hermes offline`:

```powershell
where.exe hermes
hermes --version
hermes doctor
```

Virker `hermes` i PowerShell, men ikke i dashboardet, så sæt den fulde sti i `HERMES_CMD` i `.env`, og genstart dashboardet.

### Mikrofonen starter ikke

Loggen siger `mic blocked`: tillad mikrofonen for `localhost` i browserens webstedsindstillinger (ikonet til venstre for adressen), og tryk VOICE igen.

### Et nyligt forbundet tool mangler

Tjek `hermes tools list`, genstart dashboardet, og tryk `/new`.

### Andre fejl fra voice-servicen

| Besked | Løsning |
|---|---|
| `missing: … sudo apt install -y …` | Kør den viste `apt`-kommando, og kør `install.sh` igen. |
| `NeMo needs Python 3.10–3.12` | Brug Ubuntu 22.04 eller 24.04, hvis Python ligger i det interval. |
| `no venv at … — run voice_service/install.sh first` | Kør `voice_service/install.sh`, eller sæt `JARVIS_VOICE_VENV`, hvis venv'et ligger et andet sted. |
| `… is not an English Kokoro Voice` | Vælg en Voice, der starter med `af_`, `am_`, `bf_` eller `bm_`. |
| `env: 'bash\r': No such file or directory` | Scriptet har fået Windows-linjeskift. Repoet tvinger LF på `.sh`-filer, men en klon, der blev lavet før det, retter sig ikke selv ved `git pull`. Slet scripts og hent dem igen, i PowerShell i repoet: `Remove-Item *.sh, voice_service\*.sh; git checkout -- '*.sh'` |
| Indlæsningen stopper med `Killed` | WSL er løbet tør for RAM. Som standard får WSL halvdelen af maskinens RAM. Giv den mere med `memory=12GB` under `[wsl2]` i `%UserProfile%\.wslconfig`, og kør `wsl --shutdown`. |

## Sikkerhed

- Dashboardet binder kun til `127.0.0.1` og er ikke synligt på netværket. Det samme gælder voice-servicen, og begge afviser requests med en fremmed `Host`.
- Al lyd bliver på maskinen: Hearing og Speaking kører i voice-servicen på din egen GPU.
- Alle ændrende API-kald kræver et tilfældigt token pr. start, samme origin, gyldig localhost-host, godkendt content-type og begrænset størrelse.
- Hermes-kørsler køres én ad gangen, så flere faner ikke kan køre i den samme Hermes-session samtidig.
- Rå prompts logges ikke, medmindre `JARVIS_RAW_LOG` er sat. Logfilen oprettes med `0600` og beskyttelse mod symlinks.
- `.env`, `state.json` og Python-caches er udelukket fra Git. Sætter du `JARVIS_STATE` eller `JARVIS_RAW_LOG` til en fil i repoet, skal du selv holde den ude af Git.
- Dashboardet indeholder ingen nøgler til Google, Zapier, Gmail eller Hermes. Forbundne apps ejes og godkendes af din Hermes-profil.
- Gennemgå tredjeparts-skills og MCP-servere, før du installerer dem.

## For udviklere

Testene kører med Pythons standardbibliotek og ffmpeg, uden GPU, torch eller NeMo. De går gennem dashboardets HTTP-API mod en rigtig voice-service, hvor modellerne er erstattet af fakes og stubs:

```bash
python3 -m unittest
```

Vigtige filer:

```text
server.py        dashboardets lokale HTTP-API og NDJSON-streaming
runtime.py       Hermes CLI som subprocess, og sessionskontinuitet
commands.py      dashboardets slash-kommandoer og missionskø
voice.py         klient til den lokale voice-service (Hearing og Speaking)
voice_service/   voice-servicen: HTTP-server, modeller, install.sh og start.sh
persona.md       JARVIS' korte, talte persona
ui/              HUD i HTML/CSS/JavaScript uden afhængigheder
tests/           tests gennem dashboardets HTTP-API og voice-servicens kommandoer
```

## Credit og licens

Projektet er en kopi af [`Itsme23476/jarvis-hermes-dashboard`](https://github.com/Itsme23476/jarvis-hermes-dashboard), som igen er inspireret af [`Itsme23476/jarvis-os`](https://github.com/Itsme23476/jarvis-os). Den første commit er upstream-koden uændret, inklusive den oprindelige ElevenLabs- og browser-stemme. Den lokale stemme er bygget oven på.

Udgivet under MIT-licensen med upstreams copyright bevaret; se [LICENSE](LICENSE).
