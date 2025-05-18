from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import asyncio # Added for running async functions

import tweet_fetcher # Import the module itself
from tweet_fetcher import fetch_enriched_tweet_thread, extract_tweet_id_from_url, fetch_quote_tweets # Keep specific imports
from llm_analyzer_suite import analyze_tweets # Import the analyzer function

load_dotenv(override=True) # Load environment variables from .env, overriding system vars

app = Flask(__name__)

# API keys (loaded from .env) - example, actual use will be in respective modules
# ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# OPEN_BIRDSITE_DB_TOKEN = os.getenv("OPEN_BIRDSITE_DB_TOKEN")

# Example: Check if critical env vars are loaded for other modules, just for app's awareness (optional)
# if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("OPEN_BIRDSITE_DB_TOKEN"):
#     app.logger.warning("One or more API keys may not be loaded. Ensure .env is correct and accessible.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze_url', methods=['POST'])
async def analyze_url_route(): 
    data = request.get_json()
    if not data or 'tweet_url' not in data:
        return jsonify({"error": "Missing tweet_url in request"}), 400

    tweet_url = data['tweet_url']
    if not tweet_url:
        return jsonify({"error": "tweet_url cannot be empty"}), 400

    initial_tweet_id = extract_tweet_id_from_url(tweet_url)
    if not initial_tweet_id:
        return jsonify({"error": "Invalid tweet URL or could not extract tweet ID."}), 400

    try:
        # Directly await async functions since the route is async
        all_tweets_data = await fetch_enriched_tweet_thread(tweet_url)

        if isinstance(all_tweets_data, dict) and 'error' in all_tweets_data:
            status_code = all_tweets_data.get("status_code", 500)
            return jsonify(all_tweets_data), status_code

        if not isinstance(all_tweets_data, list):
            app.logger.error(f"Unexpected data format from fetch_enriched_tweet_thread: {type(all_tweets_data)}. Expected list or error dict.")
            return jsonify({"error": "Failed to fetch tweet data or unexpected format received."}), 500
        
        if not all_tweets_data: 
            return jsonify({"error": "No tweets found for the given URL. It might be invalid, private, or deleted."}), 404

        main_post_data = None
        replies_data = []

        for tweet in all_tweets_data:
            if tweet.get('id') == initial_tweet_id:
                main_post_data = tweet
            else:
                replies_data.append(tweet)
        
        if not main_post_data:
            found_by_id = False
            for tweet in all_tweets_data:
                if tweet.get('id') == initial_tweet_id:
                    main_post_data = tweet
                    replies_data = [r for r in all_tweets_data if r.get('id') != initial_tweet_id]
                    found_by_id = True
                    break
            
            if not found_by_id:
                app.logger.warning(f"Tweet with ID {initial_tweet_id} not found in fetched data. Using first fetched tweet as main post.")
                if all_tweets_data: 
                    main_post_data = all_tweets_data[0]
                    replies_data = all_tweets_data[1:]

        if not main_post_data:
             app.logger.error(f"Could not identify a main post for URL {tweet_url} / ID {initial_tweet_id} despite fetching data. Data: {all_tweets_data[:1]}")
             return jsonify({"error": "Could not identify the main post from the fetched data."}), 404

        # Add type to main_post_data and replies_data
        if main_post_data:
            main_post_data['tweet_type'] = 'main_post'
        for reply in replies_data:
            reply['tweet_type'] = 'reply'

        # Fetch quote tweets
        # Ensure tweet_fetcher.supabase_client is available or pass it explicitly if fetch_quote_tweets requires it.
        # Assuming fetch_quote_tweets has been updated to not require client if it uses its global one.
        quote_tweets_data = await fetch_quote_tweets(tweet_fetcher.supabase_client, tweet_url) # Pass client explicitly
        
        processed_quote_tweets = []
        if isinstance(quote_tweets_data, list):
            for qt in quote_tweets_data:
                qt['tweet_type'] = 'quote_tweet' # Mark as quote_tweet
                processed_quote_tweets.append(qt)
            app.logger.info(f"Fetched {len(processed_quote_tweets)} quote tweets.")
        elif isinstance(quote_tweets_data, dict) and "error" in quote_tweets_data:
            app.logger.error(f"Error fetching quote tweets: {quote_tweets_data['error']}")
            # Decide if this should be a fatal error or if we proceed without QTs
        else:
            app.logger.info("No quote tweets found or unexpected format returned.")

        # Combine replies and quote tweets into a single list for analysis
        all_secondary_tweets = replies_data + processed_quote_tweets
        # Optional: sort all_secondary_tweets by timestamp if preferred for processing order
        # all_secondary_tweets.sort(key=lambda x: x.get('timestamp', ''))

        if not all_secondary_tweets:
            app.logger.info("No replies or quote tweets found to analyze. Fallback: creating a response with just the main post and an empty analysis.")
            # Fallback: create a response with just the main post and an empty analysis
            # Or, let analyze_tweets handle empty list for replies_data if it's robust to that.
            # For now, we'll let analyze_tweets handle it, assuming it can produce a default if no replies.

        # Call the LLM analysis function with the main post and combined secondary tweets
        app.logger.info(f"Starting LLM analysis for {len(all_secondary_tweets)} tweets")
        # analyze_tweets is synchronous as it uses a synchronous httpx client via anthropic library
        analysis_results = analyze_tweets(main_post_data, all_secondary_tweets) # Removed await
        
        if isinstance(analysis_results, dict) and 'error' in analysis_results:
            app.logger.error(f"Error from LLM analysis: {analysis_results['error']}")
            # You might want a different status code for LLM errors, e.g., 502 Bad Gateway if it's an API issue
            return jsonify({"error": "Error during LLM analysis.", "details": analysis_results['error']}), 500 
        
        app.logger.info("LLM analysis completed successfully.")
        return jsonify(analysis_results)

    except Exception as e:
        app.logger.error(f"Unhandled exception in /api/analyze_url for URL {tweet_url}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    app.run(debug=True) 