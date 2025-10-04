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
from dataclasses import dataclass
from typing import List, Tuple, Optional

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageGrab
import mss
from pynput import mouse, keyboard
import pytesseract
from deep_translator import GoogleTranslator

# No complex image processing needed - just simple OCR and distance calculation


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
        self.word_pattern = r'\b[a-zA-Z]+\b'
        
    def extract_words_from_ocr(self, ocr_data: dict) -> List[WordInfo]:
        """Extract word information from Tesseract OCR data."""
        words = []
        
        try:
            # Get detailed OCR data with bounding boxes
            for i in range(len(ocr_data['text'])):
                word_text = ocr_data['text'][i].strip()
                conf = int(ocr_data['conf'][i])
                
                # Filter words based on length and pattern
                if (conf > 0 and 
                    self.min_word_length <= len(word_text) <= self.max_word_length and
                    re.match(self.word_pattern, word_text)):
                    
                    word_info = WordInfo(
                        text=word_text,
                        x=ocr_data['left'][i],
                        y=ocr_data['top'][i],
                        width=ocr_data['width'][i],
                        height=ocr_data['height'][i],
                        confidence=conf
                    )
                    words.append(word_info)
                    
        except Exception as e:
            print(f"Error extracting words from OCR: {e}")
            
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
                ocr_data = pytesseract.image_to_data(
                    image, 
                    lang=OCR_LANGS,
                    config='--psm 6',
                    output_type=pytesseract.Output.DICT
                )
                words = self.word_detector.extract_words_from_ocr(ocr_data)
                
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
                translated = GoogleTranslator(source="auto", target=TARGET_LANG).translate(nearest_word.text)
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
        self.text_widget.insert(tk.END, "Press F8 for region translation, F9 for word translation, Ctrl+F12 to set custom trigger (keyboard/mouse/scroll)...")
        
        # Worker & controller
        self.worker = Worker(self._on_result)
        self.word_translator = WordTranslator()
        self.controller = CaptureController(self._on_region_ready, self._on_word_translate, self._on_wait_for_key)

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
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        
        if result.success:
            # Format the result with confidence
            result_text = f"{result.original_word} : {result.translated_word} ({result.confidence}%)"
        else:
            # Show error message
            result_text = f"Word translation failed: {result.error_message}"
            
        self.text_widget.insert(tk.END, result_text)
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again

    def _on_wait_for_key(self, message=None):
        """Handle wait-for-key mode activation."""
        self.text_widget.config(state=tk.NORMAL)  # Enable editing
        self.text_widget.delete("1.0", tk.END)
        
        if message:
            self.text_widget.insert(tk.END, message)
        else:
            self.text_widget.insert(tk.END, "Waiting for key... Press any key to set it as translation key")
        
        self.text_widget.config(state=tk.DISABLED)  # Disable editing again

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
