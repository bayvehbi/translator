# 🖥️ OCR Translator

A lightweight, always-on-top screen OCR and translation tool that captures text from any part of your screen and translates it in real-time.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

- **🎯 Screen OCR**: Capture text from any region of your screen with simple click-and-drag
- **🌍 Real-time Translation**: Instant translation to Turkish (easily configurable for other languages)
- **🔝 Always on Top**: Translucent window that stays above all other applications
- **🧹 Smart Text Cleaning**: Automatically removes newlines and optimizes spacing
- **📱 Multi-line Display**: Intelligent text wrapping with scrolling support
- **⚡ Lightweight**: Minimal resource usage with fast performance
- **🎮 Simple Controls**: Intuitive keyboard and mouse controls

## 🚀 Quick Start

### Option 1: Download Executable (Recommended)
1. Download `OCR_Translator.exe` from the [Releases](https://github.com/yourusername/ocr-translator/releases) page
2. Double-click to run (no installation required)
3. Hold `"` key and drag to capture text from screen

### Option 2: Run from Source
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ocr-translator.git
   cd ocr-translator
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Tesseract OCR:
   ```bash
   winget install UB-Mannheim.TesseractOCR
   ```

4. Run the application:
   ```bash
   python main.py
   ```

## 🎮 How to Use

1. **Launch** the application
2. **Capture text**: 
   - Hold down the `"` (quote) key
   - Click and drag to select a region on your screen
   - Release the quote key
3. **View results**: The captured text and translation appear in the translucent window
4. **Close**: Right-click the window or press `Ctrl+Q`

### Controls
- **`"` + Click & Drag**: Capture text from screen region
- **Right-click**: Close the application
- **Ctrl+Q**: Close the application
- **Mouse wheel**: Scroll through long text
- **Drag window**: Click and drag the window to move it

## ⚙️ Configuration

Edit `main.py` to customize:

```python
# Translation settings
TARGET_LANG = "tr"           # Target language (tr=Turkish, en=English, etc.)
OCR_LANGS   = "eng"          # OCR language (eng=English, tur=Turkish, etc.)

# Tesseract path (adjust if needed)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## 🛠️ Building from Source

To create your own executable:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Build the executable:
   ```bash
   pyinstaller translator.spec
   ```

3. Find your executable in the `dist/` folder

## 📋 Requirements

- **Windows 10/11**
- **Tesseract OCR** (installed automatically with winget)
- **Internet connection** (for translation)
- **Python 3.11+** (if running from source)

## 🔧 Dependencies

- `mss` - Fast screen capture
- `pillow` - Image processing
- `pytesseract` - OCR engine
- `pynput` - Global keyboard/mouse input
- `deep-translator` - Translation service
- `tkinter` - GUI framework (included with Python)

## 🎨 Screenshots

*Coming soon - screenshots of the application in action*

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for text recognition
- [Google Translate](https://translate.google.com/) for translation services
- [PyInstaller](https://www.pyinstaller.org/) for creating standalone executables

## 📞 Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/yourusername/ocr-translator/issues) page
2. Create a new issue with detailed information
3. Include your Windows version and any error messages

## 🔄 Changelog

### v1.0.0
- Initial release
- Screen OCR with Tesseract
- Real-time translation
- Always-on-top translucent window
- Smart text cleaning and formatting
- Multi-line display with scrolling
- Standalone executable support

---

**Made with ❤️ for easy screen text translation**