import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
import json
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re

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
        if 'ytInitialData' in str(script):
            json_str = script.string.split('ytInitialData = ')[1].split(';</script>')[0]
            return json.loads(json_str)
    return None

# Helper function to parse views
def parse_views(view_text):
    view_text = view_text.replace(',', '').replace(' views', '')
    if 'K' in view_text:
        return int(float(view_text.replace('K', '')) * 1000)
    elif 'M' in view_text:
        return int(float(view_text.replace('M', '')) * 1000000)
    return int(view_text)

# Helper function to parse duration
def parse_duration(duration_text):
    # Example: "5:30" or "1:23:45"
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
        soup = BeautifulSoup(response.text, 'html.parser')
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

# Search endpoint
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    upload_filter = request.args.get('uploadDate', 'all')
    sort_by = request.args.get('sortBy', 'most_viewed')

    # Check cache
    cache_key = f"{query}_{upload_filter}_{sort_by}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    # Search YouTube
    search_url = f"https://www.youtube.com/results?search_query={query}"
    response = requests.get(search_url, headers=headers)
    yt_data = extract_yt_initial_data(response.text)

    videos = []
    try:
        video_list = yt_data['contents']['twoColumnBrowseResultsRenderer']['tabs'][1]['tabRenderer']['content']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
        for item in video_list[:200]:  # Scan up to 200 videos
            if 'videoRenderer' in item:
                video = item['videoRenderer']
                video_id = video['videoId']
                title = video['title']['runs'][0]['text']
                views = parse_views(video['viewCountText']['simpleText'])
                duration = parse_duration(video['lengthText']['simpleText'])
                likes = int(video.get('likeCount', {'simpleText': '0'})['simpleText'].replace(',', '')) if 'likeCount' in video else 0
                upload_date_str = video['publishedTimeText']['simpleText']
                
                # Parse upload date
                upload_date = datetime.now()
                if 'day' in upload_date_str:
                    days = int(re.search(r'\d+', upload_date_str).group())
                    upload_date = upload_date - timedelta(days=days)
                elif 'month' in upload_date_str:
                    months = int(re.search(r'\d+', upload_date_str).group())
                    upload_date = upload_date - timedelta(days=months * 30)
                elif 'year' in upload_date_str:
                    years = int(re.search(r'\d+', upload_date_str).group())
                    upload_date = upload_date - timedelta(days=years * 365)

                # Apply upload date filter
                six_months_ago = datetime.now() - timedelta(days=180)
                if upload_filter == 'last_6_months' and upload_date < six_months_ago:
                    continue
                elif upload_filter == 'before_6_months' and upload_date >= six_months_ago:
                    continue

                # Get transcript to match content with title/description
                transcript = ''
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                    transcript = ' '.join([t['text'] for t in transcript_list])
                except:
                    pass

                # Check if title matches content
                title_match = query.lower() in title.lower() or (transcript and query.lower() in transcript.lower())

                if title_match:
                    # Get sentiment from comments
                    sentiment_ratio = get_comments_and_sentiment(video_id)
                    
                    # Calculate views-to-likes ratio
                    views_to_likes = likes / views if views > 0 else 0
                    
                    # Score the video
                    score = (sentiment_ratio * 0.4) + (views_to_likes * 0.3) + (views * 0.000001 * 0.3)
                    
                    videos.append({
                        'id': video_id,
                        'title': title,
                        'views': views,
                        'duration': duration,  # In seconds
                        'likes': likes,
                        'upload_date': upload_date.strftime('%Y-%m-%d'),
                        'score': score
                    })
    except:
        pass

    # Sort videos
    if sort_by == 'most_viewed':
        videos.sort(key=lambda x: x['views'], reverse=True)
    elif sort_by == 'most_liked':
        videos.sort(key=lambda x: x['likes'], reverse=True)

    # Take top 50 videos after sorting
    videos = videos[:50]

    # Cache the result
    cache[cache_key] = videos
    if len(cache) > 100:  # Limit cache size
        cache.pop(next(iter(cache)))

    return jsonify(videos)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
