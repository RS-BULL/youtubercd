from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
import re
import logging

app = Flask(__name__)
CORS(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers to mimic a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# In-memory cache for recent queries
cache = {}

# Helper function to extract ytInitialData JSON from YouTube pages
def extract_yt_initial_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    for script in scripts:
        if 'ytInitialData' in script.text:
            start = script.text.find('{')
            end = script.text.rfind('}') + 1
            json_data = script.text[start:end]
            return json.loads(json_data)
    return None

# Parse relative time (e.g., "5 years ago") to a date
def parse_relative_time(time_str):
    now = datetime.now()
    match = re.match(r'(\d+)\s*(year|month|week|day|hour|minute|second)s?\s*ago', time_str)
    if not match:
        return now  # Default to now if parsing fails
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'year':
        return now - timedelta(days=value * 365)
    elif unit == 'month':
        return now - timedelta(days=value * 30)
    elif unit == 'week':
        return now - timedelta(weeks=value)
    elif unit == 'day':
        return now - timedelta(days=value)
    elif unit == 'hour':
        return now - timedelta(hours=value)
    elif unit == 'minute':
        return now - timedelta(minutes=value)
    elif unit == 'second':
        return now - timedelta(seconds=value)
    return now

# Parse views (e.g., "1.2M views")
def parse_views(view_text):
    if not view_text or view_text == 'Unknown':
        return 0
    view_text = view_text.replace(',', '').replace(' views', '')
    if 'K' in view_text:
        return int(float(view_text.replace('K', '')) * 1000)
    elif 'M' in view_text:
        return int(float(view_text.replace('M', '')) * 1000000)
    return int(view_text)

# Parse duration (e.g., "5:30" or "1:23:45")
def parse_duration(duration_text):
    if not duration_text or duration_text == 'Unknown':
        return 0
    parts = duration_text.split(':')
    if len(parts) == 3:  # Hours:Minutes:Seconds
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:  # Minutes:Seconds
        return int(parts[0]) * 60 + int(parts[1])
    return 0

# Search videos via web scraping
@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    # Log the request
    logger.info(f"Received search request: query={query}, upload_filter={upload_filter}, sort_by={sort_by}")

    # Check cache
    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        logger.info("Returning cached result")
        return jsonify(cache[cache_key])

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch YouTube search page: status_code={response.status_code}")
        return jsonify({'error': 'Failed to fetch YouTube search page'}), 500

    data = extract_yt_initial_data(response.text)
    if not data:
        logger.error("Unable to find ytInitialData in the page")
        return jsonify({'error': 'Unable to find video data'}), 500

    # Log the raw ytInitialData for debugging
    logger.info(f"ytInitialData: {json.dumps(data, indent=2)[:500]}...")  # Log first 500 characters

    video_list = []
    try:
        # Try to find the video list in the new structure
        contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
        if not contents:
            logger.error("No contents found in ytInitialData")
            return jsonify({'error': 'No video contents found'}), 500

        videos = None
        for section in contents:
            if 'itemSectionRenderer' in section:
                videos = section['itemSectionRenderer'].get('contents', [])
                break

        if not videos:
            logger.error("No videos found in itemSectionRenderer")
            return jsonify({'error': 'No videos found'}), 500

        logger.info(f"Found {len(videos)} videos in search results")

        for video in videos[:200]:  # Scan up to 200 videos
            if 'videoRenderer' not in video:
                continue

            video_data = video['videoRenderer']
            video_id = video_data.get('videoId')
            title = video_data.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown Title')
            thumbnail = video_data.get('thumbnail', {}).get('thumbnails', [{}])[0].get('url', '')
            duration = video_data.get('lengthText', {}).get('simpleText', '0:00')
            channel = video_data.get('ownerText', {}).get('runs', [{}])[0].get('text', 'Unknown Channel')
            published = video_data.get('publishedTimeText', {}).get('simpleText', 'Unknown')
            description = video_data.get('detailedMetadataSnippets', [{}])[0].get('snippetText', {}).get('runs', [{}])[0].get('text', '')
            views = video_data.get('viewCountText', {}).get('simpleText', '0 views')

            # Parse views and duration
            views = parse_views(views)
            duration_seconds = parse_duration(duration)

            # Parse upload date
            upload_date = parse_relative_time(published)

            # Apply upload date filter
            six_months_ago =ാ

            if upload_filter == 'last_6_months' and upload_date < six_months_ago:
                logger.info(f"Skipping video {title}: too old for last_6_months filter")
                continue
            elif upload_filter == 'before_6_months' and upload_date >= six_months_ago:
                logger.info(f"Skipping video {title}: too new for before_6_months filter")
                continue

            # Relax the query matching (remove transcript dependency)
            title_match = any(word in title.lower() for word in query.lower().split())
            description_match = any(word in description.lower() for word in query.lower().split())
            if not (title_match or description_match):
                logger.info(f"Skipping video {title}: query not found in title or description")
                continue

            # For now, skip sentiment analysis to reduce requests
            sentiment_ratio = 0.5  # Neutral default
            likes = 0  # We'll reintroduce this later

            # Calculate views-to-likes ratio
            views_to_likes = likes / views if views > 0 else 0

            # Score the video
            score = (sentiment_ratio * 0.4) + (views_to_likes * 0.3) + (views * 0.000001 * 0.3)

            video_list.append({
                'id': video_id,
                'title': title,
                'thumbnail': thumbnail,
                'duration': duration_seconds,  # In seconds
                'channel': channel,
                'published': published,
                'description': description,
                'views': views,
                'likes': likes,
                'score': score,
                'upload_date': upload_date.strftime('%Y-%m-%d')
            })

            if len(video_list) >= 50:  # Limit to 50 videos to improve performance
                break

        logger.info(f"After filtering, {len(video_list)} videos remain")

        # Sort videos
        if sort_by == 'most_viewed':
            video_list.sort(key=lambda x: x['views'], reverse=True)
        elif sort_by == 'most_liked':
            video_list.sort(key=lambda x: x['likes'], reverse=True)

        # Cache the result
        cache[cache_key] = video_list
        if len(cache) > 100:  # Limit cache size
            cache.pop(next(iter(cache)))

        return jsonify(video_list)
    except Exception as e:
        logger.error(f"Error parsing video data: {str(e)}")
        return jsonify({'error': f'Error parsing video data: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
