"""
Typographic Portrait Generator - Backend Server

Two-Phase Rendering Architecture:
1. Layout & Preview: Fast placement at 2048px with 1x text (streamed live).
2. High-Quality Re-render: All placed words re-rendered at 4096px with 2x supersampling.
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

LAYOUT_REF_SIZE = 512
PREVIEW_MAX_SIZE = 2048   # Fast placement & streaming
FINAL_MAX_SIZE = 4096     # Crisp output (re-rendered at end)
RENDER_SCALE = 4          # Layout-to-preview ratio

# Performance Tracing Toggle
DEBUG_PERF = True

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_font(size):
    """
    Get a scalable font at the specified size.
    On macOS, we prioritize heavy fonts like Impact for the portrait effect.
    """
    size = int(size)
    if size < 1: size = 1
    
    font_names = [
        '/System/Library/Fonts/Supplemental/Impact.ttf',
        '/System/Library/Fonts/Supplemental/Arial Black.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Helvetica-Bold.ttc',
        'Impact', 'Arial Black', 'Arial Bold', 'Helvetica-Bold', 'Arial'
    ]
    
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
            
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except:
        return ImageFont.load_default()

def compute_integral_image(img):
    return img.cumsum(axis=0).cumsum(axis=1)

def find_valid_positions_vectorized(integral_occupancy, integral_mask, width, height, word_w, word_h, mask_threshold=0.98):
    if word_w <= 0 or word_h <= 0: return np.array([]), np.array([])
    out_h, out_w = height - word_h + 1, width - word_w + 1
    if out_h <= 0 or out_w <= 0: return np.array([]), np.array([])

    i_occ_pad = np.pad(integral_occupancy, ((1,0), (1,0)), mode='constant', constant_values=0)
    i_mask_pad = np.pad(integral_mask, ((1,0), (1,0)), mode='constant', constant_values=0)
    
    # Corners
    br = i_occ_pad[word_h : word_h+out_h, word_w : word_w+out_w]
    tr = i_occ_pad[0      : out_h,        word_w : word_w+out_w]
    bl = i_occ_pad[word_h : word_h+out_h, 0      : out_w]
    tl = i_occ_pad[0      : out_h,        0      : out_w]
    occupancy_sums = br - tr - bl + tl
    
    br_m = i_mask_pad[word_h : word_h+out_h, word_w : word_w+out_w]
    tr_m = i_mask_pad[0      : out_h,        word_w : word_w+out_w]
    bl_m = i_mask_pad[word_h : word_h+out_h, 0      : out_w]
    tl_m = i_mask_pad[0      : out_h,        0      : out_w]
    mask_sums = br_m - tr_m - bl_m + tl_m
    
    required_mask_sum = (word_w * word_h) * mask_threshold
    valid_grid = (occupancy_sums == 0) & (mask_sums >= required_mask_sum)
    return np.nonzero(valid_grid)

def place_words_dual_res(image, words, colors, background_color='transparent', threshold=128, invert=False, telemetry_sink=None, show_legend=False):
    orig_w, orig_h = image.size
    start_total = time.time()

    # Preview resolution for fast placement & streaming
    preview_sf = min(PREVIEW_MAX_SIZE / orig_w, PREVIEW_MAX_SIZE / orig_h)
    render_w, render_h = int(orig_w * preview_sf), int(orig_h * preview_sf)
    layout_w, layout_h = render_w // RENDER_SCALE, render_h // RENDER_SCALE

    # Final resolution for crisp output
    final_sf = min(FINAL_MAX_SIZE / orig_w, FINAL_MAX_SIZE / orig_h)
    final_w, final_h = int(orig_w * final_sf), int(orig_h * final_sf)
    upscale = final_sf / preview_sf  # ratio from preview to final coords
    
    gray = image.convert('L').resize((layout_w, layout_h), Image.LANCZOS)
    mask_array = np.array(gray)
    mask = (mask_array >= threshold).astype(np.int32) if invert else (mask_array < threshold).astype(np.int32)
    integral_mask = compute_integral_image(mask)
    occ_h = np.zeros((layout_h, layout_w), dtype=np.int32)
    occ_v = np.zeros((layout_h, layout_w), dtype=np.int32)
    
    bg = (255, 255, 255, 0)
    if background_color == 'white': bg = (255, 255, 255, 255)
    elif background_color == 'black': bg = (0, 0, 0, 255)
    render_canvas = Image.new('RGBA', (render_w, render_h), bg)
    
    featured = [w[1:].upper() for w in words if w.strip().startswith('*')]
    regular = [w.upper() for w in words if w.strip() and not w.strip().startswith('*')]
    all_words = featured + regular if featured or regular else ['TEXT']
    rgb_colors = [hex_to_rgb(c) for c in colors]
    
    # Updated geometric scale: 18pt to 4pt
    layout_font_sizes = [18, 14, 11, 8, 6, 4, 3]
    
    # --- DYNAMIC GROUPING LOGIC ---
    num_fonts = len(layout_font_sizes)
    # Largest third (can round down)
    header_count = max(1, num_fonts // 3)
    
    headers = layout_font_sizes[:header_count]
    grout = layout_font_sizes[-2:] if num_fonts >= 2 else layout_font_sizes[-1:]
    
    # --- IMPROVED COVERAGE BUDGETING ---
    total_mask_pixels = np.sum(mask)
    if total_mask_pixels == 0: total_mask_pixels = 1 
    
    # We want a total coverage of ~85%. 
    # Let's allocate specific slices of the TOTAL silhouette to each pass.
    coverage_slices = {} # Percentage of TOTAL silhouette per pass
    
    # Headers (~20% total)
    for lfs in headers: coverage_slices[lfs] = 0.20 / header_count
    
    # Texture (~25% total)
    texture_fonts = [l for l in layout_font_sizes if l not in headers and l not in grout]
    for lfs in texture_fonts: coverage_slices[lfs] = 0.25 / max(1, len(texture_fonts))
    
    # Grout 1 (~20%)
    if len(grout) > 0: coverage_slices[grout[0]] = 0.20
    
    # Grout 2 (The "Exhaustion" pass - target the remaining gap up to 85% total)
    # This pass will just try to fill as much as possible until max_failures.
    if len(grout) > 1: coverage_slices[grout[1]] = 0.20 # Reasonable cap
    
    dummy_draw = ImageDraw.Draw(Image.new('L', (1, 1)))
    color_idx = 0
    placements = []  # Store (word, angle, px, py, rfs, color_rgba) for final re-render
    last_yield_time = time.time()
    angles = [0, 90]
    
    print(f"Dual-res packing (N/3 Hierarchy): {layout_w}x{layout_h} layout -> {render_w}x{render_h} render")
    print(f"Groups: Headers={headers}, Grout={grout}")
    
    setup_end = time.time()
    setup_duration_ms = (setup_end - start_total) * 1000
    
    # Send setup telemetry event
    if telemetry_sink is not None:
        telemetry_sink.append({
            'event': 'phase_complete',
            'phase': 'setup',
            'duration_ms': setup_duration_ms
        })
    
    total_pixels_placed = 0
    
    for pass_idx, lfs in enumerate(layout_font_sizes):
        pass_start = time.time()
        render_font_base = lfs * RENDER_SCALE
        is_feature = (pass_idx == 0 and featured)
        
        target_pass_pixels = total_mask_pixels * coverage_slices.get(lfs, 0.05)
        pixels_placed_this_pass = 0
        
        # Dynamic behavior assignment: Balanced Density vs Variety
        if lfs in headers:
            batch_size, max_failures = 10, 25
            max_per_batch = 2 
            layout_padding = 1
        elif lfs in grout:
            batch_size, max_failures = 200, 150 # Aggressive early-exit for filler
            max_per_batch = 8 
            layout_padding = 0 
        else:
            batch_size, max_failures = 40, 50 
            max_per_batch = 4 
            layout_padding = 1
            
        # Selective Padding Config
        base_p = 1.0 
        long_plane_p = 3.0
            
        consecutive_failures = 0
        
        print(f"--- FONT PASS: {lfs}pt (Target: {int(target_pass_pixels)}px) ---")
        
        horiz_pixels, vert_pixels = 0, 0
        
        # --- CACHING STRATEGY ---
        render_cache = {} 
        dirty_integral = True
        cached_integral_all, cached_integral_h, cached_integral_v = None, None, None
        
        last_pass_pixels = pixels_placed_this_pass # Initialize for the pass
        dirty_render = False

        while pixels_placed_this_pass < target_pass_pixels:
            if consecutive_failures > max_failures: break
            
            # AGGRESSIVE ORIENTATION BALANCE 
            h_v_ratio = horiz_pixels / (vert_pixels + 1)
            angle_choices = [90] if h_v_ratio > 1.1 else ([0] if h_v_ratio < 0.9 else angles)
            angle = random.choice(angle_choices)
            word = random.choice(featured if is_feature else all_words)
            
            cache_key = (word, angle)
            if cache_key in render_cache:
                txt_final, wl_w_base, wl_h_base, wl_w_long, wl_h_long, final_pw, final_ph, rfs = render_cache[cache_key]
            else:
                rfs = render_font_base
                if is_feature and word in featured: rfs = int(render_font_base * 1.5)

                # Fast 1x render for placement & preview (no supersampling)
                font_preview = get_font(rfs)
                bbox = dummy_draw.textbbox((0, 0), word, font=font_preview, anchor='mm')
                rw_h, rh_h = bbox[2]-bbox[0], bbox[3]-bbox[1]
                tmp_dim = int(max(rw_h, rh_h) + 40)

                txt_tmp = Image.new('RGBA', (tmp_dim, tmp_dim), (0,0,0,0))
                draw_tmp = ImageDraw.Draw(txt_tmp)
                draw_tmp.text((tmp_dim/2, tmp_dim/2), word, font=font_preview, anchor='mm', fill=rgb_colors[color_idx % len(rgb_colors)]+(255,))

                if angle == 90: txt_tmp = txt_tmp.transpose(Image.ROTATE_90)
                elif angle == -90: txt_tmp = txt_tmp.transpose(Image.ROTATE_270)

                ink_bbox_h = txt_tmp.getbbox()
                if not ink_bbox_h:
                    consecutive_failures += 1; continue
                txt_final = txt_tmp.crop(ink_bbox_h)
                final_pw, final_ph = txt_final.size
                
                wl_w_base = int(np.ceil((final_pw + base_p * 2 * RENDER_SCALE) / RENDER_SCALE))
                wl_h_base = int(np.ceil((final_ph + base_p * 2 * RENDER_SCALE) / RENDER_SCALE))
                wl_w_long = int(np.ceil((final_pw + (base_p + long_plane_p) * 2 * RENDER_SCALE) / RENDER_SCALE)) if angle == 0 else wl_w_base
                wl_h_long = wl_h_base if angle == 0 else int(np.ceil((final_ph + (base_p + long_plane_p) * 2 * RENDER_SCALE) / RENDER_SCALE))

                render_cache[cache_key] = (txt_final, wl_w_base, wl_h_base, wl_w_long, wl_h_long, final_pw, final_ph, rfs)

            # --- INTEGRAL CACHE REFRESH ---
            if dirty_integral:
                occ_all = occ_h | occ_v
                cached_integral_all, cached_integral_h, cached_integral_v = compute_integral_image(occ_all), compute_integral_image(occ_h), compute_integral_image(occ_v)
                dirty_integral = False

            integral_occ_same = cached_integral_h if angle == 0 else cached_integral_v

            # --- VECTORIZED SEARCH (Base + Long Plane) ---
            search_start = time.time()
            
            # 1. Base check (Small gap vs ALL)
            i_occ_all_pad = np.pad(cached_integral_all, ((1,0), (1,0)), mode='constant', constant_values=0)
            i_mask_pad = np.pad(integral_mask, ((1,0), (1,0)), mode='constant', constant_values=0)
            out_h_b, out_w_b = layout_h - wl_h_base + 1, layout_w - wl_w_base + 1
            if out_h_b <= 0 or out_w_b <= 0: consecutive_failures += 1; continue
            occ_base_sums = i_occ_all_pad[wl_h_base:wl_h_base+out_h_b, wl_w_base:wl_w_base+out_w_b] - i_occ_all_pad[0:out_h_b, wl_w_base:wl_w_base+out_w_b] - i_occ_all_pad[wl_h_base:wl_h_base+out_h_b, 0:out_w_b] + i_occ_all_pad[0:out_h_b, 0:out_w_b]
            mask_sums = i_mask_pad[wl_h_base:wl_h_base+out_h_b, wl_w_base:wl_w_base+out_w_b] - i_mask_pad[0:out_h_b, wl_w_base:wl_w_base+out_w_b] - i_mask_pad[wl_h_base:wl_h_base+out_h_b, 0:out_w_b] + i_mask_pad[0:out_h_b, 0:out_w_b]
            valid_base = (occ_base_sums == 0) & (mask_sums >= (wl_w_base * wl_h_base) * (0.82 if lfs in grout else 0.92))
            
            # 2. Long check (Large gap vs SAME)
            i_occ_same_pad = np.pad(integral_occ_same, ((1,0), (1,0)), mode='constant', constant_values=0)
            out_h_l, out_w_l = layout_h - wl_h_long + 1, layout_w - wl_w_long + 1
            limit_h, limit_w = min(out_h_b, out_h_l), min(out_w_b, out_w_l)
            if limit_h <= 0 or limit_w <= 0: consecutive_failures += 1; continue
            occ_long_sums = i_occ_same_pad[wl_h_long:wl_h_long+limit_h, wl_w_long:wl_w_long+limit_w] - i_occ_same_pad[0:limit_h, wl_w_long:wl_w_long+limit_w] - i_occ_same_pad[wl_h_long:wl_h_long+limit_h, 0:limit_w] + i_occ_same_pad[0:limit_h, 0:limit_w]
            
            # Combine the two masks (constrained to the smaller limit area)
            ys, xs = np.nonzero(valid_base[:limit_h, :limit_w] & (occ_long_sums == 0))
            
            search_end = time.time()
            
            if len(ys) == 0:
                consecutive_failures += 1; continue
                
            consecutive_failures = 0
            idx_list = random.sample(range(len(ys)), min(len(ys), batch_size))
            bf, placed_in_batch = [], 0
            
            for idx in idx_list:
                if pixels_placed_this_pass >= target_pass_pixels or placed_in_batch >= max_per_batch: break
                lx, ly = xs[idx], ys[idx]
                if any(not (lx + wl_w_base <= bx or lx >= bx + bw or ly + wl_h_base <= by or ly >= by + bh) for bx, by, bw, bh in bf): continue
                
                # PASTE on preview canvas
                px, py = int((lx + wl_w_base/2) * RENDER_SCALE - final_pw/2), int((ly + wl_h_base/2) * RENDER_SCALE - final_ph/2)
                render_canvas.alpha_composite(txt_final, (max(0, px), max(0, py)))

                # Store placement for high-quality re-render
                placements.append((word, angle, lx, ly, wl_w_base, wl_h_base, rfs, rgb_colors[color_idx % len(rgb_colors)]))
                
                if angle == 0: occ_h[ly:ly+wl_h_base, lx:lx+wl_w_base] = 1
                else: occ_v[ly:ly+wl_h_base, lx:lx+wl_w_base] = 1
                
                bf.append((lx, ly, wl_w_base, wl_h_base))
                pixels_placed_this_pass += (wl_w_base * wl_h_base)
                if angle == 0: horiz_pixels += (wl_w_base * wl_h_base)
                else: vert_pixels += (wl_w_base * wl_h_base)
                
                dirty_integral = True; dirty_render = True 
                placed_in_batch += 1; color_idx += 1
        
            # Update UI if changed and throttled
            now = time.time()
            if dirty_render and now - last_yield_time > 0.4:
                yield (render_canvas, False)
                last_yield_time = now
                dirty_render = False

        if DEBUG_PERF:
            pass_duration = (time.time() - pass_start) * 1000
            print(f"  [Pass {lfs}pt] Finished in {pass_duration:.0f}ms. Placed {pixels_placed_this_pass}px ({pixels_placed_this_pass/total_mask_pixels*100:.1f}%)")
        else:
            pass_duration = (time.time() - pass_start) * 1000
            
        total_pixels_placed += pixels_placed_this_pass

        if telemetry_sink is not None:
            telemetry_sink.append({
                'event': 'pass_complete',
                'font_size': lfs,
                'render_font_size': render_font_base,
                'duration_ms': pass_duration,
                'target_pixels': int(target_pass_pixels),
                'actual_pixels': int(pixels_placed_this_pass),
                'coverage_pct': (pixels_placed_this_pass / total_mask_pixels) * 100,
                'horiz_pct': (horiz_pixels / pixels_placed_this_pass * 100) if pixels_placed_this_pass > 0 else 0,
                'vert_pct': (vert_pixels / pixels_placed_this_pass * 100) if pixels_placed_this_pass > 0 else 0
            })
                
        yield (render_canvas, False)
    
    if DEBUG_PERF:
        final_coverage = (total_pixels_placed / total_mask_pixels) * 100
        print(f"--- PLACEMENT COMPLETE --- Total Coverage: {final_coverage:.1f}% ({len(placements)} words placed)")

    # --- PHASE 2: HIGH-QUALITY RE-RENDER at final resolution ---
    rerender_start = time.time()
    print(f"--- RE-RENDER PHASE: {final_w}x{final_h} ({len(placements)} words) ---")

    final_canvas = Image.new('RGBA', (final_w, final_h), bg)
    hq_dummy_draw = ImageDraw.Draw(Image.new('L', (1, 1)))
    quality_scale = 2  # 2x supersample for crisp text

    for word, angle, lx, ly, wl_w, wl_h, rfs_preview, color_rgb in placements:
        # Scale font size from preview to final resolution
        rfs_final = rfs_preview * upscale
        font_hq = get_font(int(rfs_final * quality_scale))

        bbox = hq_dummy_draw.textbbox((0, 0), word, font=font_hq, anchor='mm')
        rw_h, rh_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tmp_dim = int(max(rw_h, rh_h) + 40)

        txt_tmp = Image.new('RGBA', (tmp_dim, tmp_dim), (0, 0, 0, 0))
        draw_tmp = ImageDraw.Draw(txt_tmp)
        draw_tmp.text((tmp_dim / 2, tmp_dim / 2), word, font=font_hq, anchor='mm', fill=color_rgb + (255,))

        if angle == 90: txt_tmp = txt_tmp.transpose(Image.ROTATE_90)
        elif angle == -90: txt_tmp = txt_tmp.transpose(Image.ROTATE_270)

        ink_bbox = txt_tmp.getbbox()
        if not ink_bbox: continue
        txt_hq = txt_tmp.crop(ink_bbox)

        # Downscale from quality_scale to final size
        hq_w, hq_h = txt_hq.size
        txt_final_hq = txt_hq.resize((hq_w // quality_scale, hq_h // quality_scale), Image.LANCZOS)
        fw, fh = txt_final_hq.size

        # Compute paste position in final coordinates
        px = int((lx + wl_w / 2) * RENDER_SCALE * upscale - fw / 2)
        py = int((ly + wl_h / 2) * RENDER_SCALE * upscale - fh / 2)
        final_canvas.alpha_composite(txt_final_hq, (max(0, px), max(0, py)))

    if DEBUG_PERF:
        rerender_duration = (time.time() - rerender_start) * 1000
        print(f"  [Re-render] {len(placements)} words in {rerender_duration:.0f}ms")

    # --- ADD TESTING LEGEND (TOP-LEFT) ---
    if show_legend:
        legend_padding = 20
        row_heights = [max(18, int(lfs * RENDER_SCALE * 0.8)) for lfs in layout_font_sizes]
        total_legend_h = sum(row_heights) + (legend_padding * 2) + (10 * len(row_heights))

        legend_w = 400
        overlay = Image.new('RGBA', (legend_w, total_legend_h), (0, 0, 0, 180))
        legend_draw = ImageDraw.Draw(overlay)

        current_y = legend_padding
        for i, lfs in enumerate(layout_font_sizes):
            rfs = lfs * RENDER_SCALE
            sample_word = random.choice(all_words)
            display_size = max(6, int(rfs * 0.9))
            legend_font = get_font(display_size)
            text_label = f"Size {rfs}: {sample_word}"
            legend_draw.text((20, current_y), text_label, font=legend_font, fill=(255, 255, 255, 255))
            current_y += row_heights[i] + 10

        final_canvas.alpha_composite(overlay, (30, 30))

    finalize_end = time.time()
    finalize_duration_ms = (finalize_end - rerender_start) * 1000
    if telemetry_sink is not None:
        telemetry_sink.append({
            'event': 'phase_complete',
            'phase': 'finalize',
            'duration_ms': finalize_duration_ms
        })

    yield (final_canvas, True)

def process_image(image_data, words, color_scheme, background_color='transparent', threshold=128, invert=False, custom_colors=None):
    if ',' in image_data: image_data = image_data.split(',')[1]
    image_bytes = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_bytes))
    if color_scheme == 'custom' and custom_colors:
        colors = [c for c in custom_colors if c.startswith('#')]
        if not colors: colors = COLOR_SCHEMES['warm_red']
    else:
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES['warm_red'])
        
    for res_img, is_final in place_words_dual_res(image, words, colors, background_color, threshold, invert):
        io_start = time.time()
        buf = io.BytesIO()
        if is_final:
            # PNG compression level 1 is much faster than level 6 (default)
            res_img.save(buf, format='PNG', compress_level=1)
            mime = "image/png"
        elif background_color == 'transparent':
            # Transparent mode: must use PNG to preserve alpha in preview frames
            res_img.save(buf, format='PNG', compress_level=1)
            mime = "image/png"
        else:
            # Quality 80 for sharper preview frames
            res_img.convert('RGB').save(buf, format='JPEG', quality=80)
            mime = "image/jpeg"
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode('utf-8')
        yield json.dumps({'result': f"data:{mime};base64,{encoded}"}) + '\n'
        
        if DEBUG_PERF:
            io_duration = (time.time() - io_start) * 1000
            print(f"  [I/O Trace] Encode & Yield: {io_duration:.1f}ms ({'PNG' if is_final else 'JPEG'})")

@app.route('/')
def index(): return send_from_directory('static', 'index.html')
@app.route('/<path:path>')
def static_files(path): return send_from_directory('static', path)

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        image_data, words = data.get('image'), data.get('words', [])
        color_scheme, background_color = data.get('colorScheme', 'warm_red'), data.get('backgroundColor', 'transparent')
        threshold, invert = int(data.get('threshold', 128)), bool(data.get('invert', False))
        custom_colors = data.get('customColors', [])
        if not image_data or not words: return jsonify({'error': 'Missing data'}), 400
        def stream():
            try:
                for json_chunk in process_image(image_data, words, color_scheme, background_color, threshold, invert, custom_colors):
                    yield json_chunk
            except Exception as e:
                import traceback; traceback.print_exc()
                yield json.dumps({'error': str(e)}) + '\n'
        return Response(stream(), mimetype='application/x-ndjson')
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/color-schemes', methods=['GET'])
def get_color_schemes(): return jsonify(COLOR_SCHEMES)

if __name__ == '__main__':
    print("Starting Typographic Portrait Generator...")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
