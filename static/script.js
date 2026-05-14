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

const navAnalyzerBtn = document.getElementById('navAnalyzerBtn');
const navDashboardBtn = document.getElementById('navDashboardBtn');
const dashboardSection = document.getElementById('dashboardSection');

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

// Dashboard Logic
let skillsChartInstance = null;
let expChartInstance = null;
let locChartInstance = null;
let rawCandidates = [];
let activeFilters = { skills: new Set(), experience: new Set(), location: new Set() };

navAnalyzerBtn.addEventListener('click', () => {
    navAnalyzerBtn.style.background = 'rgba(99,102,241,0.2)';
    navAnalyzerBtn.style.borderColor = 'var(--primary)';
    navDashboardBtn.style.background = 'rgba(255,255,255,0.05)';
    navDashboardBtn.style.borderColor = 'rgba(255,255,255,0.1)';
    
    dashboardSection.style.display = 'none';
    uploadModule.style.display = 'flex';
    resultsSection.style.display = 'none';
});

navDashboardBtn.addEventListener('click', async () => {
    navDashboardBtn.style.background = 'rgba(99,102,241,0.2)';
    navDashboardBtn.style.borderColor = 'var(--primary)';
    navAnalyzerBtn.style.background = 'rgba(255,255,255,0.05)';
    navAnalyzerBtn.style.borderColor = 'rgba(255,255,255,0.1)';
    
    uploadModule.style.display = 'none';
    resultsSection.style.display = 'none';
    progressContainer.style.display = 'none';
    dashboardSection.style.display = 'block';
    
    await loadDashboardData();
});

async function loadDashboardData() {
    try {
        const response = await fetch(`${BASE_URL}/api/dashboard`);
        const data = await response.json();
        
        if (data.success) {
            rawCandidates = data.candidates;
            setupFilters();
            applyFilters();
        } else {
            alert(data.error);
            navAnalyzerBtn.click(); // Revert back if no data
        }
    } catch (err) {
        console.error(err);
        alert('Failed to load dashboard data.');
        navAnalyzerBtn.click();
    }
}

// Slicer UI Interactions
document.querySelectorAll('.select-selected').forEach(btn => {
    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        const list = this.nextElementSibling;
        const isHidden = list.classList.contains('select-hide');
        document.querySelectorAll('.select-items').forEach(el => el.classList.add('select-hide'));
        if (isHidden) list.classList.remove('select-hide');
    });
});
document.addEventListener('click', () => {
    document.querySelectorAll('.select-items').forEach(el => el.classList.add('select-hide'));
});
document.querySelectorAll('.select-items').forEach(list => {
    list.addEventListener('click', e => e.stopPropagation());
});

document.getElementById('clearFiltersBtn').addEventListener('click', () => {
    activeFilters.skills.clear();
    activeFilters.experience.clear();
    activeFilters.location.clear();
    document.querySelectorAll('.select-items input').forEach(cb => cb.checked = false);
    applyFilters();
});

function setupFilters() {
    const allSkills = new Set();
    const allExp = new Set();
    const allLoc = new Set();
    
    rawCandidates.forEach(c => {
        c.skills.forEach(s => allSkills.add(s));
        allExp.add(c.experience);
        allLoc.add(c.location);
    });
    
    populateDropdown('skillsList', Array.from(allSkills).sort(), 'skills');
    populateDropdown('expList', Array.from(allExp).sort(), 'experience');
    populateDropdown('locList', Array.from(allLoc).sort(), 'location');
}

function populateDropdown(containerId, items, filterType) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    items.forEach(item => {
        const div = document.createElement('div');
        div.innerHTML = `<input type="checkbox" value="${item}"> <span>${item}</span>`;
        const cb = div.querySelector('input');
        div.addEventListener('click', (e) => {
            if (e.target !== cb) cb.checked = !cb.checked;
            if (cb.checked) activeFilters[filterType].add(item);
            else activeFilters[filterType].delete(item);
            applyFilters();
        });
        container.appendChild(div);
    });
}

function applyFilters() {
    let filtered = rawCandidates;
    
    // Slicer OR logic for Skills (candidate has ANY of selected skills)
    if (activeFilters.skills.size > 0) {
        filtered = filtered.filter(c => c.skills.some(s => activeFilters.skills.has(s)));
    }
    // Slicer OR logic for Experience (candidate has ANY of selected experience levels)
    if (activeFilters.experience.size > 0) {
        filtered = filtered.filter(c => activeFilters.experience.has(c.experience));
    }
    // Slicer OR logic for Location
    if (activeFilters.location.size > 0) {
        filtered = filtered.filter(c => activeFilters.location.has(c.location));
    }
    
    // Re-Aggregate
    const skillsCount = {};
    const expCount = {};
    const locCount = {};
    
    filtered.forEach(c => {
        c.skills.forEach(s => skillsCount[s] = (skillsCount[s] || 0) + 1);
        expCount[c.experience] = (expCount[c.experience] || 0) + 1;
        locCount[c.location] = (locCount[c.location] || 0) + 1;
    });
    
    const sortedSkills = Object.entries(skillsCount).sort((a,b) => b[1] - a[1]).slice(0,10);
    const sortedLoc = Object.entries(locCount).sort((a,b) => b[1] - a[1]).slice(0,5);
    
    const aggregated = {
        skills: { labels: sortedSkills.map(i=>i[0]), data: sortedSkills.map(i=>i[1]) },
        experience: { labels: Object.keys(expCount), data: Object.values(expCount) },
        locations: { labels: sortedLoc.map(i=>i[0]), data: sortedLoc.map(i=>i[1]) }
    };
    
    renderCharts(aggregated);
}

function renderCharts(data) {
    const primaryColor = '#6366f1';
    const accentColor = '#10b981';
    const textMuted = '#94a3b8';
    
    // Skills Chart
    const skillsCtx = document.getElementById('skillsChart').getContext('2d');
    if (skillsChartInstance) skillsChartInstance.destroy();
    skillsChartInstance = new Chart(skillsCtx, {
        type: 'bar',
        data: {
            labels: data.skills.labels,
            datasets: [{
                label: 'Candidate Count',
                data: data.skills.data,
                backgroundColor: primaryColor,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: textMuted } },
                x: { grid: { display: false }, ticks: { color: textMuted } }
            },
            plugins: { legend: { display: false } },
            animation: { duration: 400 }
        }
    });

    // Experience Chart
    const expCtx = document.getElementById('expChart').getContext('2d');
    if (expChartInstance) expChartInstance.destroy();
    expChartInstance = new Chart(expCtx, {
        type: 'doughnut',
        data: {
            labels: data.experience.labels,
            datasets: [{
                data: data.experience.data,
                backgroundColor: [primaryColor, accentColor, '#8b5cf6'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right', labels: { color: textMuted } } },
            animation: { duration: 400 }
        }
    });

    // Location Chart
    const locCtx = document.getElementById('locChart').getContext('2d');
    if (locChartInstance) locChartInstance.destroy();
    locChartInstance = new Chart(locCtx, {
        type: 'bar',
        data: {
            labels: data.locations.labels,
            datasets: [{
                label: 'Candidate Count',
                data: data.locations.data,
                backgroundColor: accentColor,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: textMuted } },
                y: { grid: { display: false }, ticks: { color: textMuted } }
            },
            plugins: { legend: { display: false } },
            animation: { duration: 400 }
        }
    });
}

