# Typographic Project - Testing Suite

This directory contains automated tests and verification tools for the packing engine.

## 1. Distribution Verification
**File**: `verify_distribution.py`

This is the primary tool for checking the quality of the typographic portraits. It runs the generator and verifies that each font size is taking up its assigned "Real Estate" (Area Budget).

### How to Run:
```bash
python3 tests/verify_distribution.py
```

### Requirements:
- Requires a source image at `tests/fixtures/test_input.png`.
- Outputs a report to the console and a verification image to `tests/test_distribution_proof.png`.

---

2. Core Logic Unit Tests
**File**: `test_packing.py`

A low-level test that verifies the mathematical "Integral Image" search logic. This runs on a tiny synthetic grid and does not require external images. Use this if you are making changes to the core collision detection code.

### How to Run:
```bash
python3 tests/test_packing.py
```

---

3. Fixtures
**Directory**: `fixtures/`
Contains static assets used by the tests (e.g., standard input images).
