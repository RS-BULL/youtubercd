const backendUrl = 'https://your-app-name.up.railway.app'; // Replace with your Railway URL
const VIDEOS_PER_LOAD = 2;
let allVideos = { short: [], long: [] };
let currentTab = 'short';

function parseDuration(seconds) {
    if (!seconds) return "0:00";
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds < 10 ? '0' : ''}${remainingSeconds}`;
}

function formatNumber(num) {
    if (!num) return '0';
    num = parseInt(num) || 0;
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

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

document.getElementById('searchForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('query').value;
    const resultDiv = document.getElementById('result');
    resultDiv.innerHTML = '<div class="loader"></div>';

    try {
        // Only include filters in the URL if they are selected
        const uploadFilter = document.getElementById('upload-filter').value || '';
        const sortFilter = document.getElementById('sort-filter').value || '';
        let url = `${backendUrl}/search?query=${encodeURIComponent(query)}`;
        if (uploadFilter) url += `&uploadDate=${uploadFilter}`;
        if (sortFilter) url += `&sortBy=${sortFilter}`;

        const response = await fetch(url);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Backend error: ${response.status} - ${errorText}`);
        }
        const data = await response.json();

        allVideos.short = data.short || [];
        allVideos.long = data.long || [];

        let shortTermIndex = 0;
        let longTermIndex = 0;

        resultDiv.innerHTML = `
            <p class="analyzed-count">Analyzed ${allVideos.short.length + allVideos.long.length} videos to find the best for you</p>
            <div class="tabs">
                <button class="tab active" data-tab="short">Quick Watches</button>
                <button class="tab" data-tab="long">In-Depth Videos</button>
            </div>
            <div class="video-grid" id="video-grid"></div>
            <button id="load-more" class="load-more">Load More</button>
        `;

        shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTab = tab.dataset.tab;
                document.getElementById('video-grid').innerHTML = '';
                if (currentTab === 'short') {
                    shortTermIndex = displayVideos('short', allVideos.short, 0);
                } else {
                    longTermIndex = displayVideos('long', allVideos.long, 0);
                }
            });
        });

        document.getElementById('load-more').addEventListener('click', () => {
            if (currentTab === 'short') {
                shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);
                if (shortTermIndex >= allVideos.short.length) {
                    document.getElementById('load-more').style.display = 'none';
                }
            } else {
                longTermIndex = displayVideos('long', allVideos.long, longTermIndex);
                if (longTermIndex >= allVideos.long.length) {
                    document.getElementById('load-more').style.display = 'none';
                }
            }
        });
    } catch (error) {
        console.error('Error:', error);
        resultDiv.innerHTML = `<p class="error">${error.message}</p>`;
    }
});
