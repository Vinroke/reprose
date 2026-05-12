# Repose Storyteller
### Offline AI-assisted fiction writing — powered by Ollama

---

## What it is

Repose Storyteller is a local, offline writing tool built around the three-continuation workflow popularised by Dreamily. Write prose, generate three continuation options, pick the one that fits, keep going. No subscription. No cloud. Nothing leaves your machine.

It runs entirely in your browser, served locally. Your writing is stored in your browser's local storage and never transmitted anywhere.

---

## What you need

- **Python** — https://www.python.org/downloads/
  Windows users: tick **Add Python to PATH** during installation.
- **Ollama** — https://ollama.com/download
  The launcher will open this page automatically if Ollama isn't found.
- **A pulled model** — the launcher will offer recommended options on first run.

---

## Getting started

1. Put `reprose-1_0-flare-inline-fix.html`, `reprose_launcher_tkinter.py`, and this README in the same folder.
2. Run `reprose_launcher_tkinter.py` — double-click on Windows, or `python3 reprose_launcher_tkinter.py` on Linux/macOS.
3. The launcher checks Ollama, starts a local server, and opens your browser.
4. Select a model from the dropdown and start writing.

If no models are installed, the launcher will walk you through pulling one.

---

## Basic workflow

- Write or paste prose into the editor. Bold, italic, and underline apply real formatting.
- Hit **Generate Flares** (or Ctrl+Enter) to produce three continuation options.
- Read them, accept the one you want — it inserts at your cursor position.
- Individual flares can be refreshed or pinned independently.
- The seed field steers where each flare begins. The instruction field nudges tone, pacing, or direction without becoming part of the document.
- Instruction presets let you save and recall common directions in one click.
- POV voice profiles let you define a character's grammar and register — the active profile is injected at generation time, not stored in the prose.
- The system prompt establishes world context, tone, and content permissions persistently across all generations.

---

## Themes

Oak (default), Dark, Aero, and Aqua are built in. Aqua is the most visually distinct — raised gel buttons, pinstripe chrome — and is easiest on the eyes during long sessions. All themes can be further customised via the Stylish browser extension targeting `localhost:8787`.

---

## Saving and backup

Repose Storyteller autosaves to browser local storage. **This is not a substitute for backups.** Use **Export Snapshot** regularly — it saves a full JSON backup of all projects to a file you control. Browser storage can be cleared without warning under low-disk conditions.

Individual chapters and full manuscripts can be exported as `.txt` at any time.

---

## Models

The launcher offers a curated selection on first run. For fiction writing, models with reduced content restrictions (such as Dolphin Mistral) will produce fewer mid-generation refusals than their vanilla equivalents. The repeat penalty and system prompt controls in the AI settings row are your primary tools for managing generation behaviour.

Repose Storyteller is designed for Ollama running locally. Cloud API integration (Claude, GPT, Gemini) is not supported and will not be added. If you want that, there are other tools better suited to it.

---

## A note on hardware

Generation speed depends entirely on your GPU. A 4GB VRAM card running a 7–8B model is the realistic floor for a usable experience. Anything less is technically functional in the same sense that a bicycle is technically a vehicle.

---

## Known limitations

- No epub export — use Calibre on the exported `.txt` file. It will do a better job anyway.
- No cloud sync, no mobile support, no collaboration features. This is intentional.



*Built out of frustration with RLHF refusals mid-scene. Grew somewhat.*
