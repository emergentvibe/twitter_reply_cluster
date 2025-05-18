from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import asyncio # Added for running async functions
from urllib.parse import urlparse # For parsing URL to get username
import json # For serializing data to pass to template

import tweet_fetcher # Import the module itself
from tweet_fetcher import fetch_enriched_tweet_thread, extract_tweet_id_from_url, fetch_quote_tweets
from llm_analyzer_suite import analyze_tweets # Import the analyzer function
import db_manager # For PostgreSQL caching

load_dotenv(override=True) # Load environment variables from .env, overriding system vars

app = Flask(__name__)

# Initialize the database table on startup
db_manager.create_cache_table_if_not_exists()

# API keys (loaded from .env) - example, actual use will be in respective modules
# ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# OPEN_BIRDSITE_DB_TOKEN = os.getenv("OPEN_BIRDSITE_DB_TOKEN")

# Example: Check if critical env vars are loaded for other modules, just for app's awareness (optional)
# if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("OPEN_BIRDSITE_DB_TOKEN"):
#     app.logger.warning("One or more API keys may not be loaded. Ensure .env is correct and accessible.")

# Helper to extract username from tweet URL
def extract_username_from_url(tweet_url: str) -> str | None:
    try:
        path_parts = urlparse(tweet_url).path.strip('/').split('/')
        # Expected structure: username/status/tweet_id
        if len(path_parts) >= 3 and path_parts[-2].lower() == 'status':
            return path_parts[-3]
        # Expected structure for profiles if accidentally passed: username
        # Might need more robust parsing if other URL types are common
    except Exception as e:
        app.logger.error(f"Error parsing username from URL {tweet_url}: {e}")
    return None

@app.route('/')
def index():
    # This route now might also serve cached results if index.html is adapted,
    # but for now, it's the main entry.
    # The new route /@username/status/id will handle specific cached views.
    return render_template('index.html', analysis_data_json=None)

@app.route('/api/analyze_url', methods=['POST'])
async def analyze_url_route():
    data = request.get_json()
    if not data or 'tweet_url' not in data:
        return jsonify({"error": "Missing tweet_url in request"}), 400

    tweet_url = data['tweet_url']
    if not tweet_url:
        return jsonify({"error": "tweet_url cannot be empty"}), 400

    tweet_id = extract_tweet_id_from_url(tweet_url)
    if not tweet_id:
        return jsonify({"error": "Invalid tweet URL or could not extract tweet ID."}), 400

    # Attempt to fetch from PG cache first
    # Use asyncio.to_thread to run the synchronous DB call in a separate thread
    cached_analysis_row = await asyncio.to_thread(db_manager.get_analysis_from_pg_cache, tweet_id)
    
    if cached_analysis_row and cached_analysis_row.get('analysis_results_json'):
        app.logger.info(f"Cache hit for tweet ID: {tweet_id}. Returning cached PG data.")
        username_from_cache = cached_analysis_row.get('tweet_author_username', 'user')
        view_url = f"/{username_from_cache}/status/{tweet_id}"
        # The analysis_results_json from PG should already be a dict due to DictCursor and JSONB handling
        return jsonify({
            "status": "success_cached",
            "view_url": view_url,
            "data": cached_analysis_row['analysis_results_json'] 
        })

    app.logger.info(f"Cache miss for tweet ID: {tweet_id}. Proceeding with full analysis.")
    tweet_author_username = extract_username_from_url(tweet_url)
    if not tweet_author_username:
        # Fallback or error if username can't be parsed, needed for view_url
        app.logger.warning(f"Could not extract username from URL: {tweet_url}. Using 'unknown_user'.")
        tweet_author_username = "unknown_user"

    try:
        all_tweets_data = await fetch_enriched_tweet_thread(tweet_url)

        if isinstance(all_tweets_data, dict) and 'error' in all_tweets_data:
            status_code = all_tweets_data.get("status_code", 500)
            return jsonify(all_tweets_data), status_code

        if not isinstance(all_tweets_data, list):
            app.logger.error(f"Unexpected data from fetch_enriched_tweet_thread: {type(all_tweets_data)}.")
            return jsonify({"error": "Failed to fetch tweet data or unexpected format received."}), 500
        
        if not all_tweets_data:
            return jsonify({"error": "No tweets found for the given URL. It might be invalid, private, or deleted."}), 404

        main_post_data = None
        replies_data = []

        for tweet_item in all_tweets_data:
            if tweet_item.get('id') == tweet_id:
                main_post_data = tweet_item
            else:
                replies_data.append(tweet_item)
        
        if not main_post_data: # Fallback if ID matching fails, use first tweet
            if all_tweets_data:
                main_post_data = all_tweets_data[0]
                replies_data = all_tweets_data[1:]
            else: # Should be caught by 'if not all_tweets_data' earlier
                return jsonify({"error": "Could not identify the main post from the fetched data."}), 404
        
        if main_post_data:
            main_post_data['tweet_type'] = 'main_post'
        for reply in replies_data:
            reply['tweet_type'] = 'reply'

        # Pass the supabase_client from tweet_fetcher module to fetch_quote_tweets
        quote_tweets_data = await fetch_quote_tweets(tweet_fetcher.supabase_client, tweet_url)
        processed_quote_tweets = []
        if isinstance(quote_tweets_data, list):
            for qt in quote_tweets_data:
                qt['tweet_type'] = 'quote_tweet'
                processed_quote_tweets.append(qt)
        
        all_secondary_tweets = replies_data + processed_quote_tweets
        analysis_results = analyze_tweets(main_post_data, all_secondary_tweets)
        
        if isinstance(analysis_results, dict) and 'error' in analysis_results:
            return jsonify({"error": "Error during LLM analysis.", "details": analysis_results['error']}), 500
        
        if tweet_id and tweet_author_username:
            # Use asyncio.to_thread for the synchronous save operation
            await asyncio.to_thread(
                db_manager.save_analysis_to_pg_cache,
                tweet_id,
                tweet_author_username,
                tweet_url,
                analysis_results
            )
        
        view_url = f"/{tweet_author_username}/status/{tweet_id}"
        app.logger.info(f"LLM analysis completed. View at: {view_url}")
        return jsonify({
            "status": "success_analyzed",
            "view_url": view_url,
            "data": analysis_results
        })

    except Exception as e:
        app.logger.error(f"Unhandled exception in /api/analyze_url for URL {tweet_url}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/<string:username>/status/<string:tweet_id_str>')
async def view_cached_analysis(username: str, tweet_id_str: str):
    app.logger.info(f"Attempting to view cached PG analysis for user: {username}, tweet_id: {tweet_id_str}")
    
    # The username from the URL is mostly for human-readable URLs, tweet_id_str is the key
    cached_data_row = await asyncio.to_thread(db_manager.get_analysis_from_pg_cache, tweet_id_str)
    
    if cached_data_row and cached_data_row.get('analysis_results_json'):
        app.logger.info(f"Found cached PG analysis for tweet_id: {tweet_id_str}")
        # Pass the analysis_results_json part, which is the actual analysis data structure
        return render_template('index.html', analysis_data_json=json.dumps(cached_data_row['analysis_results_json']))
    else:
        app.logger.warning(f"No cached PG analysis found for tweet_id: {tweet_id_str}. User: {username}")
        # Optionally, you could redirect to the homepage with a message,
        # or offer to analyze it if it's a valid tweet URL pattern.
        # For now, return a simple 404 page or message.
        return render_template('analysis_not_found.html', username=username, tweet_id=tweet_id_str), 404

if __name__ == '__main__':
    # Ensure the app runs with the appropriate host and port for Gunicorn
    # Gunicorn will specify host/port, so app.run() is mainly for local dev
    port = int(os.environ.get("PORT", 8080)) # Default to 8080 if PORT not set
    app.run(debug=True, host='0.0.0.0', port=port) 