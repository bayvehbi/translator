# OCR Translator

OCR-based language learning overlay for Windows. Captures any region of your screen, reads the text, and shows the translation + word-by-word breakdown in an always-on-top overlay. Designed for reading French or English content while learning.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **Screen region capture** — F8 to select a region, F10 for full screen
- **Word at cursor** — F9 translates the nearest word to your cursor
- **Two translation backends** — Google Translate or OpenAI LLM (toggle with Ctrl+L)
- **Word-by-word breakdown** — follows the original sentence structure
- **Clickable words** — click any word in the original text to see its context-aware meaning (pre-fetched, no extra API call on click)
- **Pronunciation** — click a word to hear it, or press ▶ to read the full sentence (gTTS)
- **Tips & tricks** — short language learning notes per scan (toggleable via `detailed_mode` in config)
- **Word history** — panel below the overlay sorted by lookup frequency
- **Configurable languages** — choose source (FR/EN) and target (EN/TR) on startup
- **Custom triggers** — remap F8/F9 to any key, mouse button, or scroll (Ctrl+F8 / Ctrl+F9)
- **Always-on-top** — translucent overlay, draggable, right-click to close

## Quick Start

### Run from Source

1. Clone and install dependencies:
   ```bash
   git clone https://github.com/yourusername/ocr-translator.git
   cd ocr-translator
   pip install -r requirements.txt
   ```

2. Run:
   ```bash
   python main.py
   ```

3. On startup, select your source and target language, then use the keys below.

## Controls

| Key | Action |
|-----|--------|
| `F8` | Set region corners (press twice: top-left, then bottom-right) |
| `F9` | Translate word at cursor |
| `F10` | Capture and translate full screen |
| `Ctrl+L` | Toggle translation backend (LLM / Google) |
| `Ctrl+F8` | Remap region trigger to any key/mouse/scroll |
| `Ctrl+F9` | Remap word trigger to any key/mouse/scroll |
| `Right-click` | Close the application |

## Configuration

Edit `config.json` next to the executable:

```json
{
  "openai_api_key": "sk-...",
  "openai_model": "gpt-4o-mini",
  "use_llm": true,
  "detailed_mode": true
}
```

| Key | Description |
|-----|-------------|
| `use_llm` | Use OpenAI instead of Google Translate |
| `detailed_mode` | Show tips & tricks section (requires `use_llm`) |
| `openai_model` | Any OpenAI chat model |

## Building

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole main.py
```

## Requirements

- Windows 10/11
- Python 3.11+
- Internet connection (for translation and TTS)
- OpenAI API key (optional, for LLM mode)

## Dependencies

- `easyocr` — OCR engine
- `deep-translator` — Google Translate backend
- `openai` — LLM translation backend
- `gtts` + `pygame` — text-to-speech pronunciation
- `mss` + `pillow` — screen capture
- `pynput` — global keyboard/mouse input
- `tkinter` — GUI (included with Python)

## License

MIT
