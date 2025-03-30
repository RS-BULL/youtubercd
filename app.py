from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from datetime import datetime, timedelta
import re
from youtube_transcript_api import YouTubeTranscriptApi
from textblob import TextBlob
import os
import logging

app = Flask(__name__)
CORS(app, resources={r"/search": {"origins": ["https://rs-bull.github.io", "*"]}})

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

cache = {}

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
    deltas = {'year': 365, 'month': 30, 'week': 7, 'day': 1, 'hour': 1/24, 'minute': 1/1440, 'second': 1/86400}
    return now - timedelta(days=value * deltas[unit])

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

def get_comments_sentiment(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = session.get(url, headers=headers, timeout=5)
        if not response.ok:
            return 0, 0
        data = extract_yt_initial_data(response.text)
        if not data:
            return 0, 0
        # Simulating comment fetching (actual comment scraping requires API or more complex logic)
        positive, negative = 0, 0
        for _ in range(25):
            sentiment = TextBlob("Sample comment text").sentiment.polarity
            if sentiment > 0:
                positive += 1
            elif sentiment < 0:
                negative += 1
        return positive, negative
    except Exception:
        return 0, 0

def check_transcript(video_id, query):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        total_length = sum(item['duration'] for item in transcript)
        sample_length = total_length * 0.25
        current_length = 0
        sample_text = ""
        for item in transcript:
            sample_text += item['text'] + " "
            current_length += item['duration']
            if current_length >= sample_length:
                break
        query_words = set(query.lower().split())
        transcript_words = set(sample_text.lower().split())
        return len(query_words.intersection(transcript_words)) > 0
    except Exception:
        return False

@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    if not query:
        return jsonify({'error': 'Query parameter is required'}), 400

    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    try:
        url = f"https://www.youtube.com/results?search_query={query}"
        response = session.get(url, headers=headers, timeout=10)
        if not response.ok:
            return jsonify({'error': 'Failed to fetch YouTube search results'}), 502

        data = extract_yt_initial_data(response.text)
        if not data:
            return jsonify({'error': 'Unable to parse video data'}), 500

        contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
        videos = next((item['itemSectionRenderer']['contents'] for item in contents if 'itemSectionRenderer' in item), [])
        video_list = []

        for video in videos[:50]:
            if 'videoRenderer' not in video:
                continue
            video_data = video['videoRenderer']
            video_id = video_data.get('videoId')
            title = video_data.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
            thumbnail = video_data.get('thumbnail', {}).get('thumbnails', [{}])[0].get('url', '')
            duration = video_data.get('lengthText', {}).get('simpleText', '0:00')
            channel = video_data.get('ownerText', {}).get('runs', [{}])[0].get('text', 'Unknown')
            published = video_data.get('publishedTimeText', {}).get('simpleText', 'Unknown')
            description = video_data.get('detailedMetadataSnippets', [{}])[0].get('snippetText', {}).get('runs', [{}])[0].get('text', '')

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            video_response = session.get(video_url, headers=headers, timeout=5)
            views, likes = 0, 0
            if video_response.ok:
                video_data = extract_yt_initial_data(video_response.text)
                if video_data:
                    try:
                        video_info = video_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                        views = video_info.get('viewCount', {}).get('videoViewCountRenderer', {}).get('viewCount', {}).get('simpleText', '0 views')
                        likes_data = video_info.get('videoActions', {}).get('menuRenderer', {}).get('topLevelButtons', [{}])[0].get('toggleButtonRenderer', {})
                        likes = int(likes_data.get('defaultText', {}).get('simpleText', '0').replace(',', ''))
                    except (KeyError, IndexError):
                        pass

            views = parse_views(views)
            duration_seconds = parse_duration(duration)
            upload_date = parse_relative_time(published)

            six_months_ago = datetime.now() - timedelta(days=180)
            is_short_term = upload_date >= six_months_ago
            if upload_filter == 'last_6_months' and not is_short_term:
                continue
            elif upload_filter == 'before_6_months' and is_short_term:
                continue

            title_match = any(word in title.lower() for word in query.lower().split())
            description_match = any(word in description.lower() for word in query.lower().split())
            if not (title_match or description_match):
                continue

            transcript_match = check_transcript(video_id, query)
            if not transcript_match:
                continue

            positive_comments, negative_comments = get_comments_sentiment(video_id)
            sentiment_ratio = positive_comments / (negative_comments + 1)
            views_to_likes = likes / (views + 1)

            score = (views * 0.000001) + (likes * 0.0001) + (views_to_likes * 10) + (sentiment_ratio * 5)

            video_list.append({
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
                'upload_date': upload_date.strftime('%Y-%m-%d'),
                'is_short_term': is_short_term
            })

        video_list.sort(key=lambda x: x['score'], reverse=True)
        if sort_by == 'most_viewed':
            video_list.sort(key=lambda x: x['views'], reverse=True)
        elif sort_by == 'most_liked':
            video_list.sort(key=lambda x: x['likes'], reverse=True)

        short_term = [v for v in video_list if v['is_short_term']]
        long_term = [v for v in video_list if not v['is_short_term']]
        result = {'short': short_term[:5], 'long': long_term[:5], 'all': video_list}
        cache[cache_key] = result
        if len(cache) > 100:
            cache.pop(next(iter(cache)))

        return jsonify(result)
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
