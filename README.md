# J.A.R.V.I.S. — Local Desktop AI Assistant

<p align="center">
  <img src="assets/jarvis_banner.png" alt="J.A.R.V.I.S." width="900">
</p>

<p align="center">
  <b>“Just A Rather Very Intelligent System.”</b><br>
  An Iron Man themed, fully local, voice-or-text desktop assistant — powered by <a href="https://ollama.com">Ollama</a> — that really operates your PC.
</p>

---

## What it does

J.A.R.V.I.S. runs **entirely on your machine** (no cloud AI calls) and turns
plain English into real actions:

| You say | JARVIS does |
| --- | --- |
| *“open YouTube and watch Marques Brownlee”* | Finds the top match and opens its watch page in your browser |
| *“open Spotify, play my daily mix, then open my notes app”* | Chains all three steps, narrating each one |
| *“reply to this email saying I'll be there at 6”* | Reads the message selected in Outlook, drafts a reply, opens it for **your** review — and never presses Send |
| *“volume to 30%” · “pause it” · “next track”* | Media & volume control in whatever app is playing |
| *“set a 10 minute timer for the pizza”* | Spoken + on-screen reminder when it fires |
| *“summarise this article”* (with a URL) | Fetches the page text, reads back a summary |
| *“open my resume file and tell me what's missing”* | Asks your explicit confirmation first, then reads and analyses |
| *“log in to my bank…”* | **Refuses. Always.** (see Guardrails) |

Follow-ups work: *“now pause it”*, *“make it louder”*, *“the third one”*.

## The .exe

Two standalone Windows binaries are built automatically by GitHub Actions
(**no Python required on your PC**):

| File | Contents |
| --- | --- |
| **JARVIS-AI.exe** | Full build — bundles Whisper-class offline speech recognition (larger download) |
| **JARVIS-AI-Lite.exe** | Lite build — uses Windows' built-in speech recognition (smaller) |

**Where to get it**

1. **Releases page** → [`nightly` release](../../releases) — run the workflow
   *Build JARVIS-AI.exe* (Actions tab → *Run workflow*) to publish it there.
2. **Actions tab** → latest green run → *Artifacts* — download directly from
   any build.

Prefer to build it yourself? One double-click: `build_exe.bat` (see below).

## Quick start

1. **Install [Ollama](https://ollama.com/download)** on the PC you want to
   control and pull a model:
   ```bash
   ollama pull qwen3:8b        # smartest small brain for commands (default)
   ```
2. **Download `JARVIS-AI.exe`** and double-click it.
3. **The first-run wizard** checks Ollama, lets you pick/pull a model, tests
   your microphone and voice (pick a British voice for the full effect), and
   confirms the safety limits.
4. **Talk to Jarvis.** Type a command, or hold **🎤 HOLD TO TALK** and speak.

> The setup wizard also lives in the menu bar → *Run setup wizard…* at any time.

## Which model makes Jarvis smart?

The assistant is only as sharp as the local model behind it. Swap any time in
**☰ → Configuration → Local model tag** (then talk again — no restart needed).

| Your hardware | Pull this | Jarvis-level |
| --- | --- | --- |
| **8 GB+ RAM / any GPU** | `ollama pull qwen3:8b` | **Recommended.** Sharp tool use, reliable chains — the default |
| **12 GB+ GPU** | `ollama pull qwen3:14b` | Noticeably smarter planning, slower |
| Weak / old PC | `ollama pull llama3.2` | Fastest, but expect more mistakes |
| Pure tool reliability | `ollama pull llama3-groq-tool-use:8b` | Purpose-built function-caller |
| Beast (24 GB+ GPU) | `ollama pull qwen3:30b-a3b` | Big-model behaviour, small-model speed |

*(`qwen3:8b` needs roughly 6–8 GB of RAM/VRAM in use. `llama3.2` — what early
builds shipped with — is a 3B-speed model and is the usual cause of "the AI is
dumb".)*

## Example commands

```
open youtube and play Marques Brownlee
open the latest video from Linus Tech Tips
search the web for best mechanical keyboards
open chrome, then open gmail
open notepad and type "meeting notes: budget approved"
reply to this email saying the report is attached and I'll call at 4
compose an email to alex@example.com subject "Lunch?" body "Sushi at 1?"
pause it          /  volume to 20%  /  mute
set a 25 minute timer called tea
remind me at 17:30 to call the dentist
read C:\Users\me\Documents\report.txt and summarise it
screenshot
what's my system status?
```

**Voice:** hold the mic button (or hold it and speak — release to send).
**Stop anything instantly:** the red **STOP** button, **Esc**, or the
*Abort automation* tray item.

## Power & privacy controls — you are always in charge

JARVIS is **never always-listening**. The microphone only opens while you
actively hold the talk control; nothing runs in the background waiting for
speech.

| Shortcut | Action |
| --- | --- |
| **Ctrl+Alt+P** | **Master standby / wake — disable JARVIS instantly.** Kills the mic, silences speech and halts any running automation until pressed again |
| **Ctrl+Alt+Space** | Hold to talk (works from any app) |
| **Ctrl+Alt+J** | Show / hide the HUD window |
| **Esc** (or STOP button) | Abort the current action chain immediately |
| **Ctrl+Q** | Quit J.A.R.V.I.S. completely |

The same controls live in the **☰ J.A.R.V.I.S.** menu (top-left), including
an *enabled* checkbox equal to Ctrl+Alt+P. While in standby the arc reactor
goes dark, the mic button locks, and commands are refused. The system-tray
icon keeps *Abort automation* and *Exit* one click away.

## Guardrails — enforced in code, not just in the prompt

These are hard limits in the executor layer. The model cannot route around
them because *there is no tool that can*:

- ❌ **Never logs in, signs up or authenticates** anywhere — requests are
  refused before the model is even consulted.
- ❌ **Never enters, stores or handles** passwords, PINs, 2FA codes, card
  numbers, API keys — any credential-looking payload is blocked from tool
  arguments too.
- ❌ **Never touches credential stores** — SSH keys, browser login data,
  `.env` files, wallets etc. are hard-blocked paths.
- ⛔ **Destructive/irreversible actions** (deleting files, closing apps,
  writing files, anything touching personal folders) require **explicit
  on-screen confirmation**. File deletion additionally requires you to *type*
  `DELETE` — and goes to the Recycle Bin, never permanent.
- ⌨️ **Smart typing confirmations** — everyday on-screen input just happens:
  searches, song names, YouTube channels, pressing Enter, clicking result
  rows to finish a task. Confirmation is requested only for *private or
  crucial* text (long or multi-line messages, emails) and destructive click
  labels (delete, buy, send…). Strict mode (Settings) restores
  confirm-everything.
- ✉️ **Email is draft-only.** JARVIS prepares the reply in your already-signed-in
  Outlook and displays it. *You* press Send.
- 👁️ **All automation is visible** — typed keys, opened windows, narrated
  steps. No silent background control.
- 🎯 **media_play**: “play X on Spotify/YouTube” runs as ONE verified ritual — focus the app, wait for it to load, search, read the on-screen results, and click the row that actually matches the song/artist/channel (never a random first song or bare Play button); if nothing matches it shows what it saw and retries smarter instead of giving up.
- 🔁 **Self-repairing plans**: if the local model emits slightly broken JSON, JARVIS repairs it and runs the intended actions instead of dumping raw text; `focus_window` switches between your apps visibly, in real time.
- 🛑 **Abort** is always one click/keypress away.

Sensitive confirmation dialogs show exactly what will happen *before* it
happens. Strict mode (Settings) asks before *every* action.

## Privacy

- Everything runs locally: Ollama for reasoning, Windows SAPI / Whisper for
  voice — no cloud AI, no telemetry.
- Settings, conversation memory and the activity log live in
  `%LOCALAPPDATA%\JARVIS\` and never leave the machine.
- The only network traffic is what the assistant does **on your behalf** in
  the browser (opening sites, fetching a page you asked it to read) and
  talking to `localhost:11434`.

## Interface

The HUD is styled after the JARVIS / Stark Industries displays: an animated
**arc reactor** whose colour tracks state (blue = idle, green = listening,
gold = thinking, cyan = executing, red = blocked), a dialogue panel, a live
activity/telemetry log, and always-visible STOP controls. System tray icon,
always-on-top toggle, global hotkey **Ctrl+Alt+J** to show/hide.

States: `LISTENING → PROCESSING → EXECUTING → RESPONDING`, with `BLOCKED`
whenever a guardrail refuses something.

## Project layout

```
main.py                  entry point (also the PyInstaller target)
JARVIS.spec              one-file build spec
build_exe.bat            one-click Windows build
jarvis/
  store.py               settings, activity log, reminders, session memory
  persona.py             JARVIS character + rules + output format
  ollama_client.py       local Ollama API (chat / tags / pull)
  brain.py               conversation + structured action-plan parsing
  guardrails.py          the hard safety layer (policies, deny-lists)
  executor.py            plan → confirmed, narrated tool execution
  app.py                 controller wiring everything together
  voice.py               TTS (SAPI) + STT (Whisper / Windows speech)
  skills/                the ONLY capabilities: web, youtube, apps, media,
                         email (draft-only), files, timers, memory, system
  ui/                    Iron Man HUD, arc reactor, wizard, tray
scripts/make_icon.py     PNG → multi-res .ico
tests/test_smoke.py      guardrails & core smoke tests
.github/workflows/       builds JARVIS-AI.exe on Windows (PyInstaller)
```

## Building from source

```bat
build_exe.bat          :: full build  -> dist\JARVIS-AI.exe
build_exe.bat lite     :: lite build  -> dist\JARVIS-AI-Lite.exe
```

Requirements: Windows 10/11, Python 3.11+. The scripts install dependencies
and PyInstaller for you. Equivalent manual steps:

```bat
pip install -r requirements-full.txt
pip install pyinstaller
python scripts\make_icon.py
pyinstaller JARVIS.spec --noconfirm --clean
```

CI does exactly this on `windows-latest` for every push — see
`.github/workflows/build-exe.yml`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| **The .exe won't open / nothing happens** | 1) Right-click the exe → **Properties** → tick **Unblock** → Apply (Windows marks downloads as unsafe). 2) If you see *"Windows protected your PC"* → **More info → Run anyway**. 3) Check **Windows Security → Protection history** — antivirus tools false-positive on app-automation code; allow it or add this folder as an exclusion. 4) Run **JARVIS-Doctor.bat** (next to the exe) — it explains and diagnoses everything. |
| Error dialog on startup | The dialog shows the exact failure. `JARVIS-CRASH.txt` is saved next to the exe and `%LOCALAPPDATA%\JARVIS\logs\boot.log` has the full boot trace — send me either. |
| *“Ollama is not responding”* | Start Ollama (system tray / `ollama serve`), or press **START OLLAMA** in the wizard. Check `http://localhost:11434`. |
| *“The model … is not installed”* | `ollama pull llama3.2` — or pick another model in *Configuration*. |
| No voice input | Check Windows microphone privacy settings (*Settings → Privacy → Microphone*). Lite build needs Windows speech recognition (add a speech language pack if dictation returns nothing). |
| JARVIS refuses a reasonable request | By design it refuses logins, credentials and destructive acts. Rephrase, or do that part yourself. |
| An action needed confirmation and timed out | It is treated as declined — just ask again. |
| The exe won't start | Install the [VC++ 2015-2022 x64 redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) (normally already present). Then run **JARVIS-Doctor.bat** and follow section 7. |
| Everything else | `%LOCALAPPDATA%\JARVIS\logs\jarvis.log` — and the Activity Log panel in the HUD. |

## Commands the assistant will never run

Logging in · signing up · entering passwords/PINs/card data · touching
SSH keys, password stores, `.env`/wallet files · sending email · deleting
anything permanently · uninstalling software · silent background control ·
running shell commands or arbitrary code (there is no such capability).

---

*Built with the original project brief in [`jarvis_ai_prompt.txt`](jarvis_ai_prompt.txt).
Runs fully locally. Powered by Ollama. Sometimes, you gotta run before you can walk.*
