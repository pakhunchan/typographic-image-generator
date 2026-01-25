"""
Typographic Portrait Generator - Backend Server

Converts images into typographic art by filling dark/light regions with text.
"""

import io
import base64
import random
import json
import time
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
import numpy as np

app = Flask(__name__, static_folder='static')
CORS(app)

# Color schemes
COLOR_SCHEMES = {
    'warm_red': ['#8B0000', '#CD5C5C', '#FF6347', '#FFA500', '#FFD700'],
    'ocean_blue': ['#000080', '#4169E1', '#00CED1', '#87CEEB', '#E0FFFF'],
    'forest_green': ['#006400', '#228B22', '#32CD32', '#90EE90', '#98FB98'],
    'sunset': ['#FF1493', '#FF4500', '#FFA500', '#FFD700', '#FFFF00'],
    'monochrome': ['#000000', '#333333', '#666666', '#999999', '#CCCCCC'],
}

# Font size mappings
FONT_SIZES = {
    'small': 10,
    'medium': 14,
    'large': 20,
}

MAX_DIMENSION = 2048


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_font(size):
    """Get a bold font at the specified size."""
    try:
        # Prioritize thick/bold fonts for better density and "poster" look
        font_paths = [
            # macOS paths (Impact/Arial Black are very thick)
            '/System/Library/Fonts/Supplemental/Impact.ttf',
            '/System/Library/Fonts/Supplemental/Arial Black.ttf',
            '/Library/Fonts/Impact.ttf',
            '/Library/Fonts/Arial Black.ttf',
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/Library/Fonts/Arial Bold.ttf',
            '/System/Library/Fonts/Helvetica.ttc', # Often has bold, but fallback
            # Common names
            'Impact',
            'Arial Black',
            'Arial Bold',
            'Helvetica-Bold',
            'DejaVuSans-Bold',
        ]
        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                continue
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def create_mask(image, threshold, invert):
    """Create a binary mask from the image based on threshold."""
    gray = image.convert('L')
    gray_array = np.array(gray)
    
    if invert:
        mask = gray_array >= threshold
    else:
        mask = gray_array < threshold
    
    return mask


def place_words_dense(width, height, mask, words, colors, base_font_size):
    """
    Place words densely with strict no-overlap policy.
    Rotations restricted to 0 and 90 degrees.
    Uses many passes with decreasing font sizes to fill gaps.
    """
    output = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    
    # Parse words
    featured = []
    regular = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        if word.startswith('*'):
            featured.append(word[1:].upper())
        else:
            regular.append(word.upper())
    
    all_words = featured + regular if featured or regular else ['TEXT']
    rgb_colors = [hex_to_rgb(c) for c in colors]
    
    # Track word positions to avoid clustering similar words
    # Dictionary mapping word -> list of (x, y) coordinates
    word_positions = {}

    # Track occupied regions
    # logical OR of placed text boxes
    occupied = np.zeros((height, width), dtype=bool)
    
    # Restrict angles to Horizontal (0) and Vertical (90)
    angles = [0, 0, 0, 90] 
    
    color_idx = 0
    
    # Multi-pass strategy:
    # 1. Very Large (Featured/Big) - Anchor points
    # 2. Large
    # 3. Medium-Large
    # 4. Medium
    # 5. Medium
    # 6. Small
    # 7. Tiny (Fillers)
    # 8. Micro (gap fillers)
    # 8. Micro (gap fillers)
    # 9. Nano (finishing touches)
    size_multipliers = [1.9, 1.7, 1.5, 1.3, 1.1, 0.9, 0.7, 0.5, 0.3]
    
    # Base density target affects attempts
    total_pixels = width * height
    # Reduce density by ~20% (Increase divisor from 20 to 25)
    base_attempts = int(total_pixels / 25) 
    
    # Minimum distance between identical words (as fraction of image diagonal)
    min_dist_ratio = 0.2 
    img_diag = np.sqrt(width**2 + height**2)
    
    for pass_idx, size_mult in enumerate(size_multipliers):
        current_font_size = max(6, int(base_font_size * size_mult)) # Allow even smaller font
        font = get_font(current_font_size)
        
        # Calculate attempts:
        # User-defined density distribution:
        # Largest 1/3 (Indices 0-2): x1.4
        # Middle 1/3 (Indices 3-5):  x1.8
        # Smallest 1/3 (Indices 6-8): x0.8
        
        base_factor = pass_idx + 1
        
        if pass_idx <= 2:   # 1.9, 1.7, 1.5
            boost = 1.4
        elif pass_idx <= 5: # 1.3, 1.1, 0.9
            boost = 1.8
        else:               # 0.7, 0.5, 0.3
            boost = 0.8
            
        attempts_factor = base_factor * boost
        
        attempts = int(base_attempts * attempts_factor) 
        
        # Reduce proximity requirement for smaller passes
        current_min_dist = max(50, img_diag * min_dist_ratio * size_mult)
            
        # Optimization: Fail fast if we can't find spots
        consecutive_failures = 0
        max_failures = 80000 
        
        # Temp draw for measurement
        dummy_draw = ImageDraw.Draw(Image.new('L', (1, 1)))
        
        last_yield_time = time.time()
        
        for i in range(attempts):
            # Frequent yield check for smooth streaming
            if i % 1000 == 0:
                current_time = time.time()
                if current_time - last_yield_time > 0.2:
                    yield output.convert('RGB')
                    last_yield_time = current_time

            if consecutive_failures > max_failures:
                break
                
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            
            # Quick check: is the center even in the mask and unoccupied?
            if y >= height or x >= width or not mask[y, x] or occupied[y, x]:
                consecutive_failures += 1
                continue
            
            # Select word avoiding proximity
            word = None
            # Try a few times to pick a word that satisfies distance check
            for _ in range(5):
                 candidate = random.choice(all_words)
                 
                 # Check distance to existing instances of this word
                 # Only check words placed in the same or previous (larger) passes
                 # Actually just check global history for this word
                 if candidate not in word_positions:
                     word = candidate
                     break
                     
                 # Check distances
                 too_close = False
                 for px, py in word_positions[candidate]:
                     dist = np.sqrt((x-px)**2 + (y-py)**2)
                     if dist < current_min_dist:
                         too_close = True
                         break
                 
                 if not too_close:
                     word = candidate
                     break
            
            # If we couldn't find a good word, just pick one (better to fill than leave empty?)
            # Or skip? User prefers distribution. Let's skip position if we really can't find a valid word.
            # But that might leave holes.
            # Compromise: if size is small, relax constraint
            if not word:
                if size_mult < 0.6:
                    word = random.choice(all_words)
                else:
                    consecutive_failures += 1
                    continue

            is_featured = word in featured
            
            # Boost featured words size in early passes
            this_pass_font = font
            if is_featured and pass_idx == 0:
                 this_pass_font = get_font(int(current_font_size * 1.5))

            angle = random.choice(angles)
            
            # Padding - smaller padding for smaller text to fit tighter
            # Padding - increased to ensure text doesn't touch
            if size_mult <= 0.4:
                padding = 1  # Was 0
            elif size_mult <= 0.6:
                padding = 2  # Was 1
            elif size_mult <= 0.8:
                padding = 5  # Was 2
            else:
                padding = 10 # Was 4
            
            # Measure text using anchor='mm' (middle-middle) to center it at (0,0)
            # bbox will be typically negative left/top and positive right/bottom
            raw_bbox = dummy_draw.textbbox((0, 0), word, font=this_pass_font, anchor='mm')
            # raw_bbox is (x0, y0, x1, y1)
            
            # Add padding to the bbox
            # We want the OCCUPIED region to include padding
            box_x0 = raw_bbox[0] - padding
            box_y0 = raw_bbox[1] - padding
            box_x1 = raw_bbox[2] + padding
            box_y1 = raw_bbox[3] + padding
            
            # Rotate bounds if 90 degrees
            if angle == 90 or angle == -90:
                # Rotate (x, y) -> (-y, x)
                # But for a rect centered at 0:
                # New width = old height, New height = old width
                w = box_x1 - box_x0
                h = box_y1 - box_y0
                
                # Re-center
                box_x0 = -h // 2
                box_x1 = h // 2
                box_y0 = -w // 2
                box_y1 = w // 2
            
            # Calculate world coordinates
            # Since we measured relative to (0,0) as center, and x,y is center:
            left = x + int(box_x0)
            right = x + int(box_x1)
            top = y + int(box_y0)
            bottom = y + int(box_y1)
            
            # Fix empty slices if right <= left due to integer division
            if right <= left: right = left + 1
            if bottom <= top: bottom = top + 1
            
            # Boundary checks
            if left < 0 or top < 0 or right > width or bottom > height:
                consecutive_failures += 1
                continue
            
            # Mask Coverage Check
            mask_slice = mask[top:bottom, left:right]
            if np.mean(mask_slice) < 0.9: 
                consecutive_failures += 1
                continue
            
            # Occupancy Check - STRICT NO OVERLAP
            occupied_slice = occupied[top:bottom, left:right]
            if np.any(occupied_slice):
                consecutive_failures += 1
                continue
            
            # Calculate actual text dimensions for image creation
            # We use the raw untransformed bbox for the text image size
            text_w = raw_bbox[2] - raw_bbox[0]
            text_h = raw_bbox[3] - raw_bbox[1]
            
            # Ensure canvas is large enough for rotation
            dim = max(text_w, text_h) + padding * 2 + 10 # Extra margin for safety
            txt_img = Image.new('RGBA', (dim, dim), (0,0,0,0))
            txt_draw = ImageDraw.Draw(txt_img)
            
            # Draw text at center
            txt_draw.text((dim/2, dim/2), word, font=this_pass_font, anchor='mm', fill=rgb_colors[color_idx % len(rgb_colors)] + (255,))
            
            if angle != 0:
                txt_img = txt_img.rotate(angle)
            
            # Now paste. 
            # We drawn center at (dim/2, dim/2).
            # We want center to be at (x, y).
            paste_x = x - dim // 2
            paste_y = y - dim // 2
            
            output.paste(txt_img, (paste_x, paste_y), txt_img)
            
            # Mark occupancy
            occupied[top:bottom, left:right] = True
            
            # Record position for proximity check
            if word not in word_positions:
                word_positions[word] = []
            word_positions[word].append((x, y))
            
            consecutive_failures = 0
            color_idx += 1
            
            consecutive_failures = 0
            color_idx += 1
            
        # Yield the current state of the image after each pass
        yield output.convert('RGB')
    
    # Final yield to ensure we catch everything
    yield output.convert('RGB')


def process_image(image_data, threshold, invert, words, color_scheme, font_size_key, custom_colors=None):
    """Main processing function."""
    # Decode image
    if ',' in image_data:
        image_data = image_data.split(',')[1]
    image_bytes = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_bytes))
    
    # Convert to RGB
    if image.mode in ('RGBA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        if image.mode == 'RGBA':
            background.paste(image, mask=image.split()[3])
        else:
            background.paste(image)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Resize if needed
    width, height = image.size
    # Resize to target dimension (Upscale or Downscale)
    ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
    # Only resize if the ratio is significantly different from 1 (avoid minor resampling artifacts if exact)
    if abs(ratio - 1.0) > 0.001:
        new_size = (int(width * ratio), int(height * ratio))
        image = image.resize(new_size, Image.LANCZOS)
        width, height = new_size
    
    # Create mask
    mask = create_mask(image, threshold, invert)
    
    # Get colors
    if color_scheme == 'custom' and custom_colors:
        colors = [c for c in custom_colors if c.startswith('#')]
        if not colors:
            colors = COLOR_SCHEMES['warm_red']
    else:
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES['warm_red'])
    
    # Calculate font size based on image size
    base_size = FONT_SIZES.get(font_size_key, FONT_SIZES['medium'])
    scale = min(width, height) / 500
    base_font_size = max(10, int(base_size * scale))
    
    # Generate typographic image (Streaming)
    for intermediate_result in place_words_dense(width, height, mask, words, colors, base_font_size):
        # Convert to PNG
        output_buffer = io.BytesIO()
        intermediate_result.save(output_buffer, format='PNG')
        output_buffer.seek(0)
        
        result_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
        yield f"data:image/png;base64,{result_base64}"


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        
        image_data = data.get('image')
        threshold = int(data.get('threshold', 128))
        invert = bool(data.get('invert', False))
        words = data.get('words', [])
        color_scheme = data.get('colorScheme', 'warm_red')
        font_size = data.get('fontSize', 'medium')
        custom_colors = data.get('customColors', [])
        
        if not image_data:
            return jsonify({'error': 'No image provided'}), 400
        if not words:
            return jsonify({'error': 'No words provided'}), 400
        
        def generate_stream():
            try:
                for result_uri in process_image(
                    image_data, threshold, invert, words,
                    color_scheme, font_size, custom_colors
                ):
                    # Format as Server-Sent Event or just ndjson
                    # We'll use a simple line-delimited JSON for ease of parsing
                    yield json.dumps({'result': result_uri}) + '\n'
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield json.dumps({'error': str(e)}) + '\n'

        return Response(generate_stream(), mimetype='application/x-ndjson')
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/color-schemes', methods=['GET'])
def get_color_schemes():
    return jsonify(COLOR_SCHEMES)


if __name__ == '__main__':
    print("Starting Typographic Portrait Generator...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
