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
from graph_visualizer import process_tweet_data

load_dotenv(override=True) # Load environment variables from .env, overriding system vars

app = Flask(__name__)

# --- Configuration Loading ---
DEFAULT_CONFIG = {
    "enable_ai_analysis": True,
    "enable_graph_visualization": True
}

def load_app_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            # Validate and merge with defaults to ensure all keys are present
            return {**DEFAULT_CONFIG, **config} 
    except FileNotFoundError:
        app.logger.warning("config.json not found, using default configuration.")
        return DEFAULT_CONFIG
    except json.JSONDecodeError:
        app.logger.error("Error decoding config.json, using default configuration.")
        return DEFAULT_CONFIG

APP_CONFIG = load_app_config()
app.logger.info(f"App configuration loaded: AI Analysis Enabled: {APP_CONFIG['enable_ai_analysis']}, Graph Viz Enabled: {APP_CONFIG['enable_graph_visualization']}")
# --- End Configuration Loading ---

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
    cached_analysis_row = await asyncio.to_thread(db_manager.get_analysis_from_pg_cache, tweet_id)
    
    if cached_analysis_row and cached_analysis_row.get('analysis_results_json'):
        app.logger.info(f"Cache hit for tweet ID: {tweet_id}. Returning cached PG data.")
        username_from_cache = cached_analysis_row.get('tweet_author_username', 'user')
        view_url = f"/{username_from_cache}/status/{tweet_id}"
        response_data = {
            "status": "success_cached",
            "view_url": view_url,
            "data": cached_analysis_row['analysis_results_json'] 
        }
        app.logger.debug(f"Returning cached response: {type(response_data)} {response_data}")
        try:
            return jsonify(response_data)
        except Exception as e:
            app.logger.error(f"Error serializing cached response: {e}\nData: {response_data}")
            return jsonify({"error": f"Serialization error: {e}", "data": str(response_data)}), 500

    app.logger.info(f"Cache miss for tweet ID: {tweet_id}. Proceeding with full analysis.")
    tweet_author_username = extract_username_from_url(tweet_url)
    if not tweet_author_username:
        app.logger.warning(f"Could not extract username from URL: {tweet_url}. Using 'unknown_user'.")
        tweet_author_username = "unknown_user"

    try:
        all_tweets_data = await fetch_enriched_tweet_thread(tweet_url)
        app.logger.info(f"Fetched {len(all_tweets_data) if isinstance(all_tweets_data, list) else '0 or error'} items from fetch_enriched_tweet_thread.")

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
        app.logger.info(f"After splitting: main_post_data is {'set' if main_post_data else 'None'}, {len(replies_data)} items in replies_data.")

        # Pass the supabase_client from tweet_fetcher module to fetch_quote_tweets
        quote_tweets_data = await fetch_quote_tweets(tweet_fetcher.supabase_client, tweet_url)
        app.logger.info(f"Fetched {len(quote_tweets_data) if isinstance(quote_tweets_data, list) else '0 or error'} raw quote tweets.")
        processed_quote_tweets = []
        if isinstance(quote_tweets_data, list):
            for qt in quote_tweets_data:
                qt['tweet_type'] = 'quote_tweet'
                processed_quote_tweets.append(qt)
        app.logger.info(f"{len(processed_quote_tweets)} processed quote tweets.")
        
        # Combine all tweets for LLM analysis and graph generation
        # Ensure main_post_data is not None before adding to the list
        all_tweets_for_processing = []
        if main_post_data:
            all_tweets_for_processing.append(main_post_data)
        all_tweets_for_processing.extend(replies_data)
        all_tweets_for_processing.extend(processed_quote_tweets)
        app.logger.info(f"Total tweets for graph processing: {len(all_tweets_for_processing)}.")
        
        # Ensure no duplicates if main_post_data could somehow also be in replies_data (shouldn't happen with current logic but good for robustness)
        # This step might be overly cautious if the split is guaranteed clean
        # temp_ids = set()
        # unique_tweets_for_processing = []
        # for tweet in all_tweets_for_processing:
        #     if tweet['id'] not in temp_ids:
        #         unique_tweets_for_processing.append(tweet)
        #         temp_ids.add(tweet['id'])
        # all_tweets_for_processing = unique_tweets_for_processing

        # LLM analysis uses main_post_data and (replies_data + processed_quote_tweets)
        all_secondary_tweets = replies_data + processed_quote_tweets # This is correct for analyze_tweets input structure
        app.logger.info(f"Total secondary tweets for LLM analysis: {len(all_secondary_tweets)}.")
        
        analysis_results = {}
        # Populate base main_post details regardless of AI analysis setting
        if main_post_data:
            analysis_results['main_post_id'] = main_post_data.get('id')
            analysis_results['main_post_text'] = main_post_data.get('text')
            analysis_results['main_post_author_handle'] = main_post_data.get('author_handle')
            analysis_results['main_post_author_display_name'] = main_post_data.get('author_display_name')
            analysis_results['main_post_likes'] = main_post_data.get('like_count')
            analysis_results['main_post_timestamp'] = main_post_data.get('timestamp')
            analysis_results['main_post_avatar_url'] = main_post_data.get('avatar_url')
            # Add any other essential main_post fields that frontend expects by default

        if APP_CONFIG.get("enable_ai_analysis", True):
            app.logger.info("AI Analysis is ENABLED. Proceeding with LLM analysis.")
            llm_outputs = analyze_tweets(main_post_data, all_secondary_tweets)
            if isinstance(llm_outputs, dict) and 'error' in llm_outputs:
                return jsonify({"error": "Error during LLM analysis.", "details": llm_outputs['error']}), 500
            analysis_results.update(llm_outputs) # Merge LLM results
        else:
            app.logger.info("AI Analysis is DISABLED. Skipping LLM analysis.")
            # Populate placeholders if AI is disabled, to prevent frontend errors if it expects these keys
            analysis_results['overall_summary'] = "AI analysis disabled."
            analysis_results['cluster_details'] = {}
            # Add llm_classification to each tweet in all_tweets_for_processing if needed by graph or other parts
            for tweet in all_tweets_for_processing:
                tweet['llm_classification'] = {"status": "AI analysis disabled"}

        # Generate graph visualization using the combined list of all tweets
        if APP_CONFIG.get("enable_graph_visualization", True):
            app.logger.info("Graph Visualization is ENABLED. Processing graph data.")
            graph_data_for_frontend = process_tweet_data(all_tweets_for_processing) 
            analysis_results['graph_metrics'] = graph_data_for_frontend.get('graph_metrics')
            analysis_results['d3_graph_data'] = graph_data_for_frontend.get('d3_graph_data')
        else:
            app.logger.info("Graph Visualization is DISABLED. Skipping graph processing.")
            analysis_results['graph_metrics'] = {"status": "Graph visualization disabled"} 
            analysis_results['d3_graph_data'] = {"status": "Graph visualization disabled", "nodes": [], "links": []} # Provide empty structure
        
        if tweet_id and tweet_author_username:
            # Use asyncio.to_thread for the synchronous save operation
            await asyncio.to_thread(
                db_manager.save_analysis_to_pg_cache,
                tweet_id,
                tweet_author_username,
                tweet_url,
                analysis_results # Save the entire updated analysis_results
            )
        
        view_url = f"/{tweet_author_username}/status/{tweet_id}"
        app.logger.info(f"LLM analysis completed. View at: {view_url}")
        response_data = {
            "status": "success_analyzed",
            "view_url": view_url,
            "data": analysis_results
        }
        app.logger.debug(f"Returning analysis response: {type(response_data)} {response_data}")
        try:
            return jsonify(response_data)
        except Exception as e:
            app.logger.error(f"Error serializing analysis response: {e}\nData: {response_data}")
            return jsonify({"error": f"Serialization error: {e}", "data": str(response_data)}), 500

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