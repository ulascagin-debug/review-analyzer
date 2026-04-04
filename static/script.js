// ============================================
// REVIEW ANALYZER — DASHBOARD SPA
// Router, Charts, Business Setup, Analysis, Plans, Presentation
// ============================================

// ===== STATE =====
let currentView = 'setup';
let activeBusiness = null;
let setupBusinesses = [];
let analysisBusinesses = [];
let selectedSetupUrl = null;
let selectedAnalysisUrl = null;
let dashboardData = null;
let analysisResult = null;
let presentationSlides = [];
let currentSlide = 0;
// oppToast vars moved to toast v2 section below

// Chart instances
let chartSentimentTrend = null;
let chartKeywords = null;
let chartRatingDist = null;

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', async () => {
    // Check for saved business
    try {
        const res = await fetch('/api/business');
        const data = await res.json();
        if (data.business) {
            activeBusiness = data.business;
            showBusinessBadge();
            navigateTo('dashboard');
            loadDashboard();
        } else {
            navigateTo('setup');
        }
    } catch {
        navigateTo('setup');
    }

    // Setup hash routing
    window.addEventListener('hashchange', handleHash);
    if (window.location.hash) handleHash();

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboard);
});

// ===== ROUTING =====
function handleHash() {
    const hash = window.location.hash.replace('#', '') || 'dashboard';
    if (!activeBusiness && hash !== 'setup') {
        navigateTo('setup');
        return;
    }
    navigateTo(hash, false);
}

function navigateTo(view, updateHash = true) {
    // Hide all views
    document.querySelectorAll('.view').forEach(v => v.style.display = 'none');

    // Show target
    const target = document.getElementById(`view-${view}`);
    if (target) {
        target.style.display = 'block';
        target.style.animation = 'none';
        target.offsetHeight; // force reflow
        target.style.animation = 'fadeIn 0.3s ease';
    }

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navItem = document.getElementById(`nav-${view}`);
    if (navItem) navItem.classList.add('active');

    currentView = view;
    if (updateHash) window.location.hash = view;

    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');

    // Load view-specific data
    if (view === 'dashboard' && activeBusiness) loadDashboard();
    if (view === 'plans' && activeBusiness) loadPlans();
    if (view === 'history' && activeBusiness) loadHistory();
    if (view === 'analysis' && activeBusiness) prefillAnalysisForm();
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

// ===== BUSINESS BADGE =====
function showBusinessBadge() {
    if (!activeBusiness) return;
    document.getElementById('business-badge').style.display = 'flex';
    document.getElementById('badge-business-name').textContent = activeBusiness.name;
    document.getElementById('btn-change-business').style.display = 'block';
}

function hideBadge() {
    document.getElementById('business-badge').style.display = 'none';
    document.getElementById('btn-change-business').style.display = 'none';
}

async function changeBusiness() {
    if (!confirm('İşletmeyi değiştirmek istediğinize emin misiniz?')) return;
    try {
        await fetch('/api/business/change', { method: 'POST' });
    } catch {}
    activeBusiness = null;
    hideBadge();
    stopOppToast();
    navigateTo('setup');
}

// ===== CATEGORY CHIPS =====
function toggleChip(btn) {
    btn.classList.toggle('active');
    // Clear error state
    const container = btn.closest('.category-chips');
    if (container) container.classList.remove('category-chips-error');
}

function getSelectedCategories(containerId) {
    const chips = document.querySelectorAll(`#${containerId} .cat-chip.active`);
    return Array.from(chips).map(c => c.dataset.cat);
}

function getCategoryString(containerId) {
    const cats = getSelectedCategories(containerId);
    return cats.join(' ');
}

// ===== SETUP FLOW =====
let searchTimer = null;

async function searchBusinessesSetup() {
    const categories = getSelectedCategories('setup-category-chips');
    const country = document.getElementById('setup-country').value.trim();
    const city = document.getElementById('setup-city').value.trim();
    const district = document.getElementById('setup-district').value.trim();

    if (categories.length === 0) {
        const chipsEl = document.getElementById('setup-category-chips');
        chipsEl.classList.add('category-chips-error');
        setTimeout(() => chipsEl.classList.remove('category-chips-error'), 1000);
        return;
    }
    if (!city) { shake('setup-city'); return; }

    const category = categories.join(' ');
    const btn = document.getElementById('btn-search-businesses');
    btn.disabled = true;
    document.getElementById('search-btn-text').style.display = 'none';
    document.getElementById('search-btn-spinner').style.display = 'flex';

    // Start elapsed timer
    let elapsed = 0;
    const elapsedEl = document.getElementById('search-elapsed');
    elapsedEl.textContent = 'Aranıyor... 0s';
    searchTimer = setInterval(() => {
        elapsed++;
        elapsedEl.textContent = `Aranıyor... ${elapsed}s`;
        if (elapsed === 10) elapsedEl.textContent = `Google Maps taranıyor... ${elapsed}s`;
        if (elapsed === 30) elapsedEl.textContent = `Hâlâ aranıyor... ${elapsed}s`;
        if (elapsed === 60) elapsedEl.textContent = `Biraz daha bekle... ${elapsed}s`;
    }, 1000);

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 min timeout

        const res = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, country, city, district }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        const data = await res.json();

        if (data.error) {
            alert('❌ Hata: ' + data.error);
        } else {
            setupBusinesses = data.businesses || [];
            if (setupBusinesses.length === 0) {
                alert('Bu bölgede işletme bulunamadı. Farklı bir yer veya kategori deneyin.');
            } else {
                renderBusinessList('setup-business-list', setupBusinesses, 'setup');
                document.getElementById('setup-step-1').style.display = 'none';
                document.getElementById('setup-step-2').style.display = 'block';
            }
        }
    } catch (e) {
        if (e.name === 'AbortError') {
            alert('⏱ Arama zaman aşımına uğradı (2 dakika). Lütfen daha küçük bir bölge veya farklı bir kategori deneyin.');
        } else {
            alert('❌ Bağlantı hatası: ' + (e.message || 'Sunucuya ulaşılamadı.'));
            console.error('Search error:', e);
        }
    }

    // Cleanup timer
    if (searchTimer) { clearInterval(searchTimer); searchTimer = null; }
    btn.disabled = false;
    document.getElementById('search-btn-text').style.display = 'flex';
    document.getElementById('search-btn-spinner').style.display = 'none';
}

function backToStep1() {
    document.getElementById('setup-step-2').style.display = 'none';
    document.getElementById('setup-step-1').style.display = 'block';
    selectedSetupUrl = null;
}

function showManualEntry() {
    document.getElementById('setup-step-1').style.display = 'none';
    document.getElementById('setup-manual').style.display = 'block';
}

function backToStep1FromManual() {
    document.getElementById('setup-manual').style.display = 'none';
    document.getElementById('setup-step-1').style.display = 'block';
}

async function completeSetup() {
    if (!selectedSetupUrl) return;
    const category = getCategoryString('setup-category-chips');
    const country = document.getElementById('setup-country').value.trim();
    const city = document.getElementById('setup-city').value.trim();
    const district = document.getElementById('setup-district').value.trim();

    const biz = setupBusinesses.find(b => b.url === selectedSetupUrl);
    if (!biz) return;

    try {
        const res = await fetch('/api/business/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: biz.name,
                category,
                country,
                city,
                district,
                maps_url: biz.url,
            })
        });
        const data = await res.json();

        if (data.business_id) {
            activeBusiness = {
                id: data.business_id,
                name: biz.name,
                category, country, city, district,
                maps_url: biz.url,
            };
            showBusinessBadge();
            navigateTo('dashboard');
        }
    } catch {
        alert('Kayıt hatası.');
    }
}

async function completeManualSetup() {
    const name = document.getElementById('manual-name').value.trim();
    const category = getCategoryString('setup-category-chips');
    const country = document.getElementById('setup-country').value.trim();
    const city = document.getElementById('setup-city').value.trim();
    const district = document.getElementById('setup-district').value.trim();

    if (!name) { shake('manual-name'); return; }
    if (!category) { alert('İş kolu seçiniz.'); return; }
    if (!city) { alert('Şehir giriniz.'); return; }

    try {
        const res = await fetch('/api/business/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, category, country, city, district })
        });
        const data = await res.json();

        if (data.business_id) {
            activeBusiness = { id: data.business_id, name, category, country, city, district };
            showBusinessBadge();
            navigateTo('dashboard');
        }
    } catch {
        alert('Kayıt hatası.');
    }
}

// ===== BUSINESS LIST RENDERER =====
function renderBusinessList(containerId, businesses, mode) {
    const listEl = document.getElementById(containerId);
    listEl.innerHTML = '';

    businesses.forEach((biz, index) => {
        const item = document.createElement('div');
        item.className = 'business-item';
        item.onclick = () => selectBusiness(biz.url, index, mode);
        item.id = `${mode}-biz-${index}`;

        const info = document.createElement('div');
        info.className = 'business-item-info';
        info.innerHTML = `<strong>${biz.name}</strong>`;

        const radio = document.createElement('div');
        radio.className = 'business-item-radio';

        item.appendChild(info);
        item.appendChild(radio);
        listEl.appendChild(item);
    });
}

function selectBusiness(url, index, mode) {
    const container = mode === 'setup' ? 'setup-business-list' : 'analysis-business-list';
    document.querySelectorAll(`#${container} .business-item`).forEach(el => el.classList.remove('selected'));
    document.getElementById(`${mode}-biz-${index}`).classList.add('selected');

    if (mode === 'setup') {
        selectedSetupUrl = url;
        document.getElementById('btn-complete-setup').disabled = false;
    } else {
        selectedAnalysisUrl = url;
        document.getElementById('btn-run-analysis').disabled = false;
    }
}

// ===== DASHBOARD =====
async function loadDashboard() {
    if (!activeBusiness) return;

    document.getElementById('dashboard-title').textContent = activeBusiness.name || 'Dashboard';
    document.getElementById('dashboard-subtitle').textContent =
        `${activeBusiness.category || ''} · ${activeBusiness.district || ''} ${activeBusiness.city || ''}`.trim();

    try {
        const res = await fetch('/api/dashboard');
        const data = await res.json();

        if (data.error) {
            document.getElementById('dashboard-empty').style.display = 'block';
            document.getElementById('stats-grid').style.display = 'none';
            return;
        }

        dashboardData = data;
        const stats = data.stats || {};

        // Update stat cards
        document.getElementById('stat-total-reviews').textContent = stats.total_reviews || 0;
        document.getElementById('stat-avg-rating').textContent = stats.avg_rating || '—';
        const posRate = stats.sentiment ?
            Math.round((stats.sentiment.positive / Math.max(stats.total_reviews, 1)) * 100) : 0;
        document.getElementById('stat-sentiment').textContent = posRate + '%';
        document.getElementById('stat-recent').textContent = stats.recent_reviews || 0;

        if (stats.total_reviews > 0) {
            document.getElementById('stats-grid').style.display = 'grid';
            document.getElementById('dashboard-empty').style.display = 'none';
            renderCharts(stats);
            renderOpportunities(data.opportunities || []);

            // Start bad review pop-ups
            if (data.bad_competitor_reviews && data.bad_competitor_reviews.length > 0) {
                startOppToast(data.bad_competitor_reviews);
            }
        } else {
            document.getElementById('dashboard-empty').style.display = 'block';
            document.getElementById('stats-grid').style.display = 'none';
        }

    } catch {
        document.getElementById('dashboard-empty').style.display = 'block';
        document.getElementById('stats-grid').style.display = 'none';
    }
}

// ===== CHARTS =====
function renderCharts(stats) {
    renderSentimentTrend(stats.daily_trend || []);
    renderKeywordsChart(stats.top_keywords || []);
    renderRatingDistChart(stats.sentiment || {});
}

function renderSentimentTrend(dailyTrend) {
    const ctx = document.getElementById('chart-sentiment-trend');
    if (!ctx) return;

    if (chartSentimentTrend) chartSentimentTrend.destroy();

    const labels = dailyTrend.map(d => d.day ? d.day.substring(5) : '');
    const posData = dailyTrend.map(d => d.pos || 0);
    const negData = dailyTrend.map(d => d.neg || 0);

    chartSentimentTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Pozitif',
                    data: posData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                },
                {
                    label: 'Negatif',
                    data: negData,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#9ca3af', font: { size: 11 } } },
            },
            scales: {
                x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true },
            }
        }
    });
}

function renderKeywordsChart(topKeywords) {
    const ctx = document.getElementById('chart-keywords');
    if (!ctx) return;

    if (chartKeywords) chartKeywords.destroy();

    const labels = topKeywords.map(k => k[0]);
    const values = topKeywords.map(k => k[1]);

    const colors = labels.map((_, i) => {
        const palette = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444',
                         '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
                         '#84cc16', '#0ea5e9', '#a855f7', '#22c55e', '#e11d48'];
        return palette[i % palette.length];
    });

    chartKeywords = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors.map(c => c + '33'),
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true },
                y: { ticks: { color: '#9ca3af', font: { size: 11 } }, grid: { display: false } },
            }
        }
    });
}

function renderRatingDistChart(sentiment) {
    const ctx = document.getElementById('chart-rating-dist');
    if (!ctx) return;

    if (chartRatingDist) chartRatingDist.destroy();

    chartRatingDist = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Pozitif', 'Negatif', 'Nötr'],
            datasets: [{
                data: [sentiment.positive || 0, sentiment.negative || 0, sentiment.neutral || 0],
                backgroundColor: ['rgba(16, 185, 129, 0.7)', 'rgba(239, 68, 68, 0.7)', 'rgba(107, 114, 128, 0.7)'],
                borderColor: ['#10b981', '#ef4444', '#6b7280'],
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#9ca3af', font: { size: 11 }, padding: 16 }
                }
            }
        }
    });
}

function renderOpportunities(opportunities) {
    const list = document.getElementById('opportunities-list');
    if (!opportunities.length) {
        list.innerHTML = '<p class="empty-state" style="padding:20px;">Henüz fırsat verisi yok.</p>';
        return;
    }

    list.innerHTML = opportunities.map(opp => `
        <div class="opp-item">
            <span class="opp-keyword">${opp.keyword}</span>
            <span class="opp-count">${opp.count}x</span>
            <span class="opp-example">${(opp.examples && opp.examples[0]) || ''}</span>
        </div>
    `).join('');
}

// ===== ANALYSIS FLOW =====
function prefillAnalysisForm() {
    if (!activeBusiness) return;
    // Select matching category chips
    if (activeBusiness.category) {
        const cats = activeBusiness.category.split(' ');
        document.querySelectorAll('#analysis-category-chips .cat-chip').forEach(chip => {
            if (cats.includes(chip.dataset.cat)) chip.classList.add('active');
            else chip.classList.remove('active');
        });
    }
    document.getElementById('analysis-country').value = activeBusiness.country || '';
    document.getElementById('analysis-city').value = activeBusiness.city || '';
    document.getElementById('analysis-district').value = activeBusiness.district || '';
}

function toggleManualMode() {
    const manual = document.getElementById('manual-section');
    const checked = document.getElementById('manual-toggle').checked;
    manual.style.display = checked ? 'block' : 'none';
}

async function findBusinessesAnalysis() {
    const categories = getSelectedCategories('analysis-category-chips');
    const country = document.getElementById('analysis-country').value.trim();
    const city = document.getElementById('analysis-city').value.trim();
    const district = document.getElementById('analysis-district').value.trim();
    const isManual = document.getElementById('manual-toggle').checked;
    const reviews = isManual ? document.getElementById('analysis-reviews').value.trim() : '';

    if (categories.length === 0) {
        const chipsEl = document.getElementById('analysis-category-chips');
        chipsEl.classList.add('category-chips-error');
        setTimeout(() => chipsEl.classList.remove('category-chips-error'), 1000);
        return;
    }
    if (!city) { shake('analysis-city'); return; }
    const category = categories.join(' ');

    if (isManual) {
        if (!reviews) { shake('analysis-reviews'); return; }
        runAnalysis(true);
        return;
    }

    const btn = document.getElementById('btn-find');
    btn.disabled = true;
    document.getElementById('find-btn-text').style.display = 'none';
    document.getElementById('find-btn-spinner').style.display = 'flex';

    try {
        const res = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, country, city, district })
        });
        const data = await res.json();

        if (data.error) {
            showAnalysisError(data.error);
        } else {
            analysisBusinesses = data.businesses || [];
            selectedAnalysisUrl = null;
            renderBusinessList('analysis-business-list', analysisBusinesses, 'analysis');
            document.getElementById('analysis-form').style.display = 'none';
            document.getElementById('analysis-selection').style.display = 'block';
        }
    } catch {
        showAnalysisError('Bağlantı hatası.');
    }

    btn.disabled = false;
    document.getElementById('find-btn-text').style.display = 'flex';
    document.getElementById('find-btn-spinner').style.display = 'none';
}

async function runAnalysis(isManual = false) {
    const category = getCategoryString('analysis-category-chips');
    const country = document.getElementById('analysis-country').value.trim();
    const city = document.getElementById('analysis-city').value.trim();
    const district = document.getElementById('analysis-district').value.trim();
    const reviews = isManual ? document.getElementById('analysis-reviews').value.trim() : '';

    // Show loading
    document.getElementById('analysis-form').style.display = 'none';
    document.getElementById('analysis-selection').style.display = 'none';
    document.getElementById('analysis-results').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'none';
    document.getElementById('analysis-loading').style.display = 'block';

    startLoadingAnimation();

    const competitorUrls = analysisBusinesses.map(b => b.url);
    const body = {
        category, country, city, district, reviews,
        target_business_url: selectedAnalysisUrl,
        competitor_urls: competitorUrls,
    };
    if (activeBusiness) body.business_id = activeBusiness.id;

    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        stopLoadingAnimation();
        document.getElementById('analysis-loading').style.display = 'none';

        if (data.error) {
            showAnalysisError(data.error);
        } else {
            analysisResult = data;
            showAnalysisResults(data);

            // Start bad review toasts
            const badRevs = (data.stats && data.stats.competitor_bad_reviews) || [];
            if (badRevs.length > 0) startOppToast(badRevs);
        }
    } catch {
        stopLoadingAnimation();
        document.getElementById('analysis-loading').style.display = 'none';
        showAnalysisError('Bağlantı hatası. Lütfen tekrar deneyin.');
    }
}

function showAnalysisResults(data) {
    const stats = data.stats || {};

    let statsHtml = '';
    if (stats.mode !== 'manual') {
        statsHtml = `
            <div class="stat">🏪 ${stats.businesses_analyzed || '—'} işletme</div>
            <div class="stat">⭐ ${stats.total_reviews || 0} yorum</div>
            <div class="stat">📊 Ort: ${stats.avg_rating || '—'}/5</div>
        `;
    } else {
        statsHtml = `<div class="stat">📋 ${stats.total_reviews} yorum (elle giriş)</div>`;
    }
    document.getElementById('analysis-stats-bar').innerHTML = statsHtml;

    // Build structured HTML from JSON data
    let html = '';

    // --- Growth Potential ---
    const gp = data.growth_potential;
    if (gp) {
        const scoreColor = gp.score >= 70 ? '#10b981' : gp.score >= 40 ? '#f59e0b' : '#ef4444';
        let breakdownHtml = '';
        if (gp.breakdown) {
            const factorIcons = { quality: '⭐', volume: '📊', trend: '📈', advantage: '⚔️', gap: '🎯' };
            breakdownHtml = `<div class="growth-breakdown">
                ${Object.entries(gp.breakdown).map(([key, f]) => {
                    const pct = Math.round((f.score / f.max) * 100);
                    const barColor = pct >= 70 ? '#10b981' : pct >= 40 ? '#f59e0b' : '#ef4444';
                    return `<div class="growth-factor">
                        <div class="factor-header">
                            <span>${factorIcons[key] || '📌'} ${f.label}</span>
                            <span class="factor-score">${f.score}/${f.max}</span>
                        </div>
                        <div class="factor-bar"><div class="factor-fill" style="width:${pct}%;background:${barColor}"></div></div>
                    </div>`;
                }).join('')}
            </div>`;
        }
        html += `
        <div class="result-card growth-card">
            <div class="result-card-header"><span>🚀 Büyüme Potansiyeli</span></div>
            <div style="display:flex;align-items:center;gap:24px;margin:16px 0;">
                <div class="growth-score" style="border-color:${scoreColor}">
                    <span class="growth-number" style="color:${scoreColor}">${gp.score}</span>
                    <span class="growth-label">/100</span>
                </div>
                <div style="flex:1;">
                    <p style="font-size:0.9rem;line-height:1.6;color:var(--text-secondary);margin-bottom:12px;">${gp.summary}</p>
                    ${breakdownHtml}
                </div>
            </div>
        </div>`;
    }

    // --- Comparison Matrix (data-driven) ---
    const matrix = data.comparison_matrix;
    if (matrix && matrix.businesses && Object.keys(matrix.businesses).length > 0) {
        const cats = matrix.categories || [];
        const bizNames = Object.keys(matrix.businesses);

        let tableRows = '';
        for (const cat of cats) {
            let cells = '';
            for (const biz of bizNames) {
                const d = matrix.businesses[biz][cat];
                if (!d || d.score === null) {
                    cells += `<td class="matrix-cell"><span class="matrix-na">—</span></td>`;
                } else {
                    const color = d.score >= 3.5 ? '#10b981' : d.score >= 2.5 ? '#f59e0b' : '#ef4444';
                    const label = d.negative > d.positive ? `${d.negative}/${d.mentioned} olumsuz` 
                                : d.positive > d.negative ? `${d.positive}/${d.mentioned} olumlu`
                                : `${d.mentioned} karma`;
                    cells += `<td class="matrix-cell">
                        <span class="matrix-score" style="color:${color}">${d.score}/5</span>
                        <span class="matrix-detail">(${label})</span>
                    </td>`;
                }
            }
            tableRows += `<tr><td class="matrix-cat">${cat}</td>${cells}</tr>`;
        }

        html += `
        <div class="result-card">
            <div class="result-card-header"><span>⚔️ Rekabet Karşılaştırma Matrisi</span><span class="badge">Veri tabanlı</span></div>
            <div class="matrix-scroll">
                <table class="comparison-matrix">
                    <thead>
                        <tr>
                            <th>Kategori</th>
                            ${bizNames.map(n => `<th title="${n}">${n.length > 18 ? n.substring(0, 16) + '…' : n}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>
        </div>`;
    }

    // --- AI Qualitative Comparison ---
    const comp = data.comparison;
    if (comp) {
        html += `
        <div class="result-card">
            <div class="result-card-header"><span>📊 Stratejik Değerlendirme</span></div>
            <div class="comparison-grid">
                <div class="comp-col comp-strong">
                    <h4>💪 Güçlü Olduğunuz Alanlar</h4>
                    <ul>${(comp.stronger_areas||[]).map(a => `<li><span class="comp-dot green"></span>${a}</li>`).join('')}</ul>
                </div>
                <div class="comp-col comp-weak">
                    <h4>⚠️ Geliştirilmesi Gerekenler</h4>
                    <ul>${(comp.weaker_areas||[]).map(a => `<li><span class="comp-dot red"></span>${a}</li>`).join('')}</ul>
                </div>
                <div class="comp-col comp-equal">
                    <h4>🤝 Eşit Olduğunuz Alanlar</h4>
                    <ul>${(comp.equal_areas||[]).map(a => `<li><span class="comp-dot gray"></span>${a}</li>`).join('')}</ul>
                </div>
            </div>
        </div>`;
    }

    // --- Competitors ---
    const competitors = data.competitors || [];
    if (competitors.length > 0) {
        html += `
        <div class="result-card">
            <div class="result-card-header"><span>🏪 Rakip Profilleri</span><span class="badge">${competitors.length} rakip</span></div>
            <div class="competitors-grid">
                ${competitors.map((c, i) => {
                    const ratingColor = c.rating >= 4.5 ? '#10b981' : c.rating >= 3.5 ? '#f59e0b' : '#ef4444';
                    return `
                    <div class="competitor-card">
                        <div class="comp-header">
                            <span class="comp-name">${c.name}</span>
                            <span class="comp-rating" style="color:${ratingColor}">⭐ ${c.rating}</span>
                        </div>
                        <span class="comp-reviews">${c.total_reviews} yorum</span>
                        ${c.strengths && c.strengths.length ? `
                        <div class="comp-tags">
                            <span class="tag-label">💪</span>
                            ${c.strengths.map(s => `<span class="tag green">${s}</span>`).join('')}
                        </div>` : ''}
                        ${c.weaknesses && c.weaknesses.length ? `
                        <div class="comp-tags">
                            <span class="tag-label">⚠️</span>
                            ${c.weaknesses.map(w => `<span class="tag red">${w}</span>`).join('')}
                        </div>` : ''}
                    </div>`;
                }).join('')}
            </div>
        </div>`;
    }

    // --- Recommendations ---
    const recs = data.recommendations;
    if (recs) {
        html += `
        <div class="result-card">
            <div class="result-card-header"><span>📋 Aksiyon Planı</span></div>
            <div class="recs-grid">
                <div class="rec-col">
                    <div class="rec-period"><span class="rec-icon">⚡</span>Bu Hafta</div>
                    <ul>${(recs.weekly||[]).map(r => `<li>${r}</li>`).join('')}</ul>
                </div>
                <div class="rec-col">
                    <div class="rec-period"><span class="rec-icon">📅</span>Bu Ay</div>
                    <ul>${(recs.monthly||[]).map(r => `<li>${r}</li>`).join('')}</ul>
                </div>
                <div class="rec-col">
                    <div class="rec-period"><span class="rec-icon">🎯</span>Bu Yıl</div>
                    <ul>${(recs.yearly||[]).map(r => `<li>${r}</li>`).join('')}</ul>
                </div>
            </div>
        </div>`;
    }

    // --- Marketing Messages (if available) ---
    const marketing = data.marketing_messages;
    if (marketing) {
        html += `
        <div class="result-card">
            <div class="result-card-header"><span>📢 Pazarlama Mesajları</span></div>
            <div class="marketing-grid">
                ${(marketing.ad_copies||[]).map((ad, i) => `
                <div class="marketing-item ad-copy">
                    <span class="marketing-label">Reklam Metni ${i+1}</span>
                    <p>${ad}</p>
                </div>`).join('')}
                ${(marketing.social_posts||[]).map((post, i) => `
                <div class="marketing-item social-post">
                    <span class="marketing-label">Sosyal Medya ${i+1}</span>
                    <p>${post}</p>
                </div>`).join('')}
            </div>
        </div>`;
    }

    document.getElementById('analysis-results-box').innerHTML = html;
    document.getElementById('analysis-results').style.display = 'block';
    document.getElementById('analysis-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showAnalysisError(msg) {
    document.getElementById('analysis-error-msg').textContent = msg;
    document.getElementById('analysis-error').style.display = 'block';
}

function resetAnalysisForm() {
    document.getElementById('analysis-selection').style.display = 'none';
    document.getElementById('analysis-form').style.display = 'block';
    selectedAnalysisUrl = null;
}

function resetAnalysisView() {
    document.getElementById('analysis-results').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'none';
    document.getElementById('analysis-form').style.display = 'block';
    document.getElementById('analysis-selection').style.display = 'none';
    analysisBusinesses = [];
    selectedAnalysisUrl = null;
    stopOppToast();
}

// ===== LOADING ANIMATION =====
let loadingTimer = null;

function startLoadingAnimation() {
    const steps = ['ls-1', 'ls-2', 'ls-3', 'ls-4'];
    let idx = 0;

    steps.forEach(id => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'done');
    });
    document.getElementById(steps[0]).classList.add('active');

    loadingTimer = setInterval(() => {
        if (idx > 0) {
            const prev = document.getElementById(steps[idx - 1]);
            prev.classList.remove('active');
            prev.classList.add('done');
            prev.textContent = '✅ ' + prev.textContent.replace(/^[^\s]+\s/, '');
        }
        idx++;
        if (idx < steps.length) {
            document.getElementById(steps[idx]).classList.add('active');
        } else {
            clearInterval(loadingTimer);
        }
    }, 3000);
}

function stopLoadingAnimation() {
    if (loadingTimer) { clearInterval(loadingTimer); loadingTimer = null; }
}

// ===== PLANS VIEW =====
async function loadPlans() {
    if (!activeBusiness) return;

    try {
        const res = await fetch('/api/analysis/latest');
        const data = await res.json();

        if (data.analysis && data.analysis.result_md) {
            const md = data.analysis.result_md;
            parsePlans(md);
        }
    } catch {}
}

const PLAN_SECTIONS = {
    '1w': { title: '1 HAFTALIK', keywords: ['1 HAFTALIK', '1 Haftalık', 'Acil Müdahale'] },
    '1m': { title: '1 AYLIK', keywords: ['1 AYLIK', '1 Aylık', 'Kısa Vadeli'] },
    '3m': { title: '3 AYLIK', keywords: ['3 AYLIK', '3 Aylık', 'Orta Vadeli'] },
    '6m': { title: '6 AYLIK', keywords: ['6 AYLIK', '6 Aylık', 'Büyüme Yol Haritası'] },
    '1y': { title: '1 YILLIK', keywords: ['1 YILLIK', '1 Yıllık', 'Vizyon Planı'] },
};

let parsedPlans = {};

function parsePlans(md) {
    // Split by ### headers for timeframe sections
    const sections = md.split(/(?=###\s)/);
    parsedPlans = {};

    for (const [key, config] of Object.entries(PLAN_SECTIONS)) {
        for (const section of sections) {
            if (config.keywords.some(kw => section.includes(kw))) {
                parsedPlans[key] = section.trim();
                break;
            }
        }
        if (!parsedPlans[key]) {
            parsedPlans[key] = `### ${config.title}\n\nBu zaman dilimi için henüz plan oluşturulmadı. Yeni analiz çalıştırın.`;
        }
    }

    // Also build presentation slides
    presentationSlides = Object.values(parsedPlans);

    // Show first plan
    switchPlan('1w');
}

function switchPlan(key) {
    document.querySelectorAll('.plan-tab').forEach(t => t.classList.remove('active'));
    const tab = document.querySelector(`.plan-tab[data-plan="${key}"]`);
    if (tab) tab.classList.add('active');

    const content = document.getElementById('plan-content');
    if (parsedPlans[key]) {
        content.innerHTML = markdownToHtml(parsedPlans[key]);
    } else {
        content.innerHTML = '<div class="empty-state"><h3>Veri yok</h3><p>Önce analiz çalıştırın.</p></div>';
    }
}

// ===== HISTORY VIEW =====
async function loadHistory() {
    if (!activeBusiness) return;

    try {
        const res = await fetch('/api/analysis/history');
        const data = await res.json();
        const list = document.getElementById('history-list');

        if (!data.history || data.history.length === 0) {
            list.innerHTML = '<div class="empty-state"><div class="empty-icon">📁</div><h3>Henüz analiz yapılmadı</h3></div>';
            return;
        }

        list.innerHTML = data.history.map(h => {
            const date = new Date(h.created_at).toLocaleString('tr-TR');
            return `
                <div class="history-item" onclick="loadHistoryItem(${h.id})">
                    <div class="history-info">
                        <span class="history-date">${date}</span>
                        <span class="history-type">${h.analysis_type || 'Full Analysis'}</span>
                    </div>
                    <span class="history-arrow">→</span>
                </div>
            `;
        }).join('');
    } catch {}
}

async function loadHistoryItem(id) {
    // For now, navigate to plans which loads latest
    navigateTo('plans');
}

// ===== PRESENTATION MODE =====
function enterPresentation() {
    // Build slides from analysis result
    if (analysisResult && analysisResult.result) {
        buildPresSlides(analysisResult.result);
    } else if (Object.keys(parsedPlans).length > 0) {
        presentationSlides = Object.values(parsedPlans);
    } else {
        alert('Önce bir analiz çalıştırın.');
        return;
    }

    if (presentationSlides.length === 0) return;

    currentSlide = 0;
    renderSlide();
    document.getElementById('presentation-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function buildPresSlides(md) {
    // Split by ## headers
    const sections = md.split(/(?=## )/);
    presentationSlides = sections.filter(s => s.trim().length > 30);
    if (presentationSlides.length === 0) {
        presentationSlides = [md];
    }
}

function renderSlide() {
    const content = document.getElementById('pres-slide-content');
    content.innerHTML = markdownToHtml(presentationSlides[currentSlide] || '');
    document.getElementById('pres-counter').textContent = `${currentSlide + 1} / ${presentationSlides.length}`;
}

function nextSlide() {
    if (currentSlide < presentationSlides.length - 1) {
        currentSlide++;
        renderSlide();
    }
}

function prevSlide() {
    if (currentSlide > 0) {
        currentSlide--;
        renderSlide();
    }
}

function exitPresentation() {
    document.getElementById('presentation-overlay').style.display = 'none';
    document.body.style.overflow = '';
}

// ===== COMPETITOR BAD REVIEW POP-UP (v2 — rotation, no repeats, shuffle) =====

let oppPool = [];           // shuffled pool of reviews
let oppSeenIds = new Set();  // track shown review IDs
let oppCurrentIdx = 0;
let oppToastTimer = null;
let oppCooldownTimer = null;
let oppFirstShowDone = false;

function startOppToast(reviews) {
    stopOppToast();

    // Filter meaningful reviews, assign unique IDs
    oppPool = reviews
        .filter(r => r.text && r.text.length >= 10)
        .map((r, i) => ({ ...r, _id: `opp_${i}_${Date.now()}` }));

    if (oppPool.length === 0) return;

    // Shuffle (Fisher-Yates)
    shuffleArray(oppPool);
    oppSeenIds.clear();
    oppCurrentIdx = 0;
    oppFirstShowDone = false;

    // 5s delay before first popup
    oppCooldownTimer = setTimeout(() => {
        oppFirstShowDone = true;
        showNextOppToast();
        oppToastTimer = setInterval(showNextOppToast, 15000);
    }, 5000);
}

function shuffleArray(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
}

function showNextOppToast() {
    if (oppPool.length === 0) return;

    // If all reviews shown, re-shuffle and reset
    if (oppSeenIds.size >= oppPool.length) {
        oppSeenIds.clear();
        shuffleArray(oppPool);
        oppCurrentIdx = 0;
    }

    // Find next unseen review
    let review = null;
    let attempts = 0;
    while (attempts < oppPool.length) {
        const candidate = oppPool[oppCurrentIdx % oppPool.length];
        oppCurrentIdx++;
        if (!oppSeenIds.has(candidate._id)) {
            review = candidate;
            oppSeenIds.add(candidate._id);
            break;
        }
        attempts++;
    }

    if (!review) return;

    const toast = document.getElementById('opp-toast');
    const starsEl = document.getElementById('opp-toast-stars');
    const bizEl = document.getElementById('opp-toast-business');
    const textEl = document.getElementById('opp-toast-text');

    // Store for modal expand
    currentOppReview = review;

    // Animate out then in
    toast.classList.remove('visible');
    setTimeout(() => {
        starsEl.innerHTML = renderStars(review.rating);
        bizEl.textContent = review.business_name || review.business || 'Rakip İşletme';
        // Truncate to 120 chars
        const text = review.text.length > 120 ? review.text.substring(0, 120) + '...' : review.text;
        textEl.textContent = text;
        toast.classList.add('visible');
    }, 500);
}

function closeOppToast() {
    document.getElementById('opp-toast').classList.remove('visible');

    // 30s cooldown after user closes, then resume
    if (oppToastTimer) {
        clearInterval(oppToastTimer);
        oppToastTimer = null;
    }
    if (oppCooldownTimer) clearTimeout(oppCooldownTimer);

    oppCooldownTimer = setTimeout(() => {
        showNextOppToast();
        oppToastTimer = setInterval(showNextOppToast, 15000);
    }, 30000);
}

function stopOppToast() {
    if (oppToastTimer) { clearInterval(oppToastTimer); oppToastTimer = null; }
    if (oppCooldownTimer) { clearTimeout(oppCooldownTimer); oppCooldownTimer = null; }
    document.getElementById('opp-toast').classList.remove('visible');
}

function renderStars(rating) {
    let stars = '';
    for (let i = 0; i < 5; i++) {
        stars += i < rating
            ? '<span style="color:#F5C518">★</span>'
            : '<span style="color:rgba(255,255,255,0.15)">☆</span>';
    }
    return stars;
}

let currentOppReview = null;

function expandOpportunity() {
    // currentOppReview is set by showNextOppToast
    if (!currentOppReview) return;

    const reviewText = currentOppReview.text || '';
    const insights = analyzeComplaint(reviewText);

    const body = document.getElementById('opp-modal-body');
    body.innerHTML = `
        <div class="opp-review-box">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                ${renderStars(currentOppReview.rating)}
                <span style="font-size:0.75rem;color:var(--text-muted);">${currentOppReview.business_name || currentOppReview.business || 'Rakip İşletme'}</span>
            </div>
            <p style="font-size:0.88rem;line-height:1.6;font-style:italic;color:var(--text-secondary);">"${reviewText}"</p>
        </div>

        <div class="opp-insight">
            <h4>🔍 Tespit Edilen Sorun</h4>
            <div class="insight-tag">${insights.category}</div>
            <p>${insights.analysis}</p>
        </div>

        <div class="opp-actions">
            <h4>🎯 Stratejik Hamle Önerileri</h4>
            <ul>
                ${insights.actions.map(a => `<li>${a}</li>`).join('')}
            </ul>
        </div>

        <div class="opp-ads">
            <h4>📢 Kullanıma Hazır Reklam Metinleri</h4>
            ${insights.adCopies.map((ad, i) => `
            <div class="ad-copy-box">
                <div class="ad-copy-label">${['Instagram Story', 'Google Ads', 'WhatsApp Durum'][i] || 'Reklam ' + (i+1)}</div>
                <p>${ad}</p>
                <button class="btn-copy" onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent);this.textContent='✓ Kopyalandı';setTimeout(()=>this.textContent='📋 Kopyala',1500)">📋 Kopyala</button>
            </div>`).join('')}
        </div>
    `;

    document.getElementById('opp-modal').style.display = 'flex';
}

function analyzeComplaint(text) {
    const t = text.toLowerCase();
    const bizName = activeBusiness ? activeBusiness.name : 'Biz';

    const patterns = [
        // MUTFAK HIZI — yemek/sipariş geç geldi (sıra bekleme DEĞİL!)
        { keys: ['sipariş', 'yemek geç', 'geç geldi', 'uzun sürdü', 'beklettiler', 'gelmedi', 'servis yavaş', 'gecikmeli'],
          cat: '🍳 Mutfak Hızı / Sipariş Gecikmesi',
          analysis: 'Müşteri siparişinin geç gelmesinden şikayetçi. Bu bir MUTFAK HIZI sorunudur — randevu veya sıra sorunu değil. Mutfak iş akışı, personel sayısı veya hazırlık süreci gözden geçirilmeli.',
          actions: [
            'Mutfak iş akışını optimize edin: sipariş alımından servis edilene kadar ortalama süreyi ölçün',
            'Yoğun saatlerde (12:00-14:00, 19:00-21:00) mutfağa 1 yardımcı ekleyin',
            'Hazırlığı uzun süren menü öğelerini önceden hazırlık (mise en place) listesine alın',
          ],
          ads: [
            `${bizName}'de artık her sipariş 15 dakikada masanızda! Yeni mutfak düzenimizle hızlı ve lezzetli servis garanti 🍳⚡`,
            `Öğle tatilinde vaktiniz az mı? ${bizName} hızlı servis garantisi ile yemek molasını keyfe dönüştürün 😋`,
            `Beklemeden, acele etmeden, tam zamanında! ${bizName}'de sipariş verdikten sonra keyfinize bakın ☕`,
          ]
        },
        // SIRA BEKLEME — kapıda/girişte sıra
        { keys: ['sıra', 'kuyruk', 'yer bulamadık', 'masa yoktu', 'kalabalık', 'doluydu', 'rezervasyon'],
          cat: '👥 Kapasite / Sıra Sorunu',
          analysis: 'Müşteri yer bulamamış veya girişte sıra beklemiş. Bu bir kapasite yönetimi sorunudur.',
          actions: [
            'Online rezervasyon sistemi kurun — WhatsApp veya web üzerinden masa ayırtma imkanı sunun',
            'Yoğun saatlerde girişte bekleme tahtası kullanın, tahmini süre bildirin',
            'Bar veya bekleme alanı oluşturun — bekleyen müşteriye ikram yapın',
          ],
          ads: [
            `${bizName}'de yerinizi önceden ayırtın! Online rezervasyon ile beklemeden masanız hazır 📲✨`,
            `Kapıda sıra yok, stresi yok! ${bizName} rezervasyon sistemiyle sorunsuz akşam yemeği 🍽️`,
            `Planınızı yapın, biz masanızı hazırlayalım 🥂 ${bizName} — hemen rezervasyon al!`,
          ]
        },
        // PERSONEL YETERSİZLİĞİ
        { keys: ['tek çalışan', 'personel az', 'yetersiz', 'garson yok', 'kimse ilgilenmedi', 'çağırdık gelmedi', 'ilgilenmediler'],
          cat: '👤 Personel Yetersizliği',
          analysis: 'Müşteri yeterli personel olmadığını belirtmiş. Bu doğrudan hizmet kalitesini etkileyen operasyonel bir sorundur.',
          actions: [
            'Yoğun saatlere özel part-time personel alın veya vardiya düzenlemesi yapın',
            'Garson çağrı sistemi kurun (zil butonu veya QR kod ile sipariş)',
            'Self-servis noktaları ekleyin (su, çay, peçete) — garson yükünü azaltın',
          ],
          ads: [
            `${bizName}'de sizi fark etmemek imkansız! Profesyonel ekibimiz her an yanınızda 🙋‍♂️✨`,
            `"Garson!" diye bağırmanıza gerek yok 😊 ${bizName}'de masanızdaki QR koddan sipariş verin!`,
            `Ekip olarak büyüdük, hizmet kalitemiz de! ${bizName}'de yeni kadromuzla tanışın 👨‍🍳👩‍🍳`,
          ]
        },
        // YEMEK KALİTESİ
        { keys: ['lezzetsiz', 'vasat', 'tatsız', 'soğuk geldi', 'bayat', 'kalitesiz', 'kötü yemek', 'beğenmedim', 'hayal kırıklığı', 'tadı yok', 'berbat'],
          cat: '🍽️ Yemek / Ürün Kalitesi Sorunu',
          analysis: 'Müşteri yemek/ürün kalitesinden memnun kalmamış. Bu, malzeme kalitesi, şef yetkinliği veya hazırlık süreci ile ilgilidir.',
          actions: [
            'Menüdeki en çok şikayet alan 3 ürünü belirleyin, tarifleri yeniden düzenleyin',
            'Taze malzeme tedarikçinizi gözden geçirin — "bugünün tazesi" konseptini vurgulayın',
            'Mutfakta tadım kontrolü sürecini standart hale getirin — servis öncesi şef onayı',
          ],
          ads: [
            `${bizName}'de şefimiz bugün taze malzemelerle hazırladı! Her tabak özenle hazırlanıyor 👨‍🍳🌿`,
            `Lezzet garanti! ${bizName}'de beğenmezseniz hesap bizden ⭐ Bu güveni veren kalitemizi deneyin!`,
            `Taze, ev yapımı lezzetler arıyorsanız doğru adrestesiniz 🍲 ${bizName} — tadına bak, farkı anla!`,
          ]
        },
        // FİYAT-DEĞER
        { keys: ['pahalı', 'fiyat', 'para', 'ücret', 'kazık', 'fahiş', 'hesap', 'porsiyon küçük', 'porsiyon az', 'maliyet'],
          cat: '💰 Fiyat-Değer Dengesi Sorunu',
          analysis: 'Müşteri fiyatı ödediği değere göre yüksek buluyor veya porsiyon-fiyat dengesinden memnun değil.',
          actions: [
            'Porsiyon-fiyat analizini yapın: rakiplerle gram/fiyat karşılaştırması çıkarın',
            'Menüde "En çok tercih edilen" veya "Şefin önerisi" etiketleriyle yönlendirme yapın',
            'Kombo menüler veya "2 kişilik özel" paketler sunarak algılanan değeri artırın',
          ],
          ads: [
            `${bizName}'de doyurucu lezzetler, şeffaf fiyatlar! 💰 Menümüz sitemizde, gelmeden bilin!`,
            `İkili özel! ${bizName}'de 2 kişilik menü uygun fiyata 🍽️ Lezzet ve ekonomi bir arada!`,
            `Kaliteden ödün vermeden, bütçeye uygun lezzetler ✨ ${bizName} — tadına bakan bir daha gelir!`,
          ]
        },
        // PERSONEL TAVRI
        { keys: ['ilgisiz', 'kaba', 'saygısız', 'umursamaz', 'soğuk tavır', 'muamele', 'güler yüz', 'suratsız'],
          cat: '😤 Personel Tavrı / İlgi Eksikliği',
          analysis: 'Müşteri personelin ilgisinden veya tavrından rahatsız olmuş. Bu, tekrar gelme kararını doğrudan etkileyen kritik bir sorundur.',
          actions: [
            'Haftalık 15 dakikalık "müşteri deneyimi" toplantıları başlatın — iyi/kötü örnekleri paylaşın',
            'Her müşteriyi ismiyle karşılama ve ikram sunma standardı oluşturun',
            'Google/Instagram\'da müşteri hikayesi paylaşın — "Müşterilerimiz ailedir" mesajı verin',
          ],
          ads: [
            `${bizName}'de her misafir VIP! 👑 Kapıdan girdiğiniz an çay/kahve hazır, isminizle karşılanırsınız ☕`,
            `Sadece yemek değil, deneyim yaşatıyoruz ✨ ${bizName} — misafirperverliğin adresi!`,
            `Güler yüz bizim olsun, keyif sizin! ${bizName}'e bir kez gelin, farkı yaşayın 😊`,
          ]
        },
        // FİZİKSEL ORTAM
        { keys: ['soğuk ortam', 'sıcak ortam', 'klima', 'ısıtma', 'havasız', 'karanlık', 'gürültü', 'müzik yüksek', 'ses'],
          cat: '🏠 Fiziksel Ortam / Ambiyans Sorunu',
          analysis: 'Müşteri mekanın fiziksel koşullarından (sıcaklık, ses, aydınlatma) rahatsız olmuş.',
          actions: [
            'Isıtma/soğutma sistemini kontrol edin — termostatı 22-24°C aralığında tutun',
            'Ses seviyesi ölçüm uygulaması kullanın — müzik 60-65 dB\'yi geçmesin',
            'Aydınlatmayı bölge bazlı ayarlayın — yemek alanı sıcak ton, bar alanı loş',
          ],
          ads: [
            `${bizName}'de konfor her detayda! 🌡️ Mükemmel sıcaklık, ferah ortam — huzurla oturun!`,
            `Rahatınız bizim işimiz ✨ ${bizName} — temiz, ferah, huzurlu. Kendinizi evinizde hissedin!`,
            `Ortam temiz, müzik hafif, servis hızlı! ${bizName} farkı budur 🎶☕`,
          ]
        },
        // HİJYEN
        { keys: ['kirli', 'pis', 'hijyen', 'steril', 'temiz', 'dezenfekte', 'koku', 'toz'],
          cat: '🧹 Hijyen / Temizlik Sorunu',
          analysis: 'Müşteri hijyen standardından memnun olmamış. Sağlık riski taşıması nedeniyle en yüksek öncelikli sorundur.',
          actions: [
            'Günde 3 kez temizlik turu standartı oluşturun — özellikle tuvalet ve giriş alanı',
            'Sterilizasyon/temizlik sürecinizi sosyal medyada video olarak paylaşın',
            'Hijyen sertifikalarınızı girişte ve online görünür yapın',
          ],
          ads: [
            `${bizName}'de medikal düzey hijyen standardı! 🧤 Her alan dezenfekte, her detay kontrollü!`,
            `Sağlığınız bizim önceliğimiz 🛡️ ${bizName} — gönül rahatlığıyla gelin!`,
            `Ultra hijyenik ortam + profesyonel ekip = ${bizName} farkı ✨`,
          ]
        },
        // RANDEVU / BEKLEME (berber/kuaför/sağlık)
        { keys: ['randevu', 'bekle', 'sıra beklettiler', 'geç aldılar'],
          cat: '⏱️ Randevu / Bekleme Yönetimi',
          analysis: 'Müşteri randevu veya sıra beklemekten şikayetçi. Bu, randevu yönetim sistemi veya zaman planlaması sorunudur.',
          actions: [
            'Online randevu sistemi kurun — müşteri geldiğinde direkt hizmet alsın',
            'Randevu aralarına 10-15 dakika tampon süre koyun — gecikme domino etkisi önlensin',
            'Yoğun/boş saatleri gösteren "en uygun saat" görseli sosyal medyada paylaşın',
          ],
          ads: [
            `⏱️ ${bizName}'de randevunuz hazır, bekleme yok! Online randevu al, gel otur, anında başlayalım 📲`,
            `Zamanınıza saygı duyuyoruz! ${bizName} — dakikası dakikasına randevu sistemi ⭐`,
            `${bizName} | Randevun varsa beklemen yok ✂️ Hemen randevu al!`,
          ]
        },
    ];

    for (const p of patterns) {
        if (p.keys.some(k => t.includes(k))) {
            return { category: p.cat, analysis: p.analysis, actions: p.actions, adCopies: p.ads };
        }
    }

    return {
        category: '📊 Genel Memnuniyetsizlik',
        analysis: 'Müşteri genel olarak hizmetten memnun kalmamış. Bu tür yorumlar detaylı incelendiğinde operasyonel iyileştirme fırsatlarına dönüşür.',
        actions: [
            'Bu yorumun tam olarak neye işaret ettiğini ekiple tartışın — müşterinin asıl beklentisi neydi?',
            'Haftada 1 kez "en çok tekrarlanan 3 şikayet" listesi çıkarın ve aksiyon alın',
            'Olumsuz yorum bırakan müşteriye 48 saat içinde kişisel yanıt yazın — geri kazanım şansı %30 artar',
        ],
        adCopies: [
            `${bizName} — müşteri memnuniyeti bizim için 1 numara! ⭐ Yüzlerce mutlu müşterimize katılın!`,
            `Kaliteli hizmet, güler yüz, profesyonel ekip ✨ ${bizName}'de her detay sizin için düşünüldü!`,
            `${bizName} farkını yaşayın! Google'da 5 yıldız alan hizmeti deneyin 📲`,
        ],
    };
}

function closeOppModal() {
    document.getElementById('opp-modal').style.display = 'none';
}

// ===== CRON TRIGGER =====
async function triggerCron() {
    try {
        const res = await fetch('/api/cron/trigger', { method: 'POST' });
        const data = await res.json();
        if (data.message) {
            alert('✅ Veri toplama arka planda başlatıldı. Birkaç dakika içinde veriler güncellenecek.');
        } else if (data.error) {
            alert('Hata: ' + data.error);
        }
    } catch {
        alert('Bağlantı hatası.');
    }
}

// ===== MARKDOWN TO HTML =====
function markdownToHtml(md) {
    if (!md) return '';
    let html = md;

    // Tables
    html = html.replace(/(\|.+\|\n)(\|[-|: ]+\|\n)((\|.+\|\n?)+)/g, function(match, header, separator, body) {
        const headers = header.trim().split('|').filter(c => c.trim());
        const rows = body.trim().split('\n');
        let table = '<table><thead><tr>';
        headers.forEach(h => table += `<th>${h.trim()}</th>`);
        table += '</tr></thead><tbody>';
        rows.forEach(row => {
            const cells = row.split('|').filter(c => c.trim());
            if (cells.length > 0) {
                table += '<tr>';
                cells.forEach(c => table += `<td>${c.trim()}</td>`);
                table += '</tr>';
            }
        });
        table += '</tbody></table>';
        return table;
    });

    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/^---$/gm, '<hr>');
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/((<li>.*<\/li>\n?)+)/g, '<ul>$&</ul>');
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    html = html.replace(/^(?!<[htlubo]|<li|<hr)(.+)$/gm, '<p>$1</p>');
    html = html.replace(/<p>\s*<\/p>/g, '');

    return html;
}

// ===== UTILITIES =====
function shake(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.borderColor = '#ef4444';
    el.style.animation = 'shake 0.4s ease-in-out';
    el.focus();
    setTimeout(() => { el.style.borderColor = ''; el.style.animation = ''; }, 600);
}

function handleKeyboard(e) {
    // Ctrl+Enter to submit
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (currentView === 'analysis') {
            const selection = document.getElementById('analysis-selection');
            if (selection.style.display === 'block' && selectedAnalysisUrl) {
                runAnalysis();
            } else {
                findBusinessesAnalysis();
            }
        }
    }

    // Presentation mode keys
    if (document.getElementById('presentation-overlay').style.display === 'flex') {
        if (e.key === 'ArrowRight' || e.key === ' ') nextSlide();
        if (e.key === 'ArrowLeft') prevSlide();
        if (e.key === 'Escape') exitPresentation();
    }

    // Escape for modals
    if (e.key === 'Escape') {
        closeOppModal();
    }
}
