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

import tkinter as tk
import numpy as np
from PIL import Image, ImageGrab
import mss
import easyocr
from pynput import mouse, keyboard
from deep_translator import GoogleTranslator
from openai import OpenAI


# ---------------- Configuration ---------------- #
def load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

CONFIG = load_config()

TARGET_LANG    = "tr"
OCR_LANGS      = ['en']
READER: easyocr.Reader = None
USE_LLM        = False
OPENAI_CLIENT: OpenAI = None
OPENAI_MODEL   = CONFIG.get("openai_model", "gpt-4o-mini")


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
            f"Sentence: \"{text}\"\n\n"
            f"For each word in the sentence, give its {TARGET_LANG} meaning as used in this specific sentence (context-aware, not dictionary).\n"
            f"Ignore word order differences. Output one line only, no extra text:\n"
            f"word1→meaning1  word2→meaning2  word3→meaning3"
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
                {"role": "system", "content": f"Translate to {TARGET_LANG}. Return only the translation, nothing else."},
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
        self.on_region_ready = on_region_ready
        self.on_word_translate = on_word_translate
        self.on_wait_for_key = on_wait_for_key
        self._lock = threading.Lock()
        self._points = []  # Store cursor positions
        self._waiting_for_key = False
        self._ctrl_pressed = False
        self._f12_pressed = False
        self._custom_translate_key = None  # Store the custom translation key
        self._input_count = 0  # Count all inputs during wait mode
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click, on_move=self._on_mouse_move, on_scroll=self._on_mouse_scroll)
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self):
        self._kb_listener.stop()
        self._mouse_listener.stop()

    def _on_key_press(self, key):
        try:
            # Check for Ctrl+F12 combination
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = True
            elif key == keyboard.Key.f12:
                self._f12_pressed = True
            
            # If both Ctrl and F12 are pressed, activate wait-for-key mode
            if self._ctrl_pressed and self._f12_pressed and not self._waiting_for_key:
                self._waiting_for_key = True
                self._input_count = 0  # Reset input counter
                threading.Thread(target=self.on_wait_for_key, daemon=True).start()
                return True
            
            # If we're waiting for input, count this keyboard input
            if self._waiting_for_key:
                self._input_count += 1
                if key not in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.f12]:
                    self._waiting_for_key = False
                    self._custom_translate_key = key
                    threading.Thread(target=self.on_wait_for_key, args=(f"Keyboard key '{key}' set as translation trigger! (Total inputs detected: {self._input_count})",), daemon=True).start()
                    return True
            
            # Check if pressed key is the custom translation key
            if self._custom_translate_key and key == self._custom_translate_key:
                import win32gui
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
                threading.Thread(target=self.on_word_translate, args=(x, y), daemon=True).start()
                return True
            
            # Original F8 functionality
            if key == keyboard.Key.f8:
                # Get current mouse cursor position
                import win32gui
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
                
                with self._lock:
                    self._points.append((x, y))
                    
                    if len(self._points) == 2:
                        # We have both points, create selection
                        (x1, y1), (x2, y2) = self._points
                        x_left, x_right = sorted([x1, x2])
                        y_top, y_bottom = sorted([y1, y2])
                        
                        sel = Selection(x_left, y_top, x_right, y_bottom)
                        threading.Thread(target=self.on_region_ready, args=(sel,), daemon=True).start()
                        self._points.clear()  # Reset for next selection
                        
            # Original F9 functionality (only if no custom key is set)
            elif key == keyboard.Key.f9 and self._custom_translate_key is None:
                # Word translation mode
                import win32gui
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
                threading.Thread(target=self.on_word_translate, args=(x, y), daemon=True).start()
                
        except Exception as e:
            pass
        return True
    
    def _on_key_release(self, key):
        """Handle key release events."""
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = False
            elif key == keyboard.Key.f12:
                self._f12_pressed = False
        except Exception as e:
            pass
        return True
    
    def _on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click events."""
        try:
            # If we're waiting for input, count this mouse click
            if self._waiting_for_key and pressed:
                self._input_count += 1
                self._waiting_for_key = False
                self._custom_translate_key = f"mouse_{button.name}"  # Store mouse button as trigger
                threading.Thread(target=self.on_wait_for_key, args=(f"Mouse {button.name} click set as translation trigger! (Total inputs detected: {self._input_count})",), daemon=True).start()
            # Check if this mouse click is the custom translation trigger
            elif self._custom_translate_key and self._custom_translate_key == f"mouse_{button.name}" and pressed:
                import win32gui
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
                threading.Thread(target=self.on_word_translate, args=(x, y), daemon=True).start()
        except Exception as e:
            pass
        return True
    
    def _on_mouse_move(self, x, y):
        """Handle mouse movement events."""
        try:
            # If we're waiting for input, count every mouse movement
            if self._waiting_for_key:
                self._input_count += 1
                threading.Thread(target=self.on_wait_for_key, args=(f"Mouse movement detected! (Total inputs: {self._input_count}) - Press a keyboard key to set as translation key",), daemon=True).start()
        except Exception as e:
            pass
        return True
    
    def _on_mouse_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events."""
        try:
            # If we're waiting for input, count this mouse scroll
            if self._waiting_for_key:
                self._input_count += 1
                self._waiting_for_key = False
                scroll_direction = "up" if dy > 0 else "down"
                self._custom_translate_key = f"mouse_scroll_{scroll_direction}"  # Store scroll as trigger
                threading.Thread(target=self.on_wait_for_key, args=(f"Mouse scroll {scroll_direction} set as translation trigger! (Total inputs detected: {self._input_count})",), daemon=True).start()
            # Check if this mouse scroll is the custom translation trigger
            elif self._custom_translate_key:
                scroll_direction = "up" if dy > 0 else "down"
                if self._custom_translate_key == f"mouse_scroll_{scroll_direction}":
                    import win32gui
                    cursor_pos = win32gui.GetCursorPos()
                    x, y = cursor_pos
                    threading.Thread(target=self.on_word_translate, args=(x, y), daemon=True).start()
        except Exception as e:
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
        literal = ""
        if text and not text.startswith("OCR Error"):
            try:
                translated = self.clean_text(translate(text))
            except Exception as e:
                translated = f"Translation Error: {e}"
            try:
                literal = word_by_word(text, translated)
            except Exception:
                literal = ""
        else:
            translated = "No text detected"

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

        # Word history: {word: {"translation": str, "count": int}}
        self.word_history: dict = {}

        # ---- top frame: current translation ----
        self.frame = tk.Frame(self, bg="#000000")
        self.frame.pack(fill=tk.BOTH)

        self.text_widget = tk.Text(
            self.frame,
            height=3,
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

        # Add drag functionality to all widgets
        for w in (self, self.text_widget, self.history_widget, self.history_frame):
            w.bind('<Button-1>', self.start_move)
            w.bind('<B1-Motion>', self.on_move)

        # Initial message
        lang_label = "FR→TR" if 'fr' in OCR_LANGS else "EN→TR"
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, f"[{lang_label}] F8=region, F9=word, Ctrl+F12=custom trigger, RClick=close")
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

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def on_move(self, event):
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
        """Handle word translation result."""
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        if result.success:
            result_text = f"{result.original_word} : {result.translated_word} ({result.confidence:.0f}%)"
            self._add_to_history(result.original_word.lower(), result.translated_word)
        else:
            result_text = f"Word translation failed: {result.error_message}"
        self.text_widget.insert(tk.END, result_text)
        self.text_widget.config(state=tk.DISABLED)

    def _add_to_history(self, word: str, translation: str):
        """Add or increment a word in history, then refresh the display."""
        if word in self.word_history:
            self.word_history[word]["count"] += 1
        else:
            self.word_history[word] = {"translation": translation, "count": 1}
        self._refresh_history()

    def _refresh_history(self):
        """Redraw the history widget sorted by search count."""
        sorted_words = sorted(
            self.word_history.items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )
        self.history_widget.config(state=tk.NORMAL)
        self.history_widget.delete("1.0", tk.END)
        for word, data in sorted_words:
            count = data["count"]
            translation = data["translation"]
            times = f"{count}x" if count > 1 else ""
            line = f"{word} → {translation}  {times}\n"
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

    def _on_result(self, original: str, translated: str, literal: str = ""):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)

        line1 = original or "(no text detected)"
        line2 = translated or "(translation failed)"
        line3 = literal or ""

        result = f"{line1}\n{line2}"
        if line3:
            result += f"\n{line3}"

        self.text_widget.insert(tk.END, result)
        self.text_widget.config(state=tk.DISABLED)

    def _on_close(self, event=None):
        try:
            self.controller.stop()
        except Exception:
            pass
        self.destroy()


def pick_language():
    """Standalone language picker — runs its own mainloop, sets OCR_LANGS global."""
    global OCR_LANGS
    picker = tk.Tk()
    picker.title("Language")
    picker.resizable(False, False)
    picker.attributes('-topmost', True)
    picker.update_idletasks()
    w, h = 280, 100
    x = (picker.winfo_screenwidth() - w) // 2
    y = (picker.winfo_screenheight() - h) // 2
    picker.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(picker, text="Source language → Turkish", font=("Arial", 11)).pack(pady=8)
    frame = tk.Frame(picker)
    frame.pack()

    def choose(ocr):
        global OCR_LANGS
        OCR_LANGS = ocr
        picker.destroy()

    tk.Button(frame, text="English", width=10, command=lambda: choose(['en'])).pack(side=tk.LEFT, padx=10)
    tk.Button(frame, text="French",  width=10, command=lambda: choose(['fr'])).pack(side=tk.LEFT, padx=10)

    picker.mainloop()


if __name__ == "__main__":
    pick_language()
    print(f"Loading EasyOCR model for {OCR_LANGS} (GPU)...")
    READER = easyocr.Reader(OCR_LANGS, gpu=True)
    print("Model ready.")
    app = SimpleApp()
    app.mainloop()
