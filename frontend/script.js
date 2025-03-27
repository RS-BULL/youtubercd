const backendUrl = 'https://youtubercd.onrender.com'; // Replace with your Render URL
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

// Parse duration (e.g., "8:45" or "45" to minutes)
function parseDuration(duration) {
    if (!duration || duration === 'Unknown') return 0;
    const parts = duration.split(':');
    let minutes, seconds;
    if (parts.length === 1) {
        // Only seconds (e.g., "45")
        seconds = parseInt(parts[0]) || 0;
        minutes = 0;
    } else if (parts.length === 2) {
        // Minutes and seconds (e.g., "8:45")
        minutes = parseInt(parts[0]) || 0;
        seconds = parseInt(parts[1]) || 0;
    } else if (parts.length === 3) {
        // Hours, minutes, seconds (e.g., "1:23:45")
        minutes = parseInt(parts[0]) * 60 + (parseInt(parts[1]) || 0);
        seconds = parseInt(parts[2]) || 0;
    } else {
        return 0;
    }
    return Math.round(minutes + (seconds / 60)); // Round to nearest integer
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
    if (!num || num === 'Unknown') return '0';
    num = parseInt(num.replace(/[^0-9]/g, '')) || 0;
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

// Analyze transcript for relevance to query
function analyzeTranscript(transcript, query) {
    if (!transcript) return 0;
    const queryWords = query.toLowerCase().split(' ');
    const transcriptWords = transcript.toLowerCase().split(' ');
    return queryWords.reduce((score, word) => score + (transcriptWords.includes(word) ? 1 : 0), 0);
}

// Analyze title and description for relevance
function analyzeTitleDescription(title, description, query) {
    const queryWords = query.toLowerCase().split(' ');
    const text = (title + ' ' + description).toLowerCase();
    return queryWords.reduce((score, word) => score + (text.includes(word) ? 1 : 0), 0);
}

// Calculate overall score for a video
function calculateScore(video, transcriptScore, titleDescriptionScore) {
    const viewCount = parseInt(video.views.replace(/[^0-9]/g, '')) || 0;
    const viewScore = Math.log(viewCount + 1);
    let totalScore = (viewScore * 0.4) + (transcriptScore * 5) + (titleDescriptionScore * 3);

    // Penalize potential clickbait
    if (titleDescriptionScore > 0 && transcriptScore === 0) {
        totalScore *= 0.5;
    }
    return totalScore;
}

// Filter videos based on user selection
function filterVideos(videos, uploadFilter, sortFilter) {
    let filteredVideos = [...videos];
    
    // Filter by upload date
    const now = new Date();
    if (uploadFilter === 'lastWeek') {
        filteredVideos = filteredVideos.filter(video => {
            const uploadDate = parseRelativeTime(video.published);
            return (now - uploadDate) / (1000 * 60 * 60 * 24) <= 7;
        });
    } else if (uploadFilter === 'lastMonth') {
        filteredVideos = filteredVideos.filter(video => {
            const uploadDate = parseRelativeTime(video.published);
            return (now - uploadDate) / (1000 * 60 * 60 * 24) <= 30;
        });
    }

    // Sort by criteria
    if (sortFilter === 'mostViewed') {
        filteredVideos.sort((a, b) => {
            const viewsA = parseInt(a.views.replace(/[^0-9]/g, '')) || 0;
            const viewsB = parseInt(b.views.replace(/[^0-9]/g, '')) || 0;
            return viewsB - viewsA;
        });
    } else if (sortFilter === 'relevance') {
        filteredVideos.sort((a, b) => b.score - a.score);
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
                        <p class="duration"><i class="fas fa-clock"></i> ${video.duration} minutes</p>
                        <p class="views"><i class="fas fa-eye"></i> ${formatNumber(video.views)} views</p>
                        <p class="upload-date"><i class="fas fa-calendar-alt"></i> ${video.published}</p>
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
        // Step 1: Search for videos (includes details and transcripts)
        const response = await fetch(`${backendUrl}/search?query=${encodeURIComponent(query)}`);
        const videos = await response.json();
        if (!response.ok) throw new Error(videos.error || 'Error fetching videos');

        // Step 2: Process videos and calculate scores
        const scoredVideos = videos.map(video => {
            const transcriptScore = analyzeTranscript(video.transcript, query);
            const titleDescriptionScore = analyzeTitleDescription(video.title, video.description, query);
            const totalScore = calculateScore(video, transcriptScore, titleDescriptionScore);

            return {
                ...video,
                duration: parseDuration(video.duration),
                uploadDate: parseRelativeTime(video.published),
                score: totalScore
            };
        });

        // Step 3: Sort videos by score
        scoredVideos.sort((a, b) => b.score - a.score);

        // Step 4: Categorize videos by duration
        allVideos.short = scoredVideos.filter(video => video.duration < 10 && video.duration > 0);
        allVideos.long = scoredVideos.filter(video => video.duration >= 10);

        // Step 5: Display results with tabs and filters
        let shortTermIndex = 0;
        let longTermIndex = 0;

        resultDiv.innerHTML = `
            <p class="analyzed-count">Analyzed ${scoredVideos.length} videos to find the best for you</p>
            <div class="filters">
                <label>Upload Date: 
                    <select id="upload-filter">
                        <option value="all">All Time</option>
                        <option value="lastWeek">Last Week</option>
                        <option value="lastMonth">Last Month</option>
                    </select>
                </label>
                <label>Sort By: 
                    <select id="sort-filter">
                        <option value="relevance">Relevance</option>
                        <option value="mostViewed">Most Viewed</option>
                    </select>
                </label>
            </div>
            <div class="tabs">
                <button class="tab active" data-tab="short">Quick Watches</button>
                <button class="tab" data-tab="long">In-Depth Videos</button>
            </div>
            <div class="video-grid" id="video-grid"></div>
            <button id="load-more" class="load-more">Load More</button>
        `;

        // Initial display (fixed: show short videos in "Quick Watches")
        shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);

        // Tab switching (fixed: show correct category)
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTab = tab.dataset.tab;
                const uploadFilter = document.getElementById('upload-filter').value;
                const sortFilter = document.getElementById('sort-filter').value;
                const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
                document.getElementById('video-grid').innerHTML = '';
                if (currentTab === 'short') {
                    shortTermIndex = displayVideos('short', allVideos.short, 0);
                } else {
                    longTermIndex = displayVideos('long', allVideos.long, 0);
                }
            });
        });

        // Filter changes
        document.getElementById('upload-filter').addEventListener('change', () => {
            const uploadFilter = document.getElementById('upload-filter').value;
            const sortFilter = document.getElementById('sort-filter').value;
            const filteredVideos = filterVideos(allVideos[currentTab], uploadFilter, sortFilter);
            document.getElementById('video-grid').innerHTML = '';
            if (currentTab === 'short') {
                shortTermIndex = displayVideos('short', filteredVideos, 0);
            } else {
                longTermIndex = displayVideos('long', filteredVideos, 0);
            }
        });

        document.getElementById('sort-filter').addEventListener('change', () => {
            const uploadFilter = document.getElementById('upload-filter').value;
            const sortFilter = document.getElementById('sort-filter').value;
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
            const uploadFilter = document.getElementById('upload-filter').value;
            const sortFilter = document.getElementById('sort-filter').value;
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
