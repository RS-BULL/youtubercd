from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
import re
import os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

app = Flask(__name__)

# Configure CORS
cors_origins = os.getenv('FLASK_CORS_ORIGINS', '*')
CORS(app, resources={r"/*": {"origins": cors_origins}})

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

cache = {}

@app.route('/')
def home():
    return jsonify({"message": "YouTubeRCD API is running!"})

def extract_yt_initial_data(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        if 'ytInitialData' in script.text:
            start = script.text.find('{')
            end = script.text.rfind('}') + 1
            return json.loads(script.text[start:end])
    return None

def parse_relative_time(time_str):
    now = datetime.now()
    match = re.match(r'(\d+)\s*(year|month|week|day|hour|minute|second)s?\s*ago', time_str)
    if not match:
        return now
    value, unit = int(match.group(1)), match.group(2)
    deltas = {'year': 365, 'month': 30, 'week': 7, 'day': 1, 'hour': 1/24, 'minute': 1/1440, 'second': 1/86400}
    return now - timedelta(days=value * deltas[unit])

@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch YouTube data"}), 500

    data = extract_yt_initial_data(response.text)
    if not data:
        return jsonify({'error': 'Unable to find video data'}), 500

    videos = []
    try:
        contents = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
        for item in contents:
            if 'itemSectionRenderer' in item:
                for video in item['itemSectionRenderer']['contents']:
                    if 'videoRenderer' in video:
                        video_data = video['videoRenderer']
                        video_id = video_data.get('videoId', '')
                        title = video_data.get('title', {}).get('runs', [{}])[0].get('text', 'Unknown')
                        thumbnail = video_data.get('thumbnail', {}).get('thumbnails', [{}])[0].get('url', '')
                        duration = video_data.get('lengthText', {}).get('simpleText', '0:00')
                        channel = video_data.get('ownerText', {}).get('runs', [{}])[0].get('text', 'Unknown')
                        published = video_data.get('publishedTimeText', {}).get('simpleText', 'Unknown')
                        
                        videos.append({
                            'id': video_id,
                            'title': title,
                            'thumbnail': thumbnail,
                            'duration': duration,
                            'channel': channel,
                            'published': published
                        })
    except Exception as e:
        return jsonify({'error': f'Error parsing video data: {str(e)}'}), 500

    return jsonify({'results': videos})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
