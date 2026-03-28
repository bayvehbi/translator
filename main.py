"""
Screen OCR & Translate — ultra‑simple, always‑on‑top UI

How it works:
- Press F8 to set top-left corner (where mouse cursor is)
- Press F8 again to set bottom-right corner (where mouse cursor is)
- Translation starts automatically
- Results appear in the always‑on‑top window as "original : translation"

NEW FEATURE - Word Translation:
- Press F9 to translate the nearest word at cursor position
- Uses smart OCR with word boundary detection

Keys:
- Press  F8  to set corners (first = top-left, second = bottom-right)
- Press  F9  to translate word at cursor position
- Press  Esc  to close application
"""
from __future__ import annotations

import threading
import math
import re
import os
import json
from dataclasses import dataclass
from typing import List, Tuple, Optional

import tempfile
import tkinter as tk
import numpy as np
from PIL import Image, ImageGrab
import mss
import easyocr
from pynput import mouse, keyboard
from deep_translator import GoogleTranslator
from openai import OpenAI
try:
    from gtts import gTTS
    import pygame
    pygame.mixer.init()
    TTS_AVAILABLE = True
except Exception:
    TTS_AVAILABLE = False


# ---------------- Configuration ---------------- #
def load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

CONFIG = load_config()

TARGET_LANG      = "tr"
TARGET_LANG_NAME = "Turkish"
OCR_LANGS      = ['en']
READER: easyocr.Reader = None
USE_LLM        = CONFIG.get("use_llm", False)
DETAILED_MODE  = CONFIG.get("detailed_mode", True)
OPENAI_CLIENT: OpenAI = None
OPENAI_MODEL   = CONFIG.get("openai_model", "gpt-4o-mini")


def speak(text: str):
    """Play TTS audio for the given text using the source language."""
    if not TTS_AVAILABLE or not text:
        return
    lang = 'fr' if 'fr' in OCR_LANGS else 'en'
    def _play():
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name
                tts.write_to_fp(f)
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
            os.remove(tmp_path)
        except Exception as e:
            print(f"TTS error: {e}")
    threading.Thread(target=_play, daemon=True).start()


def word_by_word(text: str, translated: str = "") -> str:
    """
    Word-by-word mapping.
    If LLM is active: single call asking which target word each source word maps to
    (contextual, matches the actual translation).
    Otherwise: translate each word individually with Google Translate.
    """
    if USE_LLM and translated:
        global OPENAI_CLIENT
        if OPENAI_CLIENT is None:
            api_key = CONFIG.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return ""
            OPENAI_CLIENT = OpenAI(api_key=api_key)
        prompt = (
            f"Source: \"{text}\"\n"
            f"Translation: \"{translated}\"\n\n"
            f"Map each source word to its {TARGET_LANG_NAME} equivalent as used in this sentence (context-aware). "
            f"Keep the same word order as the source. Output one line only, no extra text:\n"
            f"word1→anlam1  word2→anlam2  word3→anlam3"
        )
        try:
            response = OPENAI_CLIENT.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return ""
    else:
        words = text.split()[:20]
        parts = []
        for w in words:
            clean = re.sub(r'[^a-zA-ZÀ-ÿ]', '', w)
            if not clean:
                continue
            try:
                t = GoogleTranslator(source="auto", target=TARGET_LANG).translate(clean)
                parts.append(f"{clean}→{t}")
            except Exception:
                parts.append(clean)
        return '  '.join(parts)


def get_tip(text: str, translated: str) -> str:
    """Returns a short tip/trick in the target language. Only called when DETAILED_MODE and USE_LLM."""
    global OPENAI_CLIENT
    if OPENAI_CLIENT is None:
        api_key = CONFIG.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return ""
        OPENAI_CLIENT = OpenAI(api_key=api_key)
    is_single_word = len(text.split()) == 1
    if is_single_word:
        prompt = (
            f"Word: \"{text}\" → {TARGET_LANG_NAME}: \"{translated}\"\n"
            f"Write a very short tip to help remember this word (in {TARGET_LANG_NAME}, 1-2 sentences max). "
            f"Can be etymology, memory trick, or an interesting connection. No labels."
        )
    else:
        prompt = (
            f"Text: \"{text}\"\n"
            f"{TARGET_LANG_NAME} translation: \"{translated}\"\n"
            f"Write a very short language tip or trick about this text (in {TARGET_LANG_NAME}, 1-2 sentences max). "
            f"Can be a pattern, common usage, or grammar note. No labels."
        )
    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def fetch_all_word_meanings(sentence: str) -> dict:
    """One LLM call: returns {word: meaning_in_target_lang} for every word in the sentence."""
    global OPENAI_CLIENT
    if OPENAI_CLIENT is None:
        api_key = CONFIG.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return {}
        OPENAI_CLIENT = OpenAI(api_key=api_key)
    prompt = (
        f"Sentence: \"{sentence}\"\n\n"
        f"For each word in this sentence, give its context-aware {TARGET_LANG_NAME} meaning. "
        f"Write exactly in this format, nothing else:\n"
        f"word: meaning\n\n"
        f"Include all words: conjunctions, prepositions, articles, etc."
    )
    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        result = {}
        for line in response.choices[0].message.content.strip().splitlines():
            if ':' in line:
                word, _, meaning = line.partition(':')
                result[word.strip().lower()] = meaning.strip()
        return result
    except Exception:
        return {}


def translate(text: str) -> str:
    """Translate text to TARGET_LANG using the active backend."""
    if USE_LLM:
        global OPENAI_CLIENT
        if OPENAI_CLIENT is None:
            api_key = CONFIG.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return "Error: set openai_api_key in config.json"
            OPENAI_CLIENT = OpenAI(api_key=api_key)
        response = OPENAI_CLIENT.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": f"Translate to {TARGET_LANG_NAME}. Return only the translation, nothing else."},
                {"role": "user",   "content": text},
            ],
            temperature=0,
        )
        return response.choices[0].message.content.strip()
    else:
        return GoogleTranslator(source="auto", target=TARGET_LANG).translate(text)


@dataclass
class Selection:
    x1: int
    y1: int
    x2: int
    y2: int


# ---------------- Word Translation Classes ---------------- #
@dataclass
class WordInfo:
    """Information about a detected word."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0


@dataclass
class TranslationResult:
    """Result of word translation."""
    original_word: str
    translated_word: str
    confidence: float
    position: Tuple[int, int]
    success: bool
    error_message: Optional[str] = None


class WordDetector:
    """Detects words from OCR data and finds word boundaries."""
    
    def __init__(self):
        self.min_word_length = 2
        self.max_word_length = 50
        self.word_pattern = r'[a-zA-ZÀ-ÿ]+'
        
    def extract_words_from_easyocr(self, results: list) -> List[WordInfo]:
        """Extract word information from EasyOCR results."""
        words = []
        try:
            for bbox, text, conf in results:
                # bbox = [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
                x = int(bbox[0][0])
                y = int(bbox[0][1])
                width  = int(bbox[1][0]) - x
                height = int(bbox[2][1]) - y
                conf_pct = conf * 100

                for word_text in text.split():
                    word_text = word_text.strip()
                    if (self.min_word_length <= len(word_text) <= self.max_word_length and
                            re.search(self.word_pattern, word_text)):
                        words.append(WordInfo(
                            text=word_text,
                            x=x, y=y,
                            width=width, height=height,
                            confidence=conf_pct
                        ))
        except Exception as e:
            print(f"Error extracting words from EasyOCR: {e}")
        return words
    
    def find_nearest_word(self, words: List[WordInfo], cursor_x: int, cursor_y: int) -> Optional[WordInfo]:
        """Find the word closest to the cursor position."""
        if not words:
            return None
            
        min_distance = float('inf')
        nearest_word = None
        
        for word in words:
            # Calculate distance from cursor to word center
            word_center_x = word.x + word.width // 2
            word_center_y = word.y + word.height // 2
            
            distance = math.sqrt(
                (cursor_x - word_center_x) ** 2 + 
                (cursor_y - word_center_y) ** 2
            )
            
            # Also check if cursor is within word bounds (closer distance)
            if (word.x <= cursor_x <= word.x + word.width and
                word.y <= cursor_y <= word.y + word.height):
                distance = 0  # Cursor is inside the word
                
            if distance < min_distance:
                min_distance = distance
                nearest_word = word
                
        return nearest_word


class SimpleRegionCapture:
    """Simple region capture - just get a big area around cursor."""
    
    def __init__(self):
        self.region_size = 400  # Big area around cursor
        
    def capture_big_region_around_cursor(self, cursor_x: int, cursor_y: int) -> Tuple[int, int, int, int, Image.Image]:
        """Capture a big region around cursor and return bounds + image."""
        # Calculate region bounds
        half_size = self.region_size // 2
        left = max(0, cursor_x - half_size)
        top = max(0, cursor_y - half_size)
        right = cursor_x + half_size
        bottom = cursor_y + half_size
        
        try:
            # Capture the region
            with mss.mss() as sct:
                monitor = {
                    "top": top,
                    "left": left,
                    "width": right - left,
                    "height": bottom - top
                }
                screenshot = sct.grab(monitor)
                image = Image.frombytes('RGB', (screenshot.width, screenshot.height), screenshot.rgb)
                
            return left, top, right, bottom, image
                
        except Exception as e:
            print(f"Region capture error: {e}")
            return None, None, None, None, None


class WordTranslator:
    """Simple word translation - capture big area and find closest word."""
    
    def __init__(self):
        self.min_confidence = 30  # Minimum OCR confidence
        self.word_detector = WordDetector()
        self.region_capture = SimpleRegionCapture()
    
    def translate_word_at_cursor(self, cursor_x: int, cursor_y: int) -> TranslationResult:
        """Main method to translate word at cursor position."""
        try:
            # Capture big region around cursor
            left, top, right, bottom, image = self.region_capture.capture_big_region_around_cursor(cursor_x, cursor_y)
            if image is None:
                return TranslationResult(
                    original_word="",
                    translated_word="",
                    confidence=0.0,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message="Failed to capture screen region"
                )
            
            # Process with OCR
            try:
                results = READER.readtext(np.array(image))
                words = self.word_detector.extract_words_from_easyocr(results)
                
            except Exception as e:
                return TranslationResult(
                    original_word="",
                    translated_word="",
                    confidence=0.0,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message=f"OCR processing failed: {e}"
                )
            
            if not words:
                return TranslationResult(
                    original_word="",
                    translated_word="",
                    confidence=0.0,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message="No words detected in region"
                )
            
            # Adjust word positions to screen coordinates
            for word in words:
                word.x += left  # Adjust to screen coordinates
                word.y += top   # Adjust to screen coordinates
            
            # Find nearest word to cursor
            nearest_word = self.word_detector.find_nearest_word(words, cursor_x, cursor_y)
            if nearest_word is None:
                return TranslationResult(
                    original_word="",
                    translated_word="",
                    confidence=0.0,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message="No suitable word found near cursor"
                )
            
            # Check confidence threshold
            if nearest_word.confidence < self.min_confidence:
                return TranslationResult(
                    original_word=nearest_word.text,
                    translated_word="",
                    confidence=nearest_word.confidence,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message=f"Word confidence too low: {nearest_word.confidence}%"
                )
            
            # Translate the word
            try:
                translated = translate(nearest_word.text)
                return TranslationResult(
                    original_word=nearest_word.text,
                    translated_word=translated,
                    confidence=nearest_word.confidence,
                    position=(cursor_x, cursor_y),
                    success=True
                )
            except Exception as e:
                return TranslationResult(
                    original_word=nearest_word.text,
                    translated_word="",
                    confidence=nearest_word.confidence,
                    position=(cursor_x, cursor_y),
                    success=False,
                    error_message=f"Translation failed: {e}"
                )
                
        except Exception as e:
            return TranslationResult(
                original_word="",
                translated_word="",
                confidence=0.0,
                position=(cursor_x, cursor_y),
                success=False,
                error_message=f"Unexpected error: {e}"
            )


class CaptureController:
    """Handles global keyboard and mouse input for screen capture and word translation."""

    def __init__(self, on_region_ready, on_word_translate, on_wait_for_key):
        self.on_region_ready  = on_region_ready
        self.on_word_translate = on_word_translate
        self.on_wait_for_key  = on_wait_for_key
        self._lock = threading.Lock()
        self._points = []

        self._ctrl_pressed = False
        # 'region', 'word', or None
        self._waiting_mode: Optional[str] = None
        # custom keys (keyboard key object or "mouse_X" / "mouse_scroll_X" string)
        self._custom_region_key = None
        self._custom_word_key   = None

        self._kb_listener    = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click, on_scroll=self._on_mouse_scroll)
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self):
        self._kb_listener.stop()
        self._mouse_listener.stop()

    # ---- helpers ----

    def _notify(self, msg):
        threading.Thread(target=self.on_wait_for_key, args=(msg,), daemon=True).start()

    def _do_region(self):
        import win32gui
        x, y = win32gui.GetCursorPos()
        with self._lock:
            self._points.append((x, y))
            if len(self._points) == 2:
                (x1, y1), (x2, y2) = self._points
                x_left, x_right = sorted([x1, x2])
                y_top, y_bottom  = sorted([y1, y2])
                sel = Selection(x_left, y_top, x_right, y_bottom)
                threading.Thread(target=self.on_region_ready, args=(sel,), daemon=True).start()
                self._points.clear()

    def _do_word(self):
        import win32gui
        x, y = win32gui.GetCursorPos()
        threading.Thread(target=self.on_word_translate, args=(x, y), daemon=True).start()

    def _do_fullscreen(self):
        import tkinter as tk
        root = tk.Tk()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        sel = Selection(0, 0, w, h)
        threading.Thread(target=self.on_region_ready, args=(sel,), daemon=True).start()

    def _capture_key(self, key_val):
        """Assign key_val to the current waiting mode and notify."""
        mode = self._waiting_mode
        self._waiting_mode = None
        if mode == 'region':
            self._custom_region_key = key_val
            self._notify(f"Region key mapped to: {key_val}")
        else:
            self._custom_word_key = key_val
            self._notify(f"Word key mapped to: {key_val}")

    # ---- listeners ----

    def _on_key_press(self, key):
        try:
            if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._ctrl_pressed = True
                return True

            # Ctrl+F8 → start mapping region key
            if key == keyboard.Key.f8 and self._ctrl_pressed:
                self._waiting_mode = 'region'
                self._notify("Press any key / click / scroll to use as region trigger...")
                return True

            # Ctrl+F9 → start mapping word key
            if key == keyboard.Key.f9 and self._ctrl_pressed:
                self._waiting_mode = 'word'
                self._notify("Press any key / click / scroll to use as word trigger...")
                return True

            # Capture key if in waiting mode (ignore bare Ctrl)
            if self._waiting_mode:
                self._capture_key(key)
                return True

            # Fire region action
            region_trigger = self._custom_region_key or keyboard.Key.f8
            if key == region_trigger:
                self._do_region()
                return True

            # Fire word action
            word_trigger = self._custom_word_key or keyboard.Key.f9
            if key == word_trigger:
                self._do_word()
                return True

            # F10 → full screen
            if key == keyboard.Key.f10:
                self._do_fullscreen()
                return True

        except Exception:
            pass
        return True

    def _on_key_release(self, key):
        try:
            if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._ctrl_pressed = False
        except Exception:
            pass
        return True

    def _on_mouse_click(self, x, y, button, pressed):
        try:
            if not pressed:
                return True
            btn_key = f"mouse_{button.name}"

            if self._waiting_mode:
                self._capture_key(btn_key)
                return True

            if self._custom_region_key == btn_key:
                self._do_region()
            elif self._custom_word_key == btn_key:
                self._do_word()
        except Exception:
            pass
        return True

    def _on_mouse_scroll(self, x, y, dx, dy):
        try:
            scroll_key = f"mouse_scroll_{'up' if dy > 0 else 'down'}"

            if self._waiting_mode:
                self._capture_key(scroll_key)
                return True

            if self._custom_region_key == scroll_key:
                self._do_region()
            elif self._custom_word_key == scroll_key:
                self._do_word()
        except Exception:
            pass
        return True



class Worker:
    """Background worker to capture, OCR, and translate."""
    def __init__(self, ui_callback):
        self.ui_callback = ui_callback
    
    def clean_text(self, text):
        """Clean text by removing newlines and reducing multiple spaces to max 3"""
        if not text:
            return text
        
        # Remove all newlines and replace with single space
        text = text.replace('\n', ' ').replace('\r', ' ')
        
        # Replace multiple spaces with maximum 3 spaces
        import re
        text = re.sub(r' {4,}', '   ', text)  # Replace 4+ spaces with 3 spaces
        
        # Clean up any remaining multiple spaces (but keep up to 3)
        text = re.sub(r' {2,3}', lambda m: ' ' * min(len(m.group()), 3), text)
        
        return text.strip()

    def process(self, sel: Selection):
        x1, y1, x2, y2 = sel.x1, sel.y1, sel.x2, sel.y2
        
        # Ensure valid coordinates
        if x2 <= x1 or y2 <= y1:
            self.ui_callback("Invalid coordinates", "Please select a valid region")
            return
        
        # Try MSS capture first (most reliable)
        try:
            with mss.mss() as sct:
                monitor = {
                    "top": y1,
                    "left": x1,
                    "width": x2 - x1,
                    "height": y2 - y1
                }
                screenshot = sct.grab(monitor)
                img = Image.frombytes('RGB', (screenshot.width, screenshot.height), screenshot.rgb)
        except Exception:
            # Fallback to ImageGrab
            try:
                img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            except Exception:
                self.ui_callback("Capture failed", "Could not capture screen region")
                return
        
        # OCR
        try:
            results = READER.readtext(np.array(img))
            text = ' '.join(r[1] for r in results).strip()
        except Exception as e:
            text = f"OCR Error: {e}"

        # Clean the original text
        text = self.clean_text(text)

        # Translate
        translated = ""
        if text and not text.startswith("OCR Error"):
            try:
                translated = self.clean_text(translate(text))
            except Exception as e:
                translated = f"Translation Error: {e}"
            literal = ""
            try:
                literal = word_by_word(text, translated)
            except Exception:
                pass
            tip = ""
            if USE_LLM and DETAILED_MODE:
                try:
                    tip = get_tip(text, translated)
                except Exception:
                    pass
            if tip:
                literal = f"{literal}\n{tip}" if literal else tip
        else:
            translated = "No text detected"
            literal = ""

        self.ui_callback(text, translated, literal)


class SimpleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OCR Translator")
        
        # Make window visible first, then we'll adjust transparency
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.8)  # 80% opaque (20% transparent) for better visibility
        self.configure(bg="#000000")
        
        # Remove window decorations for cleaner look
        self.overrideredirect(True)
        
        # Set window size to full screen width
        screen_width = self.winfo_screenwidth()
        self.geometry(f"{screen_width}x300+0+0")
        self.resizable(True, False)
        self.update_idletasks()

        # Word history: {word: {"translation": str, "count": int, "starred": bool}}
        self._history_path = os.path.join(os.path.dirname(__file__), "history.json")
        self.word_history: dict = self._load_history()

        # ---- top frame: current translation ----
        self.frame = tk.Frame(self, bg="#000000")
        self.frame.pack(fill=tk.BOTH)

        self.play_btn = tk.Label(
            self.frame,
            text="▶",
            bg="#000000", fg="#555555",
            font=("Consolas", 18, "bold"),
            cursor="hand2",
            padx=4,
        )
        self.play_btn.pack(side=tk.RIGHT, anchor="n")
        self.play_btn.bind("<Button-1>", lambda e: speak(self._current_original))
        self.play_btn.bind("<Enter>", lambda e: self.play_btn.config(fg="#ffffff"))
        self.play_btn.bind("<Leave>", lambda e: self.play_btn.config(fg="#555555"))

        self.text_widget = tk.Text(
            self.frame,
            height=1,
            wrap=tk.WORD,
            bg="#000000",
            fg="#ffffff",
            insertbackground="#ffffff",
            font=("Consolas", 18, "bold"),
            padx=0, pady=0,
            relief=tk.FLAT, bd=0,
            highlightthickness=0,
            selectbackground="#333333",
            selectforeground="#ffffff",
            state=tk.DISABLED,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ---- separator ----
        tk.Frame(self, bg="#333333", height=1).pack(fill=tk.X)

        # ---- bottom frame: word history ----
        self.history_frame = tk.Frame(self, bg="#000000")
        self.history_frame.pack(fill=tk.BOTH, expand=True)

        # Clicked word meaning — shown above HISTORY label
        self.word_meaning_label = tk.Label(
            self.history_frame,
            text="",
            bg="#000000", fg="#ffdd55",
            font=("Consolas", 13),
            anchor="w",
            wraplength=self.winfo_screenwidth() - 10,
            justify=tk.LEFT,
        )
        self.word_meaning_label.pack(fill=tk.X, padx=5)

        tk.Label(
            self.history_frame,
            text="HISTORY",
            bg="#000000", fg="#888888",
            font=("Consolas", 10, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=5)

        self.history_widget = tk.Text(
            self.history_frame,
            wrap=tk.WORD,
            bg="#000000",
            fg="#cccccc",
            insertbackground="#cccccc",
            font=("Consolas", 13),
            padx=0, pady=0,
            relief=tk.FLAT, bd=0,
            highlightthickness=0,
            selectbackground="#333333",
            selectforeground="#ffffff",
            state=tk.DISABLED,
        )
        self.history_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # Pre-fetched word meanings {word_lower: meaning}
        self._word_meanings: dict = {}
        self._current_original = ""
        self._drag_started = False
        self._selected_word: tuple = None  # (word, meaning)

        # Add drag functionality to all widgets
        for w in (self, self.text_widget, self.history_widget, self.history_frame):
            w.bind('<Button-1>', self.start_move)
            w.bind('<B1-Motion>', self.on_move)

        # Word click on original text (line 1)
        self.text_widget.bind('<ButtonRelease-1>', self._on_text_click)

        # Click on history widget to hear pronunciation
        self.history_widget.bind('<ButtonRelease-1>', self._on_history_click)

        # * saves selected word, - removes it
        self.bind('<asterisk>', self._save_selected_to_history)
        self.bind('<minus>', self._remove_selected_from_history)

        # Initial message
        src_label = "FR" if 'fr' in OCR_LANGS else "EN"
        lang_label = f"{src_label}→{TARGET_LANG.upper()}"
        self.text_widget.config(state=tk.NORMAL)
        backend = "LLM" if USE_LLM else "Google"
        self.text_widget.insert(tk.END, f"[{lang_label}] [{backend}] F8=region  F9=word  Ctrl+F8=remap region  Ctrl+F9=remap word  Ctrl+L=toggle translation(LLM/Google)  RClick=close")
        self.text_widget.config(state=tk.DISABLED)
        
        # Worker & controller
        self.worker = Worker(self._on_result)
        self.word_translator = WordTranslator()
        self.controller = CaptureController(self._on_region_ready, self._on_word_translate, self._on_wait_for_key)

        # Right-click to close (all widgets), keyboard shortcuts on root only
        for w in (self, self.text_widget, self.history_widget):
            w.bind('<Button-3>', self._on_close)
        self.bind('<Control-q>', self._on_close)
        self.bind('<Control-l>', self._toggle_llm)

        # Display persisted history
        if self.word_history:
            self._refresh_history()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y
        self._drag_started = False

    def on_move(self, event):
        self._drag_started = True
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def _on_region_ready(self, sel: Selection):
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, "Processing region...")
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again
        self.worker.process(sel)

    def _on_word_translate(self, cursor_x: int, cursor_y: int):
        """Handle word translation at cursor position."""
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, "Finding word at cursor...")
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again
        
        # Perform word translation
        result = self.word_translator.translate_word_at_cursor(cursor_x, cursor_y)
        self._on_word_result(result)

    def _on_word_result(self, result: TranslationResult):
        """Handle word translation result (F9 cursor word)."""
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        if result.success:
            tip = get_tip(result.original_word, result.translated_word) if (USE_LLM and DETAILED_MODE) else ""
            parts = [result.original_word, result.translated_word]
            if tip:
                parts.append(tip)
            result_text = "\n".join(parts)

        else:
            result_text = f"Kelime çevirilemedi: {result.error_message}"
        self.text_widget.insert(tk.END, result_text)
        self.text_widget.config(state=tk.DISABLED)
        self.after(0, self._fit_translation)

    def _load_history(self) -> dict:
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_history(self):
        try:
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump(self.word_history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_selected_to_history(self, event=None):
        if self._selected_word:
            word, meaning = self._selected_word
            if word.lower() not in self.word_history:
                self._add_to_history(word.lower(), meaning, starred=True)

    def _remove_selected_from_history(self, event=None):
        if self._selected_word:
            word = self._selected_word[0].lower()
            if word in self.word_history:
                del self.word_history[word]
                self._save_history()
                self._refresh_history()

    def _add_to_history(self, word: str, translation: str, starred: bool = False):
        """Add or increment a word in history, then refresh the display."""
        if word in self.word_history:
            self.word_history[word]["count"] += 1
        else:
            self.word_history[word] = {"translation": translation, "count": 1, "starred": starred}
        self._save_history()
        self._refresh_history()

    def _refresh_history(self):
        """Redraw the history widget sorted alphabetically by word."""
        import unicodedata as _ud
        def _sort_key(item):
            return _ud.normalize('NFD', item[0].lower()).encode('ascii', 'ignore').decode('ascii')
        sorted_words = sorted(self.word_history.items(), key=_sort_key)
        entries = []
        for word, data in sorted_words:
            count = data["count"]
            translation = re.sub(r'\s*\(.*?\)', '', data["translation"]).strip()
            times = f" {count}x" if count > 1 else ""
            star = "* " if data.get("starred") else ""
            import unicodedata as _ud
            entry = _ud.normalize('NFC', f"{star}{word} → {translation}{times}")
            entries.append(entry[:28] + ".." if len(entry) > 30 else entry)

        # col_width is fixed at 30 chars so cols never changes as entries are
        # added/removed — prevents the grid from reshuffling on every insert
        win_width = self.winfo_width() or self.winfo_screenwidth()
        char_width = 8
        col_width = 30
        cols = max(1, win_width // ((col_width + 2) * char_width))
        self._history_col_width = col_width

        import math
        rows = math.ceil(len(entries) / cols) if entries else 0
        self.history_widget.config(state=tk.NORMAL)
        self.history_widget.delete("1.0", tk.END)
        for r in range(rows):
            row = [entries[r + c * rows] for c in range(cols) if r + c * rows < len(entries)]
            line = "  ".join(e.ljust(col_width) for e in row) + "\n"
            self.history_widget.insert(tk.END, line)
        self.history_widget.config(state=tk.DISABLED)

    def _toggle_llm(self, event=None):
        global USE_LLM
        USE_LLM = not USE_LLM
        mode = f"OpenAI ({OPENAI_MODEL})" if USE_LLM else "Google Translate"
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, f"Translation backend: {mode}")
        self.text_widget.config(state=tk.DISABLED)

    def _on_wait_for_key(self, message=None):
        """Handle wait-for-key mode activation."""
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        
        if message:
            self.text_widget.insert(tk.END, message)
        else:
            self.text_widget.insert(tk.END, "Waiting for key... Press any key to set it as translation key")
        
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again

    def _fit_translation(self):
        """Resize text_widget and window height to fit actual rendered content."""
        self.text_widget.update_idletasks()
        try:
            n = self.text_widget.count("1.0", "end", "displaylines")[0] or 1
        except Exception:
            n = 1
        self.text_widget.config(height=max(1, n))
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_reqheight()
        x = self.winfo_x()
        y = self.winfo_y()
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_history_click(self, event):
        """Speak the word clicked in the history panel."""
        try:
            idx = self.history_widget.index(f"@{event.x},{event.y}")
            col = int(idx.split('.')[1])
            line_no = idx.split('.')[0]
            line_text = self.history_widget.get(f"{line_no}.0", f"{line_no}.end")
            col_width = getattr(self, '_history_col_width', len(line_text))
            # each column occupies col_width chars + 2-space separator
            seg_idx = col // (col_width + 2)
            start = seg_idx * (col_width + 2)
            entry = line_text[start:start + col_width].strip()
            if not entry:
                entry = line_text[:col_width].strip()
            word = entry.lstrip("* ").split("→")[0].strip()
            if word:
                self._selected_word = (word, "")
                speak(word)
        except Exception:
            pass

    def _on_text_click(self, event):
        """Show pre-fetched meaning of clicked word (line 1 = original text)."""
        if self._drag_started or not self._current_original:
            return
        try:
            idx = self.text_widget.index(f"@{event.x},{event.y}")
            if int(idx.split('.')[0]) != 1:
                return
            self.text_widget.config(state=tk.NORMAL)
            word = self.text_widget.get(
                self.text_widget.index(f"{idx} wordstart"),
                self.text_widget.index(f"{idx} wordend"),
            ).strip()
            self.text_widget.config(state=tk.DISABLED)
            word_clean = re.sub(r"[^a-zA-ZÀ-ÿ\u00C0-\u024F']", "", word)
            if not word_clean:
                return
            meaning = self._word_meanings.get(word_clean.lower(), "")
            self._selected_word = (word_clean, meaning)
            self.word_meaning_label.config(text=f"{word_clean} — {meaning}" if meaning else word_clean)
            speak(word_clean)
        except Exception:
            pass

    def _on_result(self, original: str, translated: str, literal: str = ""):
        self._current_original = original or ""
        self._word_meanings = {}
        self.word_meaning_label.config(text="")
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        line1 = original or "(no text detected)"
        line2 = translated or "(translation failed)"
        result = f"{line1}\n{line2}"
        if literal:
            result += f"\n{literal}"
        self.text_widget.insert(tk.END, result)
        self.text_widget.config(state=tk.DISABLED)
        self.after(0, self._fit_translation)
        if USE_LLM and original:
            threading.Thread(target=self._prefetch_meanings, args=(original,), daemon=True).start()

    def _prefetch_meanings(self, sentence: str):
        meanings = fetch_all_word_meanings(sentence)
        self._word_meanings = meanings

    def _on_close(self, event=None):
        try:
            self.controller.stop()
        except Exception:
            pass
        self.destroy()


def pick_language():
    """Standalone language picker — sets OCR_LANGS, TARGET_LANG, TARGET_LANG_NAME globals."""
    global OCR_LANGS, TARGET_LANG, TARGET_LANG_NAME
    picker = tk.Tk()
    picker.title("Language")
    picker.resizable(False, False)
    picker.attributes('-topmost', True)
    picker.update_idletasks()
    w, h = 320, 160
    x = (picker.winfo_screenwidth() - w) // 2
    y = (picker.winfo_screenheight() - h) // 2
    picker.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(picker, text="Source language", font=("Arial", 11, "bold")).pack(pady=(10, 2))
    src_frame = tk.Frame(picker)
    src_frame.pack()

    src_var = tk.StringVar(value="fr")
    tk.Radiobutton(src_frame, text="French", variable=src_var, value="fr").pack(side=tk.LEFT, padx=10)
    tk.Radiobutton(src_frame, text="English", variable=src_var, value="en").pack(side=tk.LEFT, padx=10)

    tk.Label(picker, text="Target language", font=("Arial", 11, "bold")).pack(pady=(10, 2))
    tgt_frame = tk.Frame(picker)
    tgt_frame.pack()

    tgt_var = tk.StringVar(value="en")
    tk.Radiobutton(tgt_frame, text="English", variable=tgt_var, value="en").pack(side=tk.LEFT, padx=10)
    tk.Radiobutton(tgt_frame, text="Turkish", variable=tgt_var, value="tr").pack(side=tk.LEFT, padx=10)

    def choose():
        global OCR_LANGS, TARGET_LANG, TARGET_LANG_NAME
        src = src_var.get()
        tgt = tgt_var.get()
        OCR_LANGS = ['fr', 'en'] if src == 'fr' else ['en']
        TARGET_LANG = tgt
        TARGET_LANG_NAME = {"en": "English", "tr": "Turkish"}.get(tgt, tgt)
        picker.destroy()

    tk.Button(picker, text="Start", width=12, command=choose).pack(pady=10)
    picker.mainloop()


if __name__ == "__main__":
    pick_language()
    print(f"Loading EasyOCR model for {OCR_LANGS} (GPU)...")
    READER = easyocr.Reader(OCR_LANGS, gpu=True)
    print("Model ready.")
    app = SimpleApp()
    app.mainloop()
