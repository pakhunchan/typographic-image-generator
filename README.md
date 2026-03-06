# Typographic — Word Portrait Studio

Transform photographs into beautiful typographic portraits. Upload any image and fill its silhouette with your own words.

**Live demo**: [typographic.pakhunchan.com](https://typographic.pakhunchan.com)

## Features

- **Two-Phase Rendering**: Fast 2048px placement with live streaming preview, then crisp 4096px final output with 2x supersampled text.
- **Featured Words**: Mark words as "featured" to make them larger and more prominent in the portrait.
- **Color Palettes**: Warm Red, Ocean Blue, Forest Green, Sunset, Monochrome, or define your own custom colors.
- **Background Options**: Transparent (PNG), white, or black backgrounds.
- **Density Control**: Fine, Regular, or Bold text density settings.
- **Fill Threshold**: Adjustable slider to control how much of the image silhouette gets filled.
- **Invert Mode**: Swap which regions of the image get filled with text.

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

### Running

```bash
python server.py
```

Open `http://localhost:5000` in your browser.

## How It Works

1. **Upload** a photo — the app converts it to a grayscale silhouette mask.
2. **Add words** — mark some as "featured" (Ctrl+B) to make them larger.
3. **Generate** — the engine places words in 7 font-size passes (18pt down to 3pt) using vectorized integral-image collision detection for fast, dense packing.
4. **Download** — the final 4096px PNG with 2x supersampled text.

## Tech Stack

- **Backend**: Python, Flask, Pillow, NumPy
- **Frontend**: Vanilla HTML/CSS/JS
- **Deployment**: Vercel

## License

MIT
