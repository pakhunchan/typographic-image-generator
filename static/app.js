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
const backgroundColor = document.getElementById('backgroundColor');
const fontSize = document.getElementById('fontSize');
const wordsInput = document.getElementById('wordsInput');
const wordCount = document.getElementById('wordCount');
const generateBtn = document.getElementById('generateBtn');
const resultContainer = document.getElementById('resultContainer');
const resultPlaceholder = document.getElementById('resultPlaceholder');
const resultImage = document.getElementById('resultImage');
const downloadBtn = document.getElementById('downloadBtn');
const boldBtn = document.getElementById('boldBtn');

// State
let currentImageData = null;
let originalFileName = 'image';

// Initialize
function init() {
    setupEventListeners();
    updateColorPreview();
    updateWordCount();
    updateBackgroundPreview();
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
    backgroundColor.addEventListener('change', updateBackgroundPreview);
    wordsInput.addEventListener('input', updateWordCount);
    wordsInput.addEventListener('keydown', handleWordsKeydown);
    wordsInput.addEventListener('paste', handleWordsPaste);
    boldBtn.addEventListener('click', toggleBoldSelection);

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
    // Store original filename without extension
    const name = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;
    // Sanitize and truncate to max 32 chars for practical length
    originalFileName = name.replace(/[^a-zA-Z0-9-_]/g, '_').substring(0, 32);

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
    thresholdValue.textContent = thresholdSlider.value + '%';
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

// Background preview grid
function updateBackgroundPreview() {
    if (backgroundColor.value === 'transparent') {
        resultContainer.classList.add('checkerboard');
    } else {
        resultContainer.classList.remove('checkerboard');
    }
}

// Editor logic
function handleWordsKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleBoldSelection();
        return;
    }

    if (e.key === 'Enter') {
        e.preventDefault();
        document.execCommand('insertHTML', false, '<div class="word-line"><br></div>');
        updateWordCount();
    }
}

function handleWordsPaste(e) {
    e.preventDefault();
    const text = (e.originalEvent || e).clipboardData.getData('text/plain');
    const lines = text.split(/\r?\n/).filter(line => line.trim());

    const html = lines.map(line => {
        const isFeatured = line.trim().startsWith('*');
        const content = isFeatured ? line.trim().substring(1) : line.trim();
        return `<div class="word-line${isFeatured ? ' featured' : ''}">${content}</div>`;
    }).join('');

    document.execCommand('insertHTML', false, html);
    updateWordCount();
}

function toggleBoldSelection() {
    const selection = window.getSelection();
    if (!selection.rangeCount) return;

    const range = selection.getRangeAt(0);
    const editor = document.getElementById('wordsInput');

    // Find all word-lines that are at least partially selected
    const allLines = Array.from(editor.querySelectorAll('.word-line'));
    const selectedLines = allLines.filter(line => selection.containsNode(line, true));

    // If no specific lines are found (e.g. just a cursor), try the parent of the selection
    if (selectedLines.length === 0) {
        let node = range.commonAncestorContainer;
        if (node.nodeType === 3) node = node.parentNode;
        const line = node.closest('.word-line');
        if (line) selectedLines.push(line);
    }

    if (selectedLines.length > 0) {
        // Determine if we are turning bold ON or OFF 
        // (If any selected line is NOT featured, we turn them all ON)
        const anyNotFeatured = selectedLines.some(l => !l.classList.contains('featured'));

        selectedLines.forEach(line => {
            if (anyNotFeatured) {
                line.classList.add('featured');
            } else {
                line.classList.remove('featured');
            }

            // Clean up any internal <b> or <strong> tags injected by the browser
            // to ensure "partial bolding" doesn't happen inside labels
            const cleanText = line.innerText;
            line.innerHTML = cleanText === "" ? "<br>" : cleanText;
        });

        updateWordCount();
    }
}

function updateWordCount() {
    const lines = Array.from(wordsInput.querySelectorAll('.word-line'));
    const total = lines.filter(l => l.innerText.trim()).length;
    const featured = lines.filter(l => l.classList.contains('featured') && l.innerText.trim()).length;

    wordCount.textContent = `${total} word${total !== 1 ? 's' : ''}${featured > 0 ? ` (${featured} featured)` : ''}`;
}

// Auto-select is now less useful for rich editor but we can keep a simpler version
function handleWordsFocus() {
    if (wordsInput.innerText.trim() === "LOVE\nHAPPY\nFUN") {
        const range = document.createRange();
        range.selectNodeContents(wordsInput);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }
}

// Generate
async function handleGenerate() {
    // Validation
    if (!currentImageData) {
        alert('Please upload an image first');
        return;
    }

    // Parse from rich editor
    const editorLines = Array.from(wordsInput.querySelectorAll('.word-line'));
    let words = editorLines.map(line => {
        const text = line.innerText.trim();
        if (!text) return null;
        return (line.classList.contains('featured') ? '*' : '') + text;
    }).filter(w => w !== null);

    // Fallback if empty to avoid error
    if (words.length === 0) {
        words = ['*LOVE', 'HAPPY', 'FUN'];
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
                threshold: Math.round(parseInt(thresholdSlider.value, 10) * 2.55),
                invert: invertCheckbox.checked,
                words: words,
                colorScheme: scheme,
                fontSize: fontSize.value,
                backgroundColor: backgroundColor.value,
                customColors: customColorsList,
            }),
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Server Error: ${response.status} ${errText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // Show result placeholder initially (to prepare for first frame)
        resultPlaceholder.classList.add('hidden');
        resultImage.classList.remove('hidden');
        downloadBtn.classList.add('hidden'); // Hide until finished

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete lines
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete chunk

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    if (data.result) {
                        resultImage.src = data.result;
                    }
                } catch (e) {
                    console.warn("Error parsing stream line:", e);
                }
            }
        }

        // Stream finished
        downloadBtn.classList.remove('hidden');

    } catch (error) {
        console.error('Generation failed:', error);
        alert('Generation failed: ' + error.message);
        resultPlaceholder.classList.remove('hidden');
        resultImage.classList.add('hidden');
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
    if (!resultImage.src || resultImage.src.includes('placeholder')) {
        console.error('No result image to download');
        return;
    }

    try {
        console.log("Initiating download...");
        const fileName = `PHC_typographic_${originalFileName}.png`;

        // Create a temporary link element
        const link = document.createElement('a');

        // Direct Data URI approach - safer for small/medium images to avoid Blob quirks
        link.href = resultImage.src;
        link.download = fileName;

        // Append to body
        document.body.appendChild(link);

        // Trigger click
        link.click();

        // Clean up with longer delay
        setTimeout(() => {
            document.body.removeChild(link);
            console.log("Download cleanup complete");
        }, 1000);

    } catch (error) {
        console.error('Download failed:', error);
        alert('Download error: ' + error.message);
    }
}

// Listen for custom color changes
customColors.addEventListener('input', updateColorPreview);

// Initialize app
init();
