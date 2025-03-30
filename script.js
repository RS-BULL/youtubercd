const backendUrl = 'https://youtubercd.onrender.com';
const VIDEOS_PER_LOAD = 2;
let allVideos = { short: [], long: [] };
let currentTab = 'short';

// Load search history from localStorage
function loadSearchHistory() {
    const history = JSON.parse(localStorage.getItem('searchHistory')) || [];
    const historyDiv = document.getElementById('search-history');
    historyDiv.innerHTML = history.length ? '<h3>Recent Searches</h3>' : '';
    history.forEach(query => {
        const button = document.createElement('button');
        button.textContent = query;
        button.className = 'history-item';
        button.addEventListener('click', () => {
            document.getElementById('query').value = query;
            document.getElementById('searchForm').dispatchEvent(new Event('submit'));
        });
        historyDiv.appendChild(button);
    });
}

// Save search query to history
function saveSearchHistory(query) {
    let history = JSON.parse(localStorage.getItem('searchHistory')) || [];
    if (!history.includes(query)) {
        history.unshift(query);
        if (history.length > 5) history.pop();
        localStorage.setItem('searchHistory', JSON.stringify(history));
    }
    loadSearchHistory();
}

// Show/hide search history on input focus
const searchInput = document.getElementById('query');
const searchHistoryDiv = document.getElementById('search-history');
searchInput.addEventListener('focus', () => {
    loadSearchHistory();
    searchHistoryDiv.style.display = 'block';
});
searchInput.addEventListener('blur', () => {
    setTimeout(() => {
        searchHistoryDiv.style.display = 'none';
    }, 200);
});

// Parse duration (e.g., seconds to "mm:ss")
function parseDuration(seconds) {
    if (!seconds) return "0:00";
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
}

// Parse relative time (e.g., "5 years ago") to a date
function parseRelativeTime(timeStr) {
    const now = new Date();
    const match = timeStr.match(/(\d+)\s*(year|month|week|day|hour|minute|second)s?\s*ago/);
    if (!match) return now;
    const value = parseInt(match[1]);
    const unit = match[2];
    if (unit === 'year') return new Date(now.setFullYear(now.getFullYear() - value));
    if (unit === 'month') return new Date(now.setMonth(now.getMonth() - value));
    if (unit === 'week') return new Date(now.setDate(now.getDate() - value * 7));
    if (unit === 'day') return new Date(now.setDate(now.getDate() - value));
    if (unit === 'hour') return new Date(now.setHours(now.getHours() - value));
    if (unit === 'minute') return new Date(now.setMinutes(now.getMinutes() - value));
    if (unit === 'second') return new Date(now.setSeconds(now.getSeconds() - value));
    return now;
}

// Format large numbers
function formatNumber(num) {
    if (!num) return '0';
    num = parseInt(num) || 0;
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// Filter videos based on user selection
function filterVideos(videos, uploadFilter, sortFilter) {
    let filteredVideos = [...videos];
    
    // Sort by criteria
    if (sortFilter === 'most_viewed') {
        filteredVideos.sort((a, b) => b.views - a.views);
    } else if (sortFilter === 'most_liked') {
        filteredVideos.sort((a, b) => b.likes - a.likes);
    }

    return filteredVideos;
}

// Display videos for the current tab
function displayVideos(category, videos, index) {
    const grid = document.getElementById('video-grid');
    const end = index + VIDEOS_PER_LOAD;
    const nextVideos = videos.slice(index, end);
    nextVideos.forEach(video => {
        grid.innerHTML += `
            <div class="video-card">
                <a href="https://www.youtube.com/watch?v=${video.id}" target="_blank">
                    <img src="${video.thumbnail}" alt="${video.title}">
                    <div class="video-info">
                        <h3>${video.title}</h3>
                        <p class="channel"><i class="fas fa-user"></i> ${video.channel}</p>
                        <p class="duration"><i class="fas fa-clock"></i> ${parseDuration(video.duration)}</p>
                        <p class="views"><i class="fas fa-eye"></i> ${formatNumber(video.views)} views</p>
                        <p class="likes"><i class="fas fa-thumbs-up"></i> ${formatNumber(video.likes)} likes</p>
                        <p class="upload-date"><i class="fas fa-calendar-alt"></i> ${video.upload_date}</p>
                        <p class="description">${video.description.slice(0, 100) + '...'}</p>
                    </div>
                </a>
            </div>
        `;
    });
    return index + VIDEOS_PER_LOAD;
}

// Handle form submission
document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('query').value;
    const resultDiv = document.getElementById('result');
    resultDiv.innerHTML = '<div class="loader"></div>';

    // Save to search history
    saveSearchHistory(query);

    try {
        // Use default values if filters are not selected
        const uploadFilter = document.getElementById('upload-filter').value || 'all';
        const sortFilter = document.getElementById('sort-filter').value || 'most_viewed';
        const response = await fetch(`${backendUrl}/search?query=${encodeURIComponent(query)}&uploadDate=${uploadFilter}&sortBy=${sortFilter}`);
        const videos = await response.json();
        if (!response.ok) throw new Error(videos.error || 'Error fetching videos');

        // Categorize videos by duration
        allVideos.short = videos.filter(video => video.duration < 10 * 60 && video.duration > 0);
        allVideos.long = videos.filter(video => video.duration >= 10 * 60);

        // Display results with tabs
        let shortTermIndex = 0;
        let longTermIndex = 0;

        resultDiv.innerHTML = `
            <p class="analyzed-count">Analyzed ${videos.length} videos to find the best for you</p>
            <div class="tabs">
                <button class="tab active" data-tab="short">Quick Watches</button>
                <button class="tab" data-tab="long">In-Depth Videos</button>
            </div>
            <div class="video-grid" id="video-grid"></div>
            <button id="load-more" class="load-more">Load More</button>
        `;

        // Initial display
        shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTab = tab.dataset.tab;
                const uploadFilter = document.getElementById('upload-filter').value || 'all';
                const sortFilter = document.getElementById('sort-filter').value || 'most_viewed';
                const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
                document.getElementById('video-grid').innerHTML = '';
                if (currentTab === 'short') {
                    shortTermIndex = displayVideos('short', filteredVideos, 0);
                } else {
                    longTermIndex = displayVideos('long', filteredVideos, 0);
                }
            });
        });

        // Filter changes
        document.getElementById('upload-filter').addEventListener('change', () => {
            const uploadFilter = document.getElementById('upload-filter').value || 'all';
            const sortFilter = document.getElementById('sort-filter').value || 'most_viewed';
            const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
            document.getElementById('video-grid').innerHTML = '';
            if (currentTab === 'short') {
                shortTermIndex = displayVideos('short', filteredVideos, 0);
            } else {
                longTermIndex = displayVideos('long', filteredVideos, 0);
            }
        });

        document.getElementById('sort-filter').addEventListener('change', () => {
            const uploadFilter = document.getElementById('upload-filter').value || 'all';
            const sortFilter = document.getElementById('sort-filter').value || 'most_viewed';
            const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
            document.getElementById('video-grid').innerHTML = '';
            if (currentTab === 'short') {
                shortTermIndex = displayVideos('short', filteredVideos, 0);
            } else {
                longTermIndex = displayVideos('long', filteredVideos, 0);
            }
        });

        // Load more
        document.getElementById('load-more').addEventListener('click', () => {
            const uploadFilter = document.getElementById('upload-filter').value || 'all';
            const sortFilter = document.getElementById('sort-filter').value || 'most_viewed';
            const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
            if (currentTab === 'short') {
                shortTermIndex = displayVideos('short', filteredVideos, shortTermIndex);
                if (shortTermIndex >= filteredVideos.length) {
                    document.getElementById('load-more').style.display = 'none';
                }
            } else {
                longTermIndex = displayVideos('long', filteredVideos, longTermIndex);
                if (longTermIndex >= filteredVideos.length) {
                    document.getElementById('load-more').style.display = 'none';
                }
            }
        });
    } catch (error) {
        console.error('Error:', error);
        resultDiv.innerHTML = `<p class="error">${error.message}</p>`;
    }
});

// Load search history on page load
loadSearchHistory();
