document.addEventListener('DOMContentLoaded', () => {
    const backendUrl = 'https://youtubercd.onrender.com';
    let allVideos = { short: [], long: [] };
    let shortTermIndex = 0;
    let longTermIndex = 0;
    const VIDEOS_PER_LOAD = 2;

    document.getElementById('searchForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = document.getElementById('query').value.trim();
        if (!query) return;
        const resultDiv = document.getElementById('result');
        resultDiv.innerHTML = '<div class="loader"></div>';

        try {
            const uploadFilter = document.getElementById('upload-filter').value;
            const sortFilter = document.getElementById('sort-filter').value;
            const params = new URLSearchParams({ query });
            if (uploadFilter) params.append('uploadDate', uploadFilter);
            if (sortFilter) params.append('sortBy', sortFilter);

            const response = await fetch(`${backendUrl}/search?${params.toString()}`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });
            if (!response.ok) throw new Error((await response.json()).error || 'Fetch failed');

            const videos = await response.json();
            allVideos.short = videos.filter(v => v.duration < 10 * 60 && v.duration > 0);
            allVideos.long = videos.filter(v => v.duration >= 10 * 60);
            shortTermIndex = 0;
            longTermIndex = 0;

            resultDiv.innerHTML = `
                <p class="analyzed-count">Analyzed ${videos.length} videos</p>
                <div class="tabs">
                    <button class="tab active" data-tab="short">Short Term</button>
                    <button class="tab" data-tab="long">Long Term</button>
                </div>
                <div class="video-grid" id="video-grid"></div>
                <button id="load-more" class="load-more">Load More</button>
            `;

            shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);
            setupTabs();
            document.getElementById('load-more').addEventListener('click', () => {
                const activeTab = document.querySelector('.tab.active').dataset.tab;
                if (activeTab === 'short') {
                    shortTermIndex = displayVideos('short', allVideos.short, shortTermIndex);
                } else {
                    longTermIndex = displayVideos('long', allVideos.long, longTermIndex);
                }
            });
        } catch (error) {
            resultDiv.innerHTML = `<p class="error">Error: ${error.message}</p>`;
        }
    });

    function displayVideos(type, videos, index) {
        const grid = document.getElementById('video-grid');
        const end = index + VIDEOS_PER_LOAD;
        const newVideos = videos.slice(index, end);
        newVideos.forEach(video => {
            grid.innerHTML += `
                <div class="video-card">
                    <a href="https://www.youtube.com/watch?v=${video.id}" target="_blank">
                        <img src="${video.thumbnail}" alt="${video.title}" class="video-thumbnail">
                        <div class="video-info">
                            <h3>${video.title}</h3>
                            <p class="channel">${video.channel}</p>
                            <p class="duration">${parseDuration(video.duration)}</p>
                            <p class="views">${formatNumber(video.views)} views</p>
                            <p class="likes">${formatNumber(video.likes)} likes</p>
                            <p class="upload-date">${video.upload_date}</p>
                            <p class="description">${video.description.slice(0, 100)}...</p>
                        </div>
                    </a>
                </div>
            `;
        });
        return end;
    }

    function setupTabs() {
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const grid = document.getElementById('video-grid');
                grid.innerHTML = '';
                if (tab.dataset.tab === 'short') {
                    shortTermIndex = displayVideos('short', allVideos.short, 0);
                } else {
                    longTermIndex = displayVideos('long', allVideos.long, 0);
                }
            });
        });
    }

    function parseDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }

    function formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num;
    }
});
