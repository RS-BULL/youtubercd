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

def calculate_relevance_score(query, title, description, transcript):
    query_words = set(query.lower().split())
    score = 0

    # Title relevance (weight: 0.5)
    title_words = title.lower().split()
    title_matches = len(query_words.intersection(title_words))
    score += (title_matches / len(query_words)) * 0.5 if query_words else 0

    # Description relevance (weight: 0.3)
    description_words = description.lower().split()
    description_matches = len(query_words.intersection(description_words))
    score += (description_matches / len(query_words)) * 0.3 if query_words else 0

    # Transcript relevance (weight: 0.2)
    if transcript:
        transcript_words = transcript.lower().split()
        transcript_matches = len(query_words.intersection(transcript_words))
        score += (transcript_matches / len(query_words)) * 0.2 if query_words else 0

    return score

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
                    if len(comments) >= 50:
                        break
        except:
            pass

        analyzer = SentimentIntensityAnalyzer()
        positive = 0
        negative = 0
        for comment in comments[:50]:
            score = analyzer.polarity_scores(comment['text'])
            if score['compound'] >= 0.05:
                positive += 1 + (comment['likes'] * 0.1)
            elif score['compound'] <= -0.05:
                negative += 1 + (comment['likes'] * 0.1)
        
        total = positive + negative
        sentiment_ratio = positive / total if total > 0 else 0.5
        return sentiment_ratio
    except:
        return 0.5

@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    data = extract_yt_initial_data(response.text)
    if not data:
        return jsonify({'error': 'Unable to find video data'}), 500

    try:
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
                except (KeyError, IndexError):
                    pass

            views = parse_views(views)
            duration_seconds = parse_duration(duration)
            upload_date = parse_relative_time(published)

            six_months_ago = datetime.now() - timedelta(days=180)
            if upload_filter == 'last_6_months' and upload_date < six_months_ago:
                continue
            elif upload_filter == 'before_6_months' and upload_date >= six_months_ago:
                continue

            transcript = None
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                transcript = ' '.join(item['text'] for item in transcript_data)
            except Exception:
                pass

            # Calculate scores
            relevance_score = calculate_relevance_score(query, title, description, transcript)
            sentiment_score = get_comments_and_sentiment(video_id)
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
            if len(video_list) >= 20:
                break

        # Sort by final score initially
        video_list.sort(key=lambda x: x['score'], reverse=True)

        # Apply user-selected sorting
        if sort_by == 'most_viewed':
            video_list.sort(key=lambda x: x['views'], reverse=True)
        elif sort_by == 'most_liked':
            video_list.sort(key=lambda x: x['likes'], reverse=True)

        cache[cache_key] = video_list
        if len(cache) > 100:
            cache.pop(next(iter(cache)))

        return jsonify(video_list)
    except (KeyError, IndexError) as e:
        return jsonify({'error': f'Error parsing video data: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
