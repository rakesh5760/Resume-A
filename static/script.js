const BASE_URL = 'http://127.0.0.1:5000';
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const folderPathInput = document.getElementById('folderPath');
const uploadModule = document.getElementById('uploadModule');
const resultsSection = document.getElementById('resultsSection');
const resultsTableBody = document.querySelector('#resultsTable tbody');
const loader = document.getElementById('loader');
const countVal = document.getElementById('countVal');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');

const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const percentText = document.getElementById('percentText');

let currentExcelFile = null;

// Drag & Drop Handlers
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => handleFiles(fileInput.files));

async function handleFiles(files) {
    if (files.length === 0) return;
    startLoading();

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    try {
        const response = await fetch(`${BASE_URL}/analyze`, {
            method: 'POST',
            body: formData
        });
        await processStream(response);
    } catch (err) {
        console.error(err);
        alert('Server Error during analysis');
    } finally {
        stopLoading();
    }
}

analyzeBtn.addEventListener('click', async () => {
    const path = folderPathInput.value.trim();
    if (!path) return alert('Please enter a folder path');
    startLoading();

    try {
        const response = await fetch(`${BASE_URL}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: path })
        });
        await processStream(response);
    } catch (err) {
        console.error(err);
        alert('Analysis Error. Check if folder path is Correct.');
    } finally {
        stopLoading();
    }
});

async function processStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'progress') {
                    updateProgress(data.current, data.total, data.file);
                } else if (data.type === 'done') {
                    currentExcelFile = data.excel_file;
                    renderResults(data.results);
                }
            }
        }
    }
}

downloadBtn.addEventListener('click', () => {
    if (currentExcelFile) {
        window.location.href = `${BASE_URL}/download/${currentExcelFile}`;
    } else {
        alert('Excel file not generated. Try processing a folder.');
    }
});

resetBtn.addEventListener('click', () => {
    resultsSection.style.display = 'none';
    uploadModule.style.display = 'flex';
    folderPathInput.value = '';
    fileInput.value = '';
});

function renderResults(results) {
    resultsSection.style.display = 'block';
    resultsTableBody.innerHTML = '';
    countVal.textContent = results.length;

    results.forEach(res => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 600;">${res['Candidate Name']}</td>
            <td style="white-space: pre-line; font-size: 0.9rem; color: var(--text-muted);">${res['Current Title']}</td>
            <td style="white-space: pre-line; font-size: 0.9rem;">${res['Skills Summary']}</td>
            <td style="font-weight: 600; color: var(--accent);">${res['Total Experience']}</td>
            <td>
                <button onclick="window.open('${BASE_URL}/view?path=${encodeURIComponent(res['Resume Path'])}', '_blank')" 
                        style="padding: 0.5rem 1rem; border-radius: 8px; background: rgba(99,102,241,0.2); border: 1px solid var(--primary); color: white; cursor: pointer;">
                    OPEN
                </button>
            </td>
        `;
        resultsTableBody.appendChild(tr);
    });
}

function updateProgress(current, total, file) {
    const percent = Math.round((current / total) * 100);
    progressBar.style.width = `${percent}%`;
    percentText.textContent = `${percent}%`;
    progressText.textContent = `Analyzing: ${file} (${current}/${total})`;
}

function startLoading() {
    uploadModule.style.display = 'none';
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    percentText.textContent = '0%';
    progressText.textContent = 'Initializing Engine...';
    resultsSection.style.display = 'none';
    analyzeBtn.disabled = true;
}

function stopLoading() {
    // Hide progress bar after completion
    setTimeout(() => {
        progressContainer.style.display = 'none';
    }, 1000);
    analyzeBtn.disabled = false;
}
