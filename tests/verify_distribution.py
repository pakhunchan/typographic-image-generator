
import os
import sys
import numpy as np
from PIL import Image
import json

# Add project root to sys.path so we can import server
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import place_words_dual_res, COLOR_SCHEMES

def run_distribution_test(image_path, words_str):
    if not os.path.exists(image_path):
        print("\n" + "!" * 40)
        print(f"ERROR: Test fixture missing at {image_path}")
        print("FIX: Please ensure you have a PNG image at that path.")
        print(f"Example: cp your_image.png tests/fixtures/test_input.png")
        print("!" * 40 + "\n")
        return

    print(f"--- TYPOGRAPHIC DISTRIBUTION TEST ---")
    print(f"Input: {image_path}")
    print(f"Words: {words_str[:50]}...")
    
    # Load test image
    img = Image.open(image_path)
    words = [w.strip() for w in words_str.split(',') if w.strip()]
    colors = COLOR_SCHEMES['warm_red']
    
    # This list will be populated by the server telemetry hook
    telemetry = []
    
    # Run the generator (Headless)
    print("Running generator...")
    generator = place_words_dual_res(
        img, 
        words, 
        colors, 
        telemetry_sink=telemetry,
        show_legend=True
    )
    
    # Consume the generator to trigger the passes
    final_img = None
    for item in generator:
        if isinstance(item, tuple):
            final_img, is_final = item
        else:
            final_img = item
    
    print("\n" + "="*105)
    print(f"{'PHASE/FONT':<12} | {'TARGET PX':<12} | {'ACTUAL PX':<12} | {'COVERAGE %':<12} | {'H/V RATIO':<12} | {'DURATION':<12} | {'STATUS'}")
    print("-" * 105)
    
    actual_total_pct = 0
    setup_ms = 0
    pass_durations = 0
    
    # 1. FIND SETUP DURATION FIRST
    for t in telemetry:
        if t.get('event') == 'phase_complete' and t.get('phase') == 'setup':
            setup_ms = t['duration_ms']
            break
            
    # Print Pre-Process Row
    print(f"{'PRE-PROCESS':<12} | {'-':<12} | {'-':<12} | {'-':>11}  | {'-':<12} | {setup_ms:>6.0f} ms    | {'DONE'}")

    for t in telemetry:
        if t.get('event') != 'pass_complete': continue
        
        actual_total_pct += t['coverage_pct']
        pass_durations += t['duration_ms']
        
        # Determine status
        if t['target_pixels'] > 0 and t['coverage_pct'] < 90:
            diff = abs(t['actual_pixels'] - t['target_pixels']) / t['target_pixels']
            status = "PASS" if diff < 0.15 else "TUNE"
        else:
            status = "FINAL"
            
        ratio_str = f"{int(t['horiz_pct'])}/{int(t['vert_pct'])}"
        print(f"{t['render_font_size']:<12} | {t['target_pixels']:<12} | {t['actual_pixels']:<12} | {t['coverage_pct']:>11.1f}% | {ratio_str:<12} | {t['duration_ms']:>6.0f} ms    | {status}")

    finalize_ms = 0
    for t in telemetry:
        if t.get('event') == 'phase_complete' and t.get('phase') == 'finalize':
            finalize_ms = t['duration_ms']
            break
            
    print(f"{'POST-PROCESS':<12} | {'-':<12} | {'-':<12} | {'-':>11}  | {'-':<12} | {finalize_ms:>6.0f} ms    | {'DONE'}")

    print("-" * 105)
    print(f"{'TOTAL':<12} | {'':<12} | {'':<12} | {actual_total_pct:>11.1f}% | {'':<12} | {'':<12} | {'DONE'}")
    print("=" * 105)
    
    print(f"\nTIMING BREAKDOWN:")
    print(f"  Pre-Processing:  {setup_ms:.0f} ms")
    print(f"  Font Packing:    {pass_durations:.0f} ms")
    print(f"  Post-Processing: {finalize_ms:.0f} ms")
    
    # --- OUTPUT GENERATION ---
    output_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. STANDALONE TYPOGRAPHY (Transparent background)
    standalone_path = os.path.join(output_dir, "test_typography_only.png")
    final_img.save(standalone_path)
    print(f"Standalone typography saved to: {standalone_path}")
    
    # 2. VISUAL SILHOUETTE VERIFICATION (Stacked/Overlay)
    print("Stacking typography on original for silhouette check...")
    original_bg = img.convert('RGBA').resize(final_img.size, Image.LANCZOS)
    
    # Create a faded version of the original so text is still visible
    overlay_proof = Image.new('RGBA', final_img.size, (255, 255, 255, 255))
    overlay_proof.paste(original_bg, (0, 0))
    
    # Add a white tint to the original to make the text pop
    white_wash = Image.new('RGBA', final_img.size, (255, 255, 255, 180))
    overlay_proof.alpha_composite(white_wash)
    
    # Finally, stack the typography
    overlay_proof.alpha_composite(final_img)
    
    # Save the overlay proof
    overlay_path = os.path.join(output_dir, "test_silhouette_check.png")
    overlay_proof.save(overlay_path)
    print(f"Comparison proof saved to:    {overlay_path}")

if __name__ == "__main__":
    # Point to the fixtures directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_img = os.path.join(base_dir, "fixtures", "test_input.png")
    
    if os.path.exists(test_img):
        test_words = "LOVE, SMILE, BE HAPPY, DON'T WORRY, JOY"
        run_distribution_test(test_img, test_words)
    else:
        print(f"No test fixture found at {test_img}")
