
import numpy as np
from PIL import Image
import sys
import os

# Mock the functions to test them in isolation or import them from server
# For this basic test, we'll keep the logic local but update paths
def compute_integral_image(img):
    return img.cumsum(axis=0).cumsum(axis=1)

def find_valid_positions(integral_occupancy, integral_mask, width, height, word_w, word_h, mask_threshold=0.99):
    if word_w <= 0 or word_h <= 0:
        return np.array([]), np.array([])
    out_h = height - word_h + 1
    out_w = width - word_w + 1
    if out_h <= 0 or out_w <= 0:
        return np.array([]), np.array([])
    i_occ_pad = np.pad(integral_occupancy, ((1,0), (1,0)), mode='constant', constant_values=0)
    i_mask_pad = np.pad(integral_mask, ((1,0), (1,0)), mode='constant', constant_values=0)
    
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
    
    area = word_w * word_h
    required_mask_sum = area * mask_threshold
    valid_grid = (occupancy_sums == 0) & (mask_sums >= required_mask_sum)
    ys, xs = np.nonzero(valid_grid)
    return ys, xs

def test_packing():
    # 100x100 mask (central circle)
    width, height = 100, 100
    mask = np.zeros((100, 100), dtype=np.int32)
    for y in range(100):
        for x in range(100):
            if (x-50)**2 + (y-50)**2 < 40**2:
                mask[y, x] = 1
    
    integral_mask = compute_integral_image(mask)
    occupied = np.zeros((100, 100), dtype=np.int32)
    integral_occupancy = compute_integral_image(occupied)
    
    # Try to find a 10x10 box
    ys, xs = find_valid_positions(integral_occupancy, integral_mask, 100, 100, 10, 10, 1.0)
    print(f"Empty board: Found {len(ys)} valid spots for 10x10 box.")
    
    if len(ys) == 0:
        print("FAILED: No spots found on empty board.")
        return

    # Place a box and check if it disappears from valid spots
    y_p, x_p = ys[0], xs[0]
    occupied[y_p:y_p+10, x_p:x_p+10] = 1
    integral_occupancy = compute_integral_image(occupied)
    
    ys_after, xs_after = find_valid_positions(integral_occupancy, integral_mask, 100, 100, 10, 10, 1.0)
    print(f"After placing 1 box: Found {len(ys_after)} valid spots.")
    
    # Check if the placed spot is no longer valid
    for y, x in zip(ys_after, xs_after):
        if y == y_p and x == x_p:
            print("FAILED: Placed spot still marked as valid!")
            return

    print("SUCCESS: Core packing logic verified.")

if __name__ == "__main__":
    test_packing()
