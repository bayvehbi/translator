"""
Screen OCR & Translate — ultra‑simple, always‑on‑top UI

How it works:
- Hold the `"` key (double‑quote) and click two points on the screen.
- The app captures the region, runs OCR, and translates to Turkish.
- Results appear in the always‑on‑top window as "original : translation"

Keys:
- Hold  `"`  while clicking to select region
- Press  Esc  to cancel an in‑progress selection
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageGrab
import mss
from pynput import mouse, keyboard
import pytesseract
from deep_translator import GoogleTranslator


# ---------------- Configuration ---------------- #
TARGET_LANG = "tr"           # translation target language (Turkish)
OCR_LANGS   = "eng"          # tesseract language (English only)

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class Selection:
    x1: int
    y1: int
    x2: int
    y2: int


class CaptureController:
    """Handles global keyboard state and mouse clicks to form a capture rectangle."""
    def __init__(self, on_region_ready):
        self.on_region_ready = on_region_ready
        self._quote_held = False
        self._points: list[tuple[int, int]] = []
        self._lock = threading.Lock()
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self._ms_listener = mouse.Listener(on_click=self._on_click)
        self._kb_listener.start()
        self._ms_listener.start()

    def stop(self):
        self._kb_listener.stop()
        self._ms_listener.stop()

    def _on_key_press(self, key):
        try:
            if isinstance(key, keyboard.KeyCode) and key.char == '"':
                with self._lock:
                    self._quote_held = True
        except Exception:
            pass
        if key == keyboard.Key.esc:
            with self._lock:
                self._points.clear()
        return True

    def _on_key_release(self, key):
        try:
            if isinstance(key, keyboard.KeyCode) and key.char == '"':
                with self._lock:
                    self._quote_held = False
        except Exception:
            pass
        return True

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return True
        with self._lock:
            if not self._quote_held:
                return True
            self._points.append((x, y))
            if len(self._points) == 2:
                (x1, y1), (x2, y2) = self._points
                self._points.clear()
                x_left, x_right = sorted([x1, x2])
                y_top, y_bottom = sorted([y1, y2])
                sel = Selection(x_left, y_top, x_right, y_bottom)
                threading.Thread(target=self.on_region_ready, args=(sel,), daemon=True).start()
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
            text = pytesseract.image_to_string(img, lang=OCR_LANGS).strip()
        except Exception as e:
            text = f"OCR Error: {e}"

        # Clean the original text
        text = self.clean_text(text)

        # Translate
        translated = ""
        if text and not text.startswith("OCR Error"):
            try:
                translated = GoogleTranslator(source="auto", target=TARGET_LANG).translate(text)
                # Clean the translated text too
                translated = self.clean_text(translated)
            except Exception as e:
                translated = f"Translation Error: {e}"
        else:
            translated = "No text detected"

        self.ui_callback(text, translated)


class SimpleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OCR Translator")
        
        # Make window visible first, then we'll adjust transparency
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.3)  # Start with 70% transparent so we can see it
        self.configure(bg="#000000")
        
        # Remove window decorations for cleaner look
        self.overrideredirect(True)
        
        # Set window size to full screen width, multi-line height
        screen_width = self.winfo_screenwidth()
        self.geometry(f"{screen_width}x120+0+0")  # Full width, 120px height for 3 lines, very top of screen
        self.resizable(True, False)  # Allow horizontal resize only
        
        # Force window to update geometry
        self.update_idletasks()
        
        # Create completely transparent frame
        self.frame = tk.Frame(self, bg="#000000")
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Create scrollbar for text widget
        self.scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        
        # Create text widget with solid text but transparent background
        self.text_widget = tk.Text(
            self.frame, 
            height=3,  # Allow up to 3 lines
            wrap=tk.WORD,  # Wrap at word boundaries
            bg="#000000",  # Black background (will be transparent)
            fg="#00ff00",  # Solid bright green text
            insertbackground="#ffffff",
            font=("Consolas", 16, "bold"),  # Even larger and bold for better visibility
            padx=0,  # No padding
            pady=0,  # No padding
            relief=tk.FLAT,  # No border
            bd=0,  # No border width
            highlightthickness=0,  # No highlight border
            selectbackground="#333333",  # Dark selection background
            selectforeground="#00ff00",  # Green selected text
            state=tk.DISABLED,  # Make it read-only and flat
            yscrollcommand=self.scrollbar.set  # Connect to scrollbar
        )
        
        # Configure scrollbar
        self.scrollbar.config(command=self.text_widget.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Pack text widget
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add drag functionality to move the window
        self.bind('<Button-1>', self.start_move)
        self.bind('<B1-Motion>', self.on_move)
        self.text_widget.bind('<Button-1>', self.start_move)
        self.text_widget.bind('<B1-Motion>', self.on_move)
        
        # Initial message
        self.text_widget.insert(tk.END, "Hold \" and click two points to capture text...")
        
        # Worker & controller
        self.worker = Worker(self._on_result)
        self.controller = CaptureController(self._on_region_ready)

        # Add close button (right-click to close)
        self.bind('<Button-3>', self._on_close)  # Right-click to close
        self.text_widget.bind('<Button-3>', self._on_close)
        
        # Add keyboard shortcut to close (Ctrl+Q)
        self.bind('<Control-q>', self._on_close)
        self.text_widget.bind('<Control-q>', self._on_close)

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
        self.text_widget.insert(tk.END, "Processing...")
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again
        self.worker.process(sel)

    def _on_result(self, original: str, translated: str):
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        
        # Format as "original : translation" - completely flat, no quotes
        if original and translated:
            result = f"{original} : {translated}"
        elif original:
            result = f"{original} : (translation failed)"
        elif translated:
            result = f"(no text detected) : {translated}"
        else:
            result = "No text detected"
            
        self.text_widget.insert(tk.END, result)
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again

    def _on_close(self, event=None):
        try:
            self.controller.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = SimpleApp()
    app.mainloop()
