from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

app = Flask(__name__)
CORS(app)

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

# Helper function to get comments and analyze sentiment
def get_comments_and_sentiment(video_id):
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, headers=headers)
        yt_data = extract_yt_initial_data(response.text)
        
        # Extract comments (limited to 100-150)
        comments = []
        try:
            comment_section = yt_data['contents']['twoColumnWatchNextResults']['results']['results']['contents']
            for item in comment_section:
                if 'commentThreadRenderer' in str(item):
                    comment = item['commentThreadRenderer']['comment']['commentRenderer']
                    comment_text = comment['contentText']['runs'][0]['text']
                    likes = int(comment.get('voteCount', {'simpleText': '0'})['simpleText'].replace(',', ''))
                    comments.append({'text': comment_text, 'likes': likes})
                    if len(comments) >= 150:
                        break
        except:
            pass

        # Sentiment analysis
        analyzer = SentimentIntensityAnalyzer()
        positive = 0
        negative = 0
        for comment in comments[:100]:  # Analyze first 100 comments
            score = analyzer.polarity_scores(comment['text'])
            if score['compound'] >= 0.05:
                positive += 1 + (comment['likes'] * 0.1)  # Weight by likes
            elif score['compound'] <= -0.05:
                negative += 1 + (comment['likes'] * 0.1)
        
        total = positive + negative
        sentiment_ratio = positive / total if total > 0 else 0
        return sentiment_ratio
    except:
        return 0.5  # Neutral if comments can't be fetched

# Search videos via web scraping, including details and transcripts
@app.route('/search', methods=['GET'])
def search_videos():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    # Check cache
    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(url, headers=headers)
    data = extract_yt_initial_data(response.text)
    if not data:
        return jsonify({'error': 'Unable to find video data'}), 500

    try:
        videos = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
        video_list = []
        for video in videos[:200]:  # Scan up to 200 videos
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
                views = '0'
                likes = 0
                if video_data:
                    try:
                        video_info = video_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][0]['videoPrimaryInfoRenderer']
                        views = video_info['viewCount']['videoViewCountRenderer']['viewCount']['simpleText']
                        likes = int(video_info.get('videoActions', {}).get('menuRenderer', {}).get('topLevelButtons', [{}])[0].get('toggleButtonRenderer', {}).get('defaultText', {}).get('simpleText', '0').replace(',', ''))
                    except (KeyError, IndexError):
                        pass

                # Parse views and duration
                views = parse_views(views)
                duration_seconds = parse_duration(duration)

                # Parse upload date
                upload_date = parse_relative_time(published)

                # Apply upload date filter
                six_months_ago = datetime.now() - timedelta(days=180)
                if upload_filter == 'last_6_months' and upload_date < six_months_ago:
                    continue
                elif upload_filter == 'before_6_months' and upload_date >= six_months_ago:
                    continue

                # Fetch transcript
                transcript = None
                try:
                    transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                    transcript = ' '.join(item['text'] for item in transcript_data)
                except Exception:
                    pass

                # Check if title/description matches content
                title_match = query.lower() in title.lower() or query.lower() in description.lower()
                content_match = transcript and query.lower() in transcript.lower()
                if not (title_match or content_match):
                    continue

                # Get sentiment from comments
                sentiment_ratio = get_comments_and_sentiment(video_id)

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
                    'transcript': transcript,
                    'score': score,
                    'upload_date': upload_date.strftime('%Y-%m-%d')
                })
            if len(video_list) >= 50:  # Limit to 50 videos to improve performance
                break

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
    except KeyError:
        return jsonify({'error': 'Error parsing video data'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
