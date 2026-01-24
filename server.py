"""
Typographic Portrait Generator - Backend Server

Converts images into typographic art by filling dark/light regions with text.
"""

import io
import base64
import random
from flask import Flask, request, jsonify, send_from_directory
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

MAX_DIMENSION = 1024


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_font(size):
    """Get a bold font at the specified size."""
    try:
        font_paths = [
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            '/Library/Fonts/Arial Bold.ttf',
            '/Library/Fonts/Arial.ttf',
            'Arial Bold',
            'Arial',
            'Helvetica',
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
    
    # Track occupied regions
    # logical OR of placed text boxes
    occupied = np.zeros((height, width), dtype=bool)
    
    # Restrict angles to Horizontal and Vertical (0, 90)
    # Note: Pillow rotate 90 is counter-clockwise. 
    # Vertical text reading up is 90, reading down is -90/270.
    angles = [0, 0, 0, 90] 
    
    color_idx = 0
    
    # Multi-pass strategy:
    # 1. Very Large (Featured/Big) - Anchor points
    # 2. Large
    # 3. Medium
    # 4. Small
    # 5. Tiny (Fillers)
    # 6. Micro (gap fillers)
    size_multipliers = [3.0, 2.0, 1.2, 0.8, 0.6, 0.4]
    
    # Base density target affects attempts
    # Calculate density target based on image size to keep performance reasonable
    total_pixels = width * height
    base_attempts = int(total_pixels / 200) # Increased base attempts significantly
    
    for pass_idx, size_mult in enumerate(size_multipliers):
        current_font_size = max(8, int(base_font_size * size_mult))
        font = get_font(current_font_size)
        
        # Increase attempts for smaller sizes to ensure filling
        attempts = base_attempts * (pass_idx + 1)
        if size_mult < 1.0:
            attempts *= 4 # Much more attempts for small words
            
        # Optimization: Fail fast if we can't find spots
        consecutive_failures = 0
        max_failures = 20000 # Allow more failures before giving up on a size
        
        for _ in range(attempts):
            if consecutive_failures > max_failures:
                break
                
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            
            # Quick check: is the center even in the mask and unoccupied?
            if y >= height or x >= width or not mask[y, x] or occupied[y, x]:
                consecutive_failures += 1
                continue
                
            word = random.choice(all_words)
            is_featured = word in featured
            
            # Boost featured words size in early passes
            this_pass_font = font
            if is_featured and pass_idx == 0:
                 this_pass_font = get_font(int(current_font_size * 1.5))

            angle = random.choice(angles)
            
            # Measure text
            # We need a temporary measure
            dummy = Image.new('L', (1, 1))
            d_draw = ImageDraw.Draw(dummy)
            bbox = d_draw.textbbox((0, 0), word, font=this_pass_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            # Padding - smaller padding for smaller text to fit tighter
            if size_mult <= 0.6:
                padding = 1
            elif size_mult <= 0.8:
                padding = 2
            else:
                padding = 4
            
            # Effective box size
            box_w = text_w
            box_h = text_h
            
            # Handle rotation dimensions
            if angle == 90 or angle == -90:
                box_w, box_h = box_h, box_w
            
            # Centered coordinates
            left = x - box_w // 2
            top = y - box_h // 2
            right = left + box_w
            bottom = top + box_h
            
            # Boundary checks
            if left < 0 or top < 0 or right > width or bottom > height:
                consecutive_failures += 1
                continue
            
            # Mask Coverage Check
            # We want the text to be deeply inside the mask
            # Check corners and center? Or full slice?
            # Numpy slice is fast.
            mask_slice = mask[top:bottom, left:right]
            
            # We require HIGH coverage (mostly inside the black area)
            # But "filling gaps" might mean we are near edges.
            # Let's say 90% of the box area must be in the mask
            if np.mean(mask_slice) < 0.9: 
                consecutive_failures += 1
                continue
            
            # Occupancy Check - STRICT NO OVERLAP
            # Check if any pixel in the target box is already occupied
            occupied_slice = occupied[top:bottom, left:right]
            if np.any(occupied_slice):
                consecutive_failures += 1
                continue
            
            # If we got here, we can place it!
            consecutive_failures = 0
            
            # Generate image to paste (re-generate with actual size/rotation)
            # Create slightly larger canvas to avoid clipping during rotation
            dim = max(text_w, text_h) + padding * 2
            txt_img = Image.new('RGBA', (dim, dim), (0,0,0,0))
            txt_draw = ImageDraw.Draw(txt_img)
            
            # Draw centered
            txt_draw.text(((dim - text_w)//2, (dim - text_h)//2), word, font=this_pass_font, fill=rgb_colors[color_idx % len(rgb_colors)] + (255,))
            
            if angle != 0:
                txt_img = txt_img.rotate(angle)
            
            # Crop to exact bounding box to minimize "invisible" overlap
            # But simple rotate might have anti-aliasing.
            # We calculated `box_w, box_h` earlier based on geometry.
            # Let's trust our geometry calculation for the occupancy mask, 
            # but paste the image centered.
            
            paste_x = x - dim // 2
            paste_y = y - dim // 2
            
            output.paste(txt_img, (paste_x, paste_y), txt_img)
            
            # Mark occupancy
            # Add a tiny buffer? No, user wants dense.
            occupied[top:bottom, left:right] = True
            
            color_idx += 1
            
    return output.convert('RGB')


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
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
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
    
    # Generate typographic image
    result = place_words_dense(width, height, mask, words, colors, base_font_size)
    
    # Convert to PNG
    output_buffer = io.BytesIO()
    result.save(output_buffer, format='PNG')
    output_buffer.seek(0)
    
    result_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')
    return f"data:image/png;base64,{result_base64}"


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
        
        result = process_image(
            image_data, threshold, invert, words,
            color_scheme, font_size, custom_colors
        )
        
        return jsonify({'result': result})
    
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
