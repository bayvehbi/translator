"""
Screen OCR & Translate — ultra‑simple, always‑on‑top UI

How it works:
- Press F8 to set top-left corner (where mouse cursor is)
- Press F8 again to set bottom-right corner (where mouse cursor is)
- Translation starts automatically
- Results appear in the always‑on‑top window as "original : translation"

Keys:
- Press  F8  to set corners (first = top-left, second = bottom-right)
- Press  Esc  to close application
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
    """Handles global keyboard input for screen capture."""
    def __init__(self, on_region_ready):
        self.on_region_ready = on_region_ready
        self._lock = threading.Lock()
        self._points = []  # Store cursor positions
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
        self._kb_listener.start()

    def stop(self):
        self._kb_listener.stop()

    def _on_key_press(self, key):
        try:
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
        self.attributes('-alpha', 0.8)  # 80% opaque (20% transparent) for better visibility
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
        
        # Create invisible scrollbar for text widget
        self.scrollbar = tk.Scrollbar(self.frame, orient="vertical")
        
        # Create text widget with solid text but transparent background
        self.text_widget = tk.Text(
            self.frame, 
            height=3,  # Allow up to 3 lines
            wrap=tk.WORD,  # Wrap at word boundaries
            bg="#000000",  # Black background (will be transparent)
            fg="#ffffff",  # Bright white text for maximum visibility
            insertbackground="#ffffff",
            font=("Consolas", 18, "bold"),  # Larger and bold for better visibility
            padx=0,  # No padding
            pady=0,  # No padding
            relief=tk.FLAT,  # No border
            bd=0,  # No border width
            highlightthickness=0,  # No highlight border
            selectbackground="#333333",  # Dark selection background
            selectforeground="#ffffff",  # White selected text
            state=tk.DISABLED,  # Make it read-only and flat
            yscrollcommand=self.scrollbar.set  # Connect to scrollbar
        )
        
        # Configure invisible scrollbar
        self.scrollbar.config(command=self.text_widget.yview)
        # Don't pack the scrollbar - keep it invisible but functional
        
        # Pack text widget to fill the entire frame
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add drag functionality to move the window
        self.bind('<Button-1>', self.start_move)
        self.bind('<B1-Motion>', self.on_move)
        self.text_widget.bind('<Button-1>', self.start_move)
        self.text_widget.bind('<B1-Motion>', self.on_move)
        
        # Initial message
        self.text_widget.insert(tk.END, "Press F8 at top-left corner, then F8 at bottom-right corner...")
        
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
