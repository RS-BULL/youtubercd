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
CORS(app, resources={r"/search": {"origins": cors_origins}})

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

cache = {}

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

def get_transcript(video_id):
    try:
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        total_duration = sum(item['duration'] for item in transcript_data)
        target_duration = total_duration * 0.25  # 25% of transcript
        current_duration = 0
        transcript_text = ''
        for item in transcript_data:
            transcript_text += item['text'] + ' '
            current_duration += item['duration']
            if current_duration >= target_duration:
                break
        return transcript_text.strip()
    except Exception:
        return None

def get_comments_and_sentiment(video_id):
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers=headers)
        yt_data = extract_yt_initial_data(response.text)
        comments = []
        try:
            comment_section = yt_data['contents']['twoColumnWatchNextResults']['results']['results']['contents']
            for item in comment_section:
                if 'commentThreadRenderer' in str(item):
                    comment = item['commentThreadRenderer']['comment']['commentRenderer']
                    comment_text = comment['contentText']['runs'][0]['text']
                    likes = int(comment.get('voteCount', {'simpleText': '0'})['simpleText'].replace(',', ''))
                    comments.append({'text': comment_text, 'likes': likes})
                    if len(comments) >= 25:
                        break
        except:
            pass

        analyzer = SentimentIntensityAnalyzer()
        positive = 0
        negative = 0
        for comment in comments[:25]:
            score = analyzer.polarity_scores(comment['text'])
            if score['compound'] >= 0.05:
                positive += 1 + (comment['likes'] * 0.1)
            elif score['compound'] <= -0.05:
                negative += 1 + (comment['likes'] * 0.1)
        total = positive + negative
        return positive / total if total > 0 else 0.5
    except:
        return 0.5

def calculate_relevance_score(query, title, description, transcript):
    query_words = set(query.lower().split())
    score = 0
    for text in [title, description, transcript]:
        if text:
            words = text.lower().split()
            matches = len(query_words.intersection(words))
            score += (matches / len(query_words)) * (0.5 if text == title else 0.3 if text == description else 0.2)
    return score

@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')  # Default: no filter
    sort_by = request.args.get('sortBy', 'relevance')     # Default: relevance

    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    data = extract_yt_initial_data(response.text)
    if not data:
        return jsonify({'error': 'Unable to find video data'}), 500

    try:
        contents = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
        videos = next((item['itemSectionRenderer']['contents'] for item in contents if 'itemSectionRenderer' in item), [])
        video_list = []

        for video in videos[:100]:  # Scan up to 100 videos
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
            video_response = requests.get(video_url, headers=headers)
            video_data = extract_yt_initial_data(video_response.text)
            views = '0'
            likes = 0
            if video_data:
                try:
                    video_info = video_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                    views = video_info.get('viewCount', {}).get('videoViewCountRenderer', {}).get('viewCount', {}).get('simpleText', '0 views')
                    likes_data = video_info.get('videoActions', {}).get('menuRenderer', {}).get('topLevelButtons', [{}])[0].get('toggleButtonRenderer', {})
                    likes = int(likes_data.get('defaultText', {}).get('simpleText', '0').replace(',', '')) if likes_data else 0
                except:
                    pass

            views = parse_views(views)
            duration_seconds = parse_duration(duration)
            upload_date = parse_relative_time(published)

            # Apply upload filter only if selected
            six_months_ago = datetime.now() - timedelta(days=180)
            if upload_filter == 'last_6_months' and upload_date < six_months_ago:
                continue
            elif upload_filter == 'before_6_months' and upload_date >= six_months_ago:
                continue

            transcript = get_transcript(video_id)
            sentiment_score = get_comments_and_sentiment(video_id)
            relevance_score = calculate_relevance_score(query, title, description, transcript)
            views_to_likes = likes / views if views > 0 else 0

            # Final score: 40% relevance, 30% sentiment, 20% views-to-likes, 10% views
            final_score = (relevance_score * 0.4) + (sentiment_score * 0.3) + (views_to_likes * 0.2) + (views * 0.000001 * 0.1)

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
                'upload_date': upload_date.strftime('%Y-%m-%d'),
                'score': final_score
            })

        # Sort by score by default
        video_list.sort(key=lambda x: x['score'], reverse=True)

        # Apply user-selected sorting
        if sort_by == 'most_viewed':
            video_list.sort(key=lambda x: x['views'], reverse=True)
        elif sort_by == 'most_liked':
            video_list.sort(key=lambda x: x['likes'], reverse=True)

        # Split into short and long tabs
        short_videos = [v for v in video_list if v['duration'] <= 600]  # <10 min
        long_videos = [v for v in video_list if v['duration'] > 600]   # >10 min

        result = {'short': short_videos, 'long': long_videos}
        cache[cache_key] = result
        if len(cache) > 100:
            cache.pop(next(iter(cache)))

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Error parsing video data: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
