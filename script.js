const backendUrl = 'https://youtubercd.onrender.com';

document.addEventListener('DOMContentLoaded', () => {
    const searchButton = document.getElementById('searchButton');
    const searchInput = document.getElementById('searchInput');
    const uploadDateFilter = document.getElementById('uploadDateFilter');
    const sortByFilter = document.getElementById('sortByFilter');

    searchButton.addEventListener('click', searchVideos);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchVideos();
    });

    // Populate dropdowns
    uploadDateFilter.innerHTML = `
        <option value="last_6_months">Last 6 Months</option>
        <option value="before_6_months">Before 6 Months</option>
        <option value="all">All Time</option>
    `;
    sortByFilter.innerHTML = `
        <option value="most_viewed">Most Viewed</option>
        <option value="most_liked">Most Liked</option>
    `;
});

async function searchVideos() {
    const query = document.getElementById('searchInput').value;
    const uploadDate = document.getElementById('uploadDateFilter').value;
    const sortBy = document.getElementById('sortByFilter').value;

    if (!query) {
        alert('Please enter a search query');
        return;
    }

    document.getElementById('results').innerHTML = '<div class="loading">Loading...</div>';

    try {
        const response = await fetch(`${backendUrl}/search?query=${encodeURIComponent(query)}&uploadDate=${uploadDate}&sortBy=${sortBy}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const videos = await response.json();
        displayResults(videos);
    } catch (error) {
        document.getElementById('results').innerHTML = '<p>Error fetching results. Please try again later.</p>';
        console.error('Error:', error);
    }
}

function displayResults(videos) {
    const resultsDiv = document.getElementById('results');
    if (videos.length === 0) {
        resultsDiv.innerHTML = '<p>No results found.</p>';
        return;
    }

    let html = '<div class="video-list">';
    videos.forEach(video => {
        const durationMinutes = Math.floor(video.duration / 60);
        const durationSeconds = video.duration % 60;
        html += `
            <div class="video-card">
                <a href="https://www.youtube.com/watch?v=${video.id}" target="_blank">
                    <h3>${video.title}</h3>
                </a>
                <div class="stats">
                    <span class="stat"><i class="fas fa-eye"></i> ${video.views.toLocaleString()} views</span>
                    <span class="stat"><i class="fas fa-thumbs-up"></i> ${video.likes.toLocaleString()} likes</span>
                    <span class="stat"><i class="fas fa-clock"></i> ${durationMinutes}m ${durationSeconds}s</span>
                    <span class="stat"><i class="fas fa-calendar-alt"></i> ${video.upload_date}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    resultsDiv.innerHTML = html;
}
