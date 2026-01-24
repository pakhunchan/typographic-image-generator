# Typographic Portrait Generator

A typographic portrait generator that turns images into stunning typographic art. This tool fills your photos with high-density, custom text patterns, offering precise controls for contrast, color palettes, and word lists to generate clean, professional-grade word portraits.

## Features

- **High-Density Text Filling**: Advanced algorithm places text horizontally and vertically (0°/90°) to strictly fill dark regions without overlap.
- **Customizable Controls**: Adjust threshold, invert colors, select color palettes, and choose font sizes.
- **Custom Text**: Use your own words and phrases. Prefix words with `*` to feature them (make them larger).
- **Instant Preview**: Real-time browser-based UI.

## Getting Started

### Prerequisites

- Python 3.x
- `pip`

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

1. Start the server:
   ```bash
   python server.py
   ```
2. Open your browser to `http://localhost:5000`

## Technologies

- **Backend**: Python, Flask, Pillow (PIL), NumPy
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)

## License

MIT
