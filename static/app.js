/**
 * Typographic Portrait Generator - Frontend Logic
 */

// Color schemes matching backend
const COLOR_SCHEMES = {
    warm_red: ['#8B0000', '#CD5C5C', '#FF6347', '#FFA500', '#FFD700'],
    ocean_blue: ['#000080', '#4169E1', '#00CED1', '#87CEEB', '#E0FFFF'],
    forest_green: ['#006400', '#228B22', '#32CD32', '#90EE90', '#98FB98'],
    sunset: ['#FF1493', '#FF4500', '#FFA500', '#FFD700', '#FFFF00'],
    monochrome: ['#000000', '#333333', '#666666', '#999999', '#CCCCCC'],
};

// DOM Elements
const uploadZone = document.getElementById('uploadZone');
const imageInput = document.getElementById('imageInput');
const uploadPlaceholder = document.getElementById('uploadPlaceholder');
const previewImage = document.getElementById('previewImage');
const thresholdSlider = document.getElementById('thresholdSlider');
const thresholdValue = document.getElementById('thresholdValue');
const invertCheckbox = document.getElementById('invertCheckbox');
const colorScheme = document.getElementById('colorScheme');
const colorPreview = document.getElementById('colorPreview');
const customColorsGroup = document.getElementById('customColorsGroup');
const customColors = document.getElementById('customColors');
const fontSize = document.getElementById('fontSize');
const wordsInput = document.getElementById('wordsInput');
const wordCount = document.getElementById('wordCount');
const generateBtn = document.getElementById('generateBtn');
const resultContainer = document.getElementById('resultContainer');
const resultPlaceholder = document.getElementById('resultPlaceholder');
const resultImage = document.getElementById('resultImage');
const downloadBtn = document.getElementById('downloadBtn');

// State
let currentImageData = null;

// Initialize
function init() {
    setupEventListeners();
    updateColorPreview();
    updateWordCount();
}

// Event Listeners
function setupEventListeners() {
    // Upload zone interactions
    uploadZone.addEventListener('click', () => imageInput.click());
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', handleDragLeave);
    uploadZone.addEventListener('drop', handleDrop);
    imageInput.addEventListener('change', handleImageSelect);

    // Controls
    thresholdSlider.addEventListener('input', handleThresholdChange);
    colorScheme.addEventListener('change', handleColorSchemeChange);
    wordsInput.addEventListener('input', updateWordCount);

    // Generate button
    generateBtn.addEventListener('click', handleGenerate);

    // Download button
    downloadBtn.addEventListener('click', handleDownload);
}

// Drag and drop handlers
function handleDragOver(e) {
    e.preventDefault();
    uploadZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('image/')) {
        handleFile(files[0]);
    }
}

// Image selection
function handleImageSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
}

function handleFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        currentImageData = e.target.result;
        previewImage.src = currentImageData;
        previewImage.classList.remove('hidden');
        uploadPlaceholder.classList.add('hidden');
    };
    reader.readAsDataURL(file);
}

// Threshold slider
function handleThresholdChange() {
    thresholdValue.textContent = thresholdSlider.value;
}

// Color scheme
function handleColorSchemeChange() {
    const scheme = colorScheme.value;
    if (scheme === 'custom') {
        customColorsGroup.classList.remove('hidden');
    } else {
        customColorsGroup.classList.add('hidden');
    }
    updateColorPreview();
}

function updateColorPreview() {
    const scheme = colorScheme.value;
    let colors;

    if (scheme === 'custom') {
        const input = customColors.value.trim();
        if (input) {
            colors = input.split(',').map(c => c.trim()).filter(c => c.startsWith('#'));
        } else {
            colors = ['#cccccc'];
        }
    } else {
        colors = COLOR_SCHEMES[scheme] || COLOR_SCHEMES.warm_red;
    }

    colorPreview.innerHTML = colors.map(color =>
        `<div class="color-swatch" style="background-color: ${color}"></div>`
    ).join('');
}

// Word count
function updateWordCount() {
    const words = wordsInput.value.split('\n').filter(w => w.trim()).length;
    const featured = wordsInput.value.split('\n').filter(w => w.trim().startsWith('*')).length;
    wordCount.textContent = `${words} word${words !== 1 ? 's' : ''}${featured > 0 ? ` (${featured} featured)` : ''}`;
}

// Generate
async function handleGenerate() {
    // Validation
    if (!currentImageData) {
        alert('Please upload an image first');
        return;
    }

    const words = wordsInput.value.split('\n').filter(w => w.trim());
    if (words.length === 0) {
        alert('Please enter at least one word');
        return;
    }

    // UI state: loading
    setLoading(true);

    try {
        const scheme = colorScheme.value;
        let customColorsList = [];
        if (scheme === 'custom') {
            customColorsList = customColors.value.split(',').map(c => c.trim()).filter(c => c.startsWith('#'));
        }

        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                image: currentImageData,
                threshold: parseInt(thresholdSlider.value, 10),
                invert: invertCheckbox.checked,
                words: words,
                colorScheme: scheme,
                fontSize: fontSize.value,
                customColors: customColorsList,
            }),
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Show result
        resultImage.src = data.result;
        resultImage.classList.remove('hidden');
        resultPlaceholder.classList.add('hidden');
        downloadBtn.classList.remove('hidden');

    } catch (error) {
        console.error('Generation failed:', error);
        alert('Generation failed: ' + error.message);
    } finally {
        setLoading(false);
    }
}

function setLoading(loading) {
    generateBtn.disabled = loading;
    const btnText = generateBtn.querySelector('.btn-text');
    const btnLoading = generateBtn.querySelector('.btn-loading');

    if (loading) {
        btnText.classList.add('hidden');
        btnLoading.classList.remove('hidden');
    } else {
        btnText.classList.remove('hidden');
        btnLoading.classList.add('hidden');
    }
}

// Download
function handleDownload() {
    if (!resultImage.src) return;

    const link = document.createElement('a');
    link.href = resultImage.src;
    link.download = 'typographic-portrait.png';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Listen for custom color changes
customColors.addEventListener('input', updateColorPreview);

// Initialize app
init();
