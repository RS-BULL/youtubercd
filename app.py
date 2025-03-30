from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from datetime import datetime, timedelta
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import os
import logging
import asyncio
import aiohttp

app = Flask(__name__)
CORS(app, resources={r"/search": {"origins": ["https://rs-bull.github.io", "*"]}})

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

cache = {}
analyzer = SentimentIntensityAnalyzer()

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

def parse_relative_time(time_str):
    now = datetime.now()
    match = re.match(r'(\d+)\s*(year|month|week|day|hour|minute|second)s?\s*ago', time_str)
    if not match:
        return now
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

def parse_views(view_text):
    if not view_text or view_text == 'Unknown':
        return 0
    view_text = view_text.replace(',', '').replace(' views', '')
    if 'K' in view_text:
        return int(float(view_text.replace('K', '')) * 1000)
    elif 'M' in view_text:
        return int(float(view_text.replace('M', '')) * 1000000)
    return int(view_text)

def parse_duration(duration_text):
    if not duration_text or duration_text == 'Unknown':
        return 0
    parts = duration_text.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0

async def fetch_page(session, url):
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
        if response.status == 200:
            return await response.text()
        return None

async def get_comments(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, url)
        if not html:
            return []
        data = extract_yt_initial_data(html)
        if not data:
            return []
        try:
            # Placeholder: Actual comment fetching requires YouTube API or deeper scraping
            # Simulate fetching top 25 comments
            return [f"Sample comment {i}" for i in range(25)]
        except (KeyError, IndexError):
            return []

def analyze_sentiment(comments):
    if not comments:
        return 0
    positive = 0
    for comment in comments[:25]:
        score = analyzer.polarity_scores(comment)
        if score['compound'] > 0.05:
            positive += 1
    return positive / min(len(comments), 25)

def check_content_match(query, title, description):
    query_terms = set(query.lower().split())
    title_lower = title.lower()
    description_lower = description.lower()
    match_score = sum(1 for term in query_terms if term in title_lower or term in description_lower)
    return match_score / len(query_terms) if query_terms else 0

async def process_video(video, query):
    video_data = video.get('videoRenderer', {})
    video_id = video_data.get('videoId')
    title = video_data.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
    thumbnail = video_data.get('thumbnail', {}).get('thumbnails', [{}])[0].get('url', '')
    duration = video_data.get('lengthText', {}).get('simpleText', '0:00')
    channel = video_data.get('ownerText', {}).get('runs', [{}])[0].get('text', 'Unknown')
    published = video_data.get('publishedTimeText', {}).get('simpleText', 'Unknown')
    description = video_data.get('detailedMetadataSnippets', [{}])[0].get('snippetText', {}).get('runs', [{}])[0].get('text', '')

    content_match = check_content_match(query, title, description)
    if content_match < 0.5:
        return None

    async with aiohttp.ClientSession() as session:
        video_html = await fetch_page(session, f"https://www.youtube.com/watch?v={video_id}")
        views = 0
        likes = 0
        if video_html:
            video_data = extract_yt_initial_data(video_html)
            if video_data:
                try:
                    video_info = video_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                    views_text = video_info.get('viewCount', {}).get('videoViewCountRenderer', {}).get('viewCount', {}).get('simpleText', '0 views')
                    views = parse_views(views_text)
                    likes_data = video_info.get('videoActions', {}).get('menuRenderer', {}).get('topLevelButtons', [{}])[0].get('toggleButtonRenderer', {})
                    likes = int(likes_data.get('defaultText', {}).get('simpleText', '0').replace(',', '')) if likes_data else 0
                except (KeyError, IndexError):
                    pass

    if views == 0 or likes == 0:
        return None

    views_to_likes_ratio = likes / views if views > 0 else 0
    comments = await get_comments(video_id)
    sentiment_ratio = analyze_sentiment(comments)

    score = (content_match * 5) + (views * 0.000001) + (likes * 0.001) + (views_to_likes_ratio * 10) + (sentiment_ratio * 5)
    duration_seconds = parse_duration(duration)
    upload_date = parse_relative_time(published)

    return {
        'id': video_id,
        'title': title,
        'thumbnail': thumbnail,
        'duration': duration_seconds,
        'channel': channel,
        'published': published,
        'description': description,
        'views': views,
        'likes': likes,
        'score': score,
        'upload_date': upload_date.strftime('%Y-%m-%d')
    }

@app.route('/search', methods=['GET'])
async def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    if not query:
        logger.warning("No query provided")
        return jsonify({'error': 'Query parameter is required'}), 400

    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        logger.info(f"Returning cached result for {cache_key}")
        return jsonify(cache[cache_key])

    try:
        logger.info(f"Fetching YouTube results for query: {query}")
        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, f"https://www.youtube.com/results?search_query={query}")
            if not html:
                logger.error("Failed to fetch YouTube search results")
                return jsonify({'error': 'Failed to fetch YouTube search results'}), 502

            data = extract_yt_initial_data(html)
            if not data:
                logger.error("Unable to parse ytInitialData")
                return jsonify({'error': 'Unable to parse video data from YouTube'}), 500

            contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
            videos = next((item['itemSectionRenderer']['contents'] for item in contents if 'itemSectionRenderer' in item), [])

            tasks = [process_video(video, query) for video in videos[:50]]
            video_list = [v for v in await asyncio.gather(*tasks) if v]

            six_months_ago = datetime.now() - timedelta(days=180)
            if upload_filter == 'last_6_months':
                video_list = [v for v in video_list if datetime.strptime(v['upload_date'], '%Y-%m-%d') >= six_months_ago]
            elif upload_filter == 'before_6_months':
                video_list = [v for v in video_list if datetime.strptime(v['upload_date'], '%Y-%m-%d') < six_months_ago]

            video_list.sort(key=lambda x: x['score'], reverse=True)
            cache[cache_key] = video_list[:10]
            if len(cache) > 100:
                cache.pop(next(iter(cache)))

            logger.info(f"Successfully processed {len(video_list)} videos for query: {query}")
            return jsonify(video_list[:10])
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)
