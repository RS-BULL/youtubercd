from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
import re

app = Flask(__name__)
CORS(app)

# Headers to mimic a browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Helper function to extract ytInitialData JSON from YouTube pages
def extract_yt_initial_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    for script in scripts:
        if 'ytInitialData' in script.text:
            json_text = script.text.split(' = ', 1)[1]
            json_data = json_text.rsplit(';', 1)[0]
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

# Search videos via web scraping, including details and transcripts
@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'No search query provided'}), 400

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    data = extract_yt_initial_data(response.text)
    if not data:
        return jsonify({'error': 'Unable to find video data'}), 500

    try:
        videos = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
        video_list = []
        for video in videos:
            if 'videoRenderer' in video:
                video_data = video['videoRenderer']
                video_id = video_data['videoId']
                title = video_data['title']['runs'][0]['text']
                thumbnail = video_data['thumbnail']['thumbnails'][0]['url']
                duration = video_data.get('lengthText', {}).get('simpleText', '0:00')
                channel = video_data['ownerText']['runs'][0]['text']
                published = video_data.get('publishedTimeText', {}).get('simpleText', 'Unknown')
                description = video_data.get('detailedMetadataSnippets', [{}])[0].get('snippetText', {}).get('runs', [{}])[0].get('text', '')

                # Fetch additional details
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                video_response = requests.get(video_url, headers=headers)
                video_data = extract_yt_initial_data(video_response.text)
                views = 'Unknown'
                if video_data:
                    try:
                        video_info = video_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                        views = video_info['viewCount']['videoViewCountRenderer']['viewCount']['simpleText']
                    except (KeyError, IndexError):
                        pass

                # Fetch transcript
                transcript = None
                try:
                    transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                    transcript = ' '.join(item['text'] for item in transcript_data)
                except Exception:
                    pass

                video_list.append({
                    'id': video_id,
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration,
                    'channel': channel,
                    'published': published,
                    'description': description,
                    'views': views,
                    'transcript': transcript
                })
            if len(video_list) >= 50:  # Limit to 50 videos to improve performance
                break
        return jsonify(video_list)
    except KeyError as e:
        return jsonify({'error': f'Error parsing video data: {e}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
