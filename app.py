from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import os
import asyncio # Added for running async functions
from urllib.parse import urlparse # For parsing URL to get username
import json # For serializing data to pass to template

import tweet_fetcher # Import the module itself
from tweet_fetcher import fetch_enriched_tweet_thread, extract_tweet_id_from_url, fetch_quote_tweets, fetch_direct_replies_enriched
from llm_analyzer_suite import analyze_tweets # Import the analyzer function
import db_manager # For PostgreSQL caching
from graph_visualizer import process_tweet_data

load_dotenv(override=True) # Load environment variables from .env, overriding system vars

app = Flask(__name__)

# --- Configuration Loading ---
DEFAULT_CONFIG = {
    "enable_ai_analysis": False,
    "enable_graph_visualization": True,
    "recursive_qt_max_depth": 2 # Default depth for recursive QT fetching
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
        app.logger.info(f"Total tweets for initial processing: {len(all_tweets_for_processing)}.")
        
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

        # Temporary list to hold tweets that have been processed by LLM or had placeholders added
        # This ensures that modifications made by analyze_tweets or the else block are passed to fetch_recursive_qt_data
        initial_tweets_for_recursion = []
        if main_post_data:
            initial_tweets_for_recursion.append(main_post_data)
        initial_tweets_for_recursion.extend(all_secondary_tweets)

        if APP_CONFIG.get("enable_ai_analysis", True):
            app.logger.info("AI Analysis is ENABLED. Proceeding with LLM analysis.")
            # analyze_tweets should ideally modify tweet dictionaries in-place or return new ones
            # that are then used. Assuming it modifies main_post_data and elements in all_secondary_tweets.
            llm_outputs = analyze_tweets(main_post_data, all_secondary_tweets)
            if isinstance(llm_outputs, dict) and 'error' in llm_outputs:
                return jsonify({"error": "Error during LLM analysis.", "details": llm_outputs['error']}), 500
            analysis_results.update(llm_outputs) # Merge LLM results
        else:
            app.logger.info("AI Analysis is DISABLED. Skipping LLM analysis.")
            analysis_results['overall_summary'] = "AI analysis disabled."
            analysis_results['cluster_details'] = {}
            # Add llm_classification to each tweet in initial_tweets_for_recursion if AI is disabled
            # This ensures these tweets carry this info into the recursive fetch
            for tweet in initial_tweets_for_recursion:
                tweet['llm_classification'] = {"status": "AI analysis disabled"}

        # Fetch recursive quote tweets using the (potentially LLM-processed) initial set
        max_qt_depth = APP_CONFIG.get("recursive_qt_max_depth", 2)
        app.logger.info(f"Starting recursive QT fetching with max_depth: {max_qt_depth}.")
        
        # The components main_post_data, replies_data, processed_quote_tweets might have been modified by LLM analysis (if enabled)
        # or the AI disabled block. Pass these modified versions.
        all_tweets_processed_recursively = await fetch_recursive_qt_data(
            initial_tweet_url=tweet_url,
            initial_tweet_id=tweet_id,
            initial_main_post_data=main_post_data, # This should be the (potentially modified) main_post_data
            initial_replies_data=replies_data,     # This should be the (potentially modified) replies_data
            initial_quote_tweets_data=processed_quote_tweets, # This should be the (potentially modified) processed_quote_tweets
            max_depth=max_qt_depth
        )
        app.logger.info(f"Recursive QT fetching completed. Total tweets after recursion: {len(all_tweets_processed_recursively)}")

        # --- BEGIN DIAGNOSTIC LOGGING for app.py analyze_url_route, right before graph processing ---
        # Updated to use all_tweets_processed_recursively
        app.logger.info(f"[DEBUG app.py analyze_url_route] BEFORE process_tweet_data. Total tweets in all_tweets_processed_recursively: {len(all_tweets_processed_recursively)}")
        if all_tweets_processed_recursively:
            app.logger.info("[DEBUG app.py analyze_url_route] First 3 (or fewer) tweets for graph (full dicts):")
            for i, tweet_graph_log in enumerate(all_tweets_processed_recursively[:3]):
                app.logger.info(f"  [DEBUG app.py graph_data {i}]: parent_tweet_id exists? {'parent_tweet_id' in tweet_graph_log}. Full dict: {tweet_graph_log}")
        # --- END DIAGNOSTIC LOGGING ---

        # Generate graph visualization using the *fully processed* list of all tweets
        if APP_CONFIG.get("enable_graph_visualization", True):
            app.logger.info("Graph Visualization is ENABLED. Processing graph data using all_tweets_processed_recursively.")
            
            # --- BEGIN TARGETED QT_LEVEL LOGGING ---
            app.logger.info("[DEBUG app.py QT_LEVEL CHECK] Checking qt_level for initial quote tweets in all_tweets_processed_recursively:")
            qt_level_1_found_count = 0
            for i, tweet_diag_qt in enumerate(all_tweets_processed_recursively):
                if tweet_diag_qt.get('tweet_type') == 'quote_tweet' and tweet_diag_qt.get('parent_tweet_id') == tweet_id:
                    app.logger.info(f"  [DEBUG app.py QT_LEVEL CHECK] Initial QT: id={tweet_diag_qt.get('id')}, qt_level={tweet_diag_qt.get('qt_level')}")
                    qt_level_1_found_count +=1
                    if qt_level_1_found_count >= 5: # Log up to 5 such QTs
                        break
            if qt_level_1_found_count == 0:
                 app.logger.info("  [DEBUG app.py QT_LEVEL CHECK] No initial QTs (children of main post) found in the list for detailed qt_level check.")
            # --- END TARGETED QT_LEVEL LOGGING ---

            # --- BEGIN DIAGNOSTIC LOGGING for app.py ---
            # Updated to use all_tweets_processed_recursively
            app.logger.info(f"[DEBUG app.py] Total tweets in all_tweets_processed_recursively: {len(all_tweets_processed_recursively)}")
            app.logger.info("[DEBUG app.py] First 5 tweets (or fewer) in all_tweets_processed_recursively:")
            for i, tweet_diag in enumerate(all_tweets_processed_recursively[:5]):
                app.logger.info(f"  [DEBUG app.py] Tweet {i}: id={tweet_diag.get('id')}, type={tweet_diag.get('tweet_type')}, parent_id={tweet_diag.get('parent_tweet_id')}, qt_level={tweet_diag.get('qt_level')}")
            
            tweets_with_parent = sum(1 for t in all_tweets_processed_recursively if t.get('parent_tweet_id'))
            tweets_without_parent = len(all_tweets_processed_recursively) - tweets_with_parent
            app.logger.info(f"[DEBUG app.py] Tweets with parent_tweet_id: {tweets_with_parent}")
            app.logger.info(f"[DEBUG app.py] Tweets without parent_tweet_id: {tweets_without_parent}")
            # --- END DIAGNOSTIC LOGGING for app.py ---

            graph_data_for_frontend = process_tweet_data(all_tweets_processed_recursively) 
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

async def fetch_recursive_qt_data(initial_tweet_url: str, initial_tweet_id: str, initial_main_post_data: dict, initial_replies_data: list, initial_quote_tweets_data: list, max_depth: int):
    all_tweets_collected = {} 
    processing_queue = [] 

    # Log received initial data
    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Entry. initial_tweet_id: {initial_tweet_id}, max_depth: {max_depth}")
    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Main post provided: {initial_main_post_data is not None}")
    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Initial replies count: {len(initial_replies_data)}")
    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Initial QTs count: {len(initial_quote_tweets_data)}")

    def add_tweet_to_collection(tweet_data, graph_link_parent_id=None, assigned_qt_level=-1):
        if not tweet_data or not isinstance(tweet_data, dict):
            app.logger.warning("[add_tweet_to_collection] Received invalid tweet_data, skipping.")
            return None
        
        current_id = tweet_data.get('id')
        if not current_id:
            app.logger.warning(f"[add_tweet_to_collection] Tweet data missing 'id', skipping: {tweet_data.get('text', '{no text}')[:50]}")
            return None

        is_new_entry = current_id not in all_tweets_collected
        current_tweet_obj = None
        original_type_before_update = None
        original_parent_before_update = None
        original_qt_level_before_update = None
        original_actual_reply_to_before_update = None # New for logging

        if is_new_entry:
            current_tweet_obj = tweet_data.copy()
            # Capture actual_reply_to_id from source data
            current_tweet_obj['actual_reply_to_id'] = tweet_data.get('reply_to_tweet_id')
            
            if 'tweet_type' not in current_tweet_obj or current_tweet_obj['tweet_type'] is None:
                app.logger.warning(f"[add_tweet_to_collection] NEW Tweet {current_id} missing tweet_type in tweet_data. Setting to 'unknown'. Original data reply_to: {tweet_data.get('reply_to_tweet_id')}")
                current_tweet_obj['tweet_type'] = 'reply' if current_tweet_obj.get('reply_to_tweet_id') else 'unknown' # Basic guess
        else: # Existing entry
            current_tweet_obj = all_tweets_collected[current_id]
            original_type_before_update = current_tweet_obj.get('tweet_type')
            original_parent_before_update = current_tweet_obj.get('parent_tweet_id')
            original_qt_level_before_update = current_tweet_obj.get('qt_level', -1)
            original_actual_reply_to_before_update = current_tweet_obj.get('actual_reply_to_id') # New for logging

            # Capture/Update actual_reply_to_id from current source data if provided
            # If current data has it, it's the most direct and likely authoritative.
            if 'reply_to_tweet_id' in tweet_data:
                current_tweet_obj['actual_reply_to_id'] = tweet_data['reply_to_tweet_id']
            # If not in current tweet_data, we keep the existing actual_reply_to_id (it might have been set from a previous pass or be None).
            # Ensure the field exists if it was never set (e.g. if first encounter didn't have reply_to_tweet_id)
            elif 'actual_reply_to_id' not in current_tweet_obj:
                 current_tweet_obj['actual_reply_to_id'] = None

            app.logger.info(f"[add_tweet_to_collection] EXISTING Tweet {current_id} PRE-UPDATE: Type='{original_type_before_update}', Parent='{original_parent_before_update}', QTLevel='{original_qt_level_before_update}', ActualReplyTo='{original_actual_reply_to_before_update}'. Processing with tweet_data type='{tweet_data.get('tweet_type')}', graph_link_parent_id='{graph_link_parent_id}', assigned_qt_level='{assigned_qt_level}', source reply_to_id='{tweet_data.get('reply_to_tweet_id')}'")
            
            # Preserve 'quote_tweet' type if already set and tweet_data offers something less specific.
            # If tweet_data explicitly says 'quote_tweet', update to it.
            if tweet_data.get('tweet_type') == 'quote_tweet':
                if current_tweet_obj.get('tweet_type') != 'quote_tweet':
                    app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: Updating type from '{current_tweet_obj.get('tweet_type')}' to 'quote_tweet' based on tweet_data.")
                    current_tweet_obj['tweet_type'] = 'quote_tweet'
                else:
                    app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: Type already 'quote_tweet', retained.")
            elif current_tweet_obj.get('tweet_type') == 'quote_tweet':
                app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: Retaining existing 'quote_tweet' type despite tweet_data type '{tweet_data.get('tweet_type')}'.")
                pass # Do nothing, preserve 'quote_tweet'
            elif 'tweet_type' in tweet_data and tweet_data['tweet_type'] is not None: # Otherwise, update from tweet_data if current isn't QT and new data has a valid type
                if current_tweet_obj.get('tweet_type') != tweet_data['tweet_type']:
                    app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: Updating type from '{current_tweet_obj.get('tweet_type')}' to '{tweet_data['tweet_type']}' from tweet_data.")
                    current_tweet_obj['tweet_type'] = tweet_data['tweet_type']
                else:
                    app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: Type '{current_tweet_obj.get('tweet_type')}' matches tweet_data, retained.")
            elif 'tweet_type' not in tweet_data or tweet_data['tweet_type'] is None:
                 app.logger.info(f"  [add_tweet_to_collection type decision] Tweet {current_id}: tweet_data has no type. Type '{current_tweet_obj.get('tweet_type')}' retained.")


        # Fallback: ensure tweet_type is set if still missing after above logic
        if 'tweet_type' not in current_tweet_obj or current_tweet_obj['tweet_type'] is None:
            app.logger.warning(f"[add_tweet_to_collection] Tweet {current_id} STILL missing 'tweet_type'. Defaulting to 'unknown'.")
            current_tweet_obj['tweet_type'] = 'unknown'
        
        # Determine the prospective parent_id from this call's context
        prospective_parent_id_from_context = graph_link_parent_id 
        # If this call doesn't specify a contextual parent, and the item *is* a reply, use its own reply_to_id
        if prospective_parent_id_from_context is None and current_tweet_obj.get('tweet_type') == 'reply':
            prospective_parent_id_from_context = current_tweet_obj.get('reply_to_tweet_id')

        # Logic for setting/updating parent_tweet_id
        parent_decision_reason = "No change initially."
        if is_new_entry:
            current_tweet_obj['parent_tweet_id'] = prospective_parent_id_from_context
            parent_decision_reason = f"NEW: Set to prospective_parent_id_from_context ('{prospective_parent_id_from_context}')"
            # app.logger.info(f"[DEBUG add_tweet_to_collection] NEW Tweet ID: {current_id}, Type: {current_tweet_obj.get('tweet_type')}, Initial parent_id set to: {prospective_parent_id_from_context}")
        else: # Existing entry, be careful with updates
            existing_parent_id = current_tweet_obj.get('parent_tweet_id') # This is original_parent_before_update
            
            # Rule 1: If this call specifically defines a QT link (graph_link_parent_id is set AND current type is QT)
            if graph_link_parent_id is not None and current_tweet_obj.get('tweet_type') == 'quote_tweet':
                if existing_parent_id != graph_link_parent_id:
                    current_tweet_obj['parent_tweet_id'] = graph_link_parent_id
                    parent_decision_reason = f"Rule 1 (QT Link): Updated from '{existing_parent_id}' to '{graph_link_parent_id}'"
                    # app.logger.info(f"[DEBUG add_tweet_to_collection] UPDATED QT Parent for ID: {current_id}. Old: {existing_parent_id}, New (QT link): {graph_link_parent_id}")
                else:
                    parent_decision_reason = f"Rule 1 (QT Link): Retained '{existing_parent_id}' (matches graph_link_parent_id)"
            # Rule 2: If existing parent was None, and this call provides a non-None prospective parent
            elif existing_parent_id is None and prospective_parent_id_from_context is not None:
                current_tweet_obj['parent_tweet_id'] = prospective_parent_id_from_context
                parent_decision_reason = f"Rule 2 (Contextual): Updated from None to '{prospective_parent_id_from_context}'"
                # app.logger.info(f"[DEBUG add_tweet_to_collection] UPDATED Parent for ID: {current_id} (was None). New: {prospective_parent_id_from_context}")
            # Rule 3: (Optional, for discussion) If this call offers a reply link and the type is 'reply',
            # and the existing parent is different - what to do? For now, we only update if existing was None or it's a QT link.
            # This means an existing specific link (e.g. QT link) won't be overwritten by a generic reply link from another context.
            else:
                parent_decision_reason = f"Rule 3 (Fallback): Retained '{existing_parent_id}'. Prospective_contextual='{prospective_parent_id_from_context}', graph_link_parent='{graph_link_parent_id}', type='{current_tweet_obj.get('tweet_type')}'"
                # app.logger.info(f"[DEBUG add_tweet_to_collection] RETAINED existing parent for ID: {current_id}. Existing: {existing_parent_id}, Contextual: {prospective_parent_id_from_context}, graph_link_parent: {graph_link_parent_id}, type: {current_tweet_obj.get('tweet_type')}")

        # Log final parent and type for existing entries after decision
        if not is_new_entry:
            app.logger.info(f"  [add_tweet_to_collection parent decision] Tweet {current_id}: Parent reason: [{parent_decision_reason}]. Final Parent='{current_tweet_obj.get('parent_tweet_id')}'")
            app.logger.info(f"  [add_tweet_to_collection post-update state] Tweet {current_id} FINAL: Type='{current_tweet_obj.get('tweet_type')}', Parent='{current_tweet_obj.get('parent_tweet_id')}', QTLevel='{current_tweet_obj.get('qt_level', -1)}', ActualReplyTo='{current_tweet_obj.get('actual_reply_to_id')}' (orig QTLevel='{original_qt_level_before_update}')")
        elif is_new_entry: # Log initial setup for new entries
             app.logger.info(f"[add_tweet_to_collection] NEW Tweet {current_id} ADDED: Type='{current_tweet_obj.get('tweet_type')}', Parent='{current_tweet_obj.get('parent_tweet_id')}', QTLevel='{current_tweet_obj.get('qt_level', -1)}', ActualReplyTo='{current_tweet_obj.get('actual_reply_to_id')}'")


        # Logic for setting/updating qt_level
        # Always prefer the lowest non-negative assigned_qt_level encountered.
        # -1 is a placeholder meaning "not yet determined" or "not a QT-related item from this path".
        current_qt_level_on_obj = current_tweet_obj.get('qt_level', -1) # Default to -1 if not present
        
        if is_new_entry:
            current_tweet_obj['qt_level'] = assigned_qt_level
            app.logger.info(f"[DEBUG add_tweet_to_collection] NEW Tweet ID: {current_id}, Initial qt_level set to: {assigned_qt_level}")
        else: # Existing entry
            if assigned_qt_level != -1: # If the current call provides a valid level
                if current_qt_level_on_obj == -1 or assigned_qt_level < current_qt_level_on_obj:
                    current_tweet_obj['qt_level'] = assigned_qt_level
                    app.logger.info(f"[DEBUG add_tweet_to_collection] UPDATED qt_level for ID: {current_id}. Old: {current_qt_level_on_obj}, New: {assigned_qt_level}")
                # else:
                    # app.logger.info(f"[DEBUG add_tweet_to_collection] RETAINED qt_level for ID: {current_id}. Existing: {current_qt_level_on_obj}, Assigned this call: {assigned_qt_level}")
            # If assigned_qt_level is -1, we don't update an existing valid level with -1.
        
        # Add to collection (or update the reference if it was already there)
        all_tweets_collected[current_id] = current_tweet_obj
        
        # Queueing logic for QTs (only if it's newly classified as QT or its level allows further processing)
        # Ensure we use the type from current_tweet_obj as it might have been updated.
        final_tweet_type = current_tweet_obj.get('tweet_type')
        final_qt_level = current_tweet_obj.get('qt_level', -1) # Use the potentially updated level

        # Check if it should be added to processing_queue (original condition from before, adapted)
        # A tweet is added to queue if:
        # 1. It's a 'quote_tweet'.
        # 2. It's a new entry to all_tweets_collected OR its qt_level was just updated to something allowing recursion.
        #    (This `is_new_entry` check alone might be too restrictive if level gets updated later allowing recursion)
        #    A better check: if it's a QT and its *final_qt_level* < max_depth and it's not already in queue *for this level or deeper*.
        #    For simplicity, we will use the original queuing logic based on `is_new_entry` for now and type.
        #    The critical part is that `add_tweet_to_collection` is now idempotent for parent/level setting.
        
        # Simplified queuing: if it's a QT and its final level allows deeper search, and not already processed for this.
        # To prevent re-queuing endlessly, we could check if (current_id, final_qt_level + 1) is already in a "processed_for_recursion" set.
        # For now, keep it similar to original logic:
        if final_tweet_type == 'quote_tweet' and is_new_entry and final_qt_level < max_depth : # and current_id not in [item[0] for item in processing_queue]:
            # The check for current_id in processing_queue might be needed if is_new_entry isn't enough
            # to prevent re-adding due to updates.
            # Let's rely on is_new_entry for the initial decision to queue.
            # The critical part is that add_tweet_to_collection's updates to parent/level are now more careful.
            
            app.logger.info(f"[add_tweet_to_collection] Queuing QT {current_id} for recursive fetching. Final level {final_qt_level}, max_depth {max_depth}")
            processing_queue.append((current_id, final_qt_level + 1, current_id)) 
        
        return current_tweet_obj

    # --- Initial Population ---
    app.logger.info("[DEBUG fetch_recursive_qt_data] Starting initial population of all_tweets_collected.")
    parent_id_for_direct_children = initial_main_post_data.get('id') if initial_main_post_data else initial_tweet_id

    if initial_main_post_data:
        app.logger.info(f"[DEBUG fetch_recursive_qt_data] Adding main post: {initial_main_post_data.get('id')}")
        add_tweet_to_collection(initial_main_post_data, graph_link_parent_id=None, assigned_qt_level=0)

    for reply_data in initial_replies_data:
        # For initial replies, do not force parentage to main post.
        # Let add_tweet_to_collection use reply_data.get('reply_to_tweet_id').
        # All these replies are part of the original thread, so qt_level is 0.
        app.logger.info(f"[DEBUG fetch_recursive_qt_data] Adding initial reply: {reply_data.get('id')} (will use its own reply_to_tweet_id if available)")
        add_tweet_to_collection(reply_data, graph_link_parent_id=None, assigned_qt_level=0)
    
    for qt_data in initial_quote_tweets_data:
        app.logger.info(f"[DEBUG fetch_recursive_qt_data] Adding initial QT: {qt_data.get('id')} with parent {parent_id_for_direct_children}")
        add_tweet_to_collection(qt_data, graph_link_parent_id=parent_id_for_direct_children, assigned_qt_level=1)

    app.logger.info(f"[DEBUG fetch_recursive_qt_data] After initial population: all_tweets_collected size: {len(all_tweets_collected)}, processing_queue size: {len(processing_queue)}")
    if all_tweets_collected:
        app.logger.info("[DEBUG fetch_recursive_qt_data] First item ID in all_tweets_collected (if any): " + str(next(iter(all_tweets_collected.keys()), "Empty")))
    # --- End Initial Population ---
    
    processed_indices_in_queue = 0
    while processed_indices_in_queue < len(processing_queue):
        qt_being_processed_id, child_qt_level_for_this_qt, parent_id_for_direct_children_of_this_qt = processing_queue[processed_indices_in_queue]
        processed_indices_in_queue += 1

        app.logger.info(f"[DEBUG fetch_recursive_qt_data] Processing queue item: QT_ID={qt_being_processed_id}, Children_QT_Level={child_qt_level_for_this_qt}, Parent_For_Children={parent_id_for_direct_children_of_this_qt}")

        original_qt_object = all_tweets_collected.get(qt_being_processed_id)
        if not original_qt_object:
            app.logger.warning(f"[DEBUG fetch_recursive_qt_data] Original QT object {qt_being_processed_id} not found in all_tweets_collected. Skipping its recursion.")
            continue

        current_qt_actual_level = original_qt_object.get('qt_level', 1) # Level of the QT being processed

        # 1. Fetch the conversation this QT belongs to
        qt_author_handle_for_thread = original_qt_object.get('author_handle')
        if not qt_author_handle_for_thread:
            app.logger.warning(f"[DEBUG fetch_recursive_qt_data] QT object {qt_being_processed_id} missing 'author_handle'. Cannot fetch its thread. Skipping reply/context fetching for this QT.")
        else:
            qt_thread_url = f"https://x.com/{qt_author_handle_for_thread}/status/{qt_being_processed_id}"
            app.logger.info(f"[DEBUG fetch_recursive_qt_data] Fetching full thread for QT_ID={qt_being_processed_id} (its actual level {current_qt_actual_level}) using URL {qt_thread_url}")
            
            # This fetches the entire conversation the QT is part of
            qt_conversation_items = await tweet_fetcher.fetch_enriched_tweet_thread(qt_thread_url)

            if isinstance(qt_conversation_items, list):
                app.logger.info(f"  [DEBUG fetch_recursive_qt_data] Fetched {len(qt_conversation_items)} items for QT {qt_being_processed_id}'s conversation.")
                for convo_item_data in qt_conversation_items:
                    convo_item_id = convo_item_data.get('id')
                    if not convo_item_id:
                        app.logger.warning(f"    [DEBUG fetch_recursive_qt_data] Skipping convo_item_data without ID for QT {qt_being_processed_id}.")
                        continue

                    # If this item is the QT itself that we are currently processing:
                    if convo_item_id == qt_being_processed_id:
                        # This convo_item_data is for the QT itself.
                        # It should be linked to the tweet it *actually quotes*.
                        # This parent information should already exist in all_tweets_collected for this QT.
                        parent_it_actually_quotes = all_tweets_collected.get(qt_being_processed_id, {}).get('parent_tweet_id')
                        
                        app.logger.info(f"    [DEBUG fetch_recursive_qt_data] Re-processing QT {convo_item_id} (as part of its own thread fetch). Original parent_tweet_id from collection: {parent_it_actually_quotes}. Current QT's actual level: {current_qt_actual_level}.")
                        add_tweet_to_collection(
                            convo_item_data, # Data for the QT itself, type might be 'main_post' from this specific fetch
                            graph_link_parent_id=parent_it_actually_quotes, # Crucial: Link to what it originally quoted
                            assigned_qt_level=current_qt_actual_level # Its own, established QT level
                        )
                    # Else, it's another tweet in the conversation (e.g., a reply to the QT, or parent of QT in that thread)
                    else:
                        # Ensure tweet_type is present for these items.
                        # _enrich_single_tweet in tweet_fetcher should generally handle this, but good to be safe.
                        if 'tweet_type' not in convo_item_data or convo_item_data['tweet_type'] is None:
                            if convo_item_data.get('reply_to_tweet_id'):
                                convo_item_data['tweet_type'] = 'reply'
                            # If no reply_to_tweet_id, it might be the main post of another convo. 
                            # We leave its type as is from enrichment, or it remains None if not set.
                            # This is acceptable as add_tweet_to_collection will handle it.

                        app.logger.info(f"    [DEBUG fetch_recursive_qt_data] Processing convo item {convo_item_id} (from QT {qt_being_processed_id}'s thread). Linking via its own reply_to_id. Assigned QT level: {current_qt_actual_level}")
                        add_tweet_to_collection(
                            convo_item_data,
                            graph_link_parent_id=None, # Let add_tweet_to_collection use convo_item_data's reply_to_tweet_id
                            assigned_qt_level=current_qt_actual_level # Group visually with the QT
                        )
            else:
                app.logger.info(f"  [DEBUG fetch_recursive_qt_data] No thread items found or error for QT {qt_being_processed_id} (URL: {qt_thread_url})")
        
        # 2. Fetch QTs that quote this current_qt_object (if depth allows)
        # This part for fetching *further QTs* (children QTs of the current QT) remains the same.
        if current_qt_actual_level < max_depth:
            # Construct the URL of the current QT to find tweets quoting it
            qt_author_handle = original_qt_object.get('author_handle')
            if not qt_author_handle: # Should ideally not happen if QT object is well-formed
                app.logger.warning(f"[DEBUG fetch_recursive_qt_data] Missing author_handle for QT_ID={qt_being_processed_id}, cannot form URL to fetch its QTs. Skipping further QT recursion for this branch.")
            else:
                qt_url_of_current_qt = f"https://x.com/{qt_author_handle}/status/{original_qt_object.get('id')}"
                app.logger.info(f"[DEBUG fetch_recursive_qt_data] Fetching QTs quoting current QT_ID={qt_being_processed_id} (URL: {qt_url_of_current_qt}), for new_child_qt_level={child_qt_level_for_this_qt})")
                
                # fetch_quote_tweets expects supabase_client as its first arg currently.
                # Ensure supabase_client is available in this scope or pass it if tweet_fetcher is refactored.
                # Assuming tweet_fetcher.supabase_client is accessible via the module.
                further_qts_quoting_this_qt = await tweet_fetcher.fetch_quote_tweets(tweet_fetcher.supabase_client, qt_url_of_current_qt)

                if isinstance(further_qts_quoting_this_qt, list):
                    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Found {len(further_qts_quoting_this_qt)} further QTs quoting QT_ID={qt_being_processed_id}")
                    for further_qt_data in further_qts_quoting_this_qt:
                        # These are new QTs. Their parent is original_qt_object.
                        # Their qt_level is child_qt_level_for_this_qt.
                        newly_added_qt_obj = add_tweet_to_collection(
                            further_qt_data,
                            graph_link_parent_id=qt_being_processed_id, # Parent is the QT they are quoting
                            assigned_qt_level=child_qt_level_for_this_qt 
                        )
                        # Add this new QT to the processing queue if it's valid and not already processed/queued, and depth allows for its children
                        if newly_added_qt_obj and newly_added_qt_obj.get('id') and newly_added_qt_obj.get('id') not in [item[0] for item in processing_queue]:
                            # The next level for children of *this new QT* will be child_qt_level_for_this_qt + 1
                            if child_qt_level_for_this_qt + 1 <= max_depth:
                                processing_queue.append((
                                    newly_added_qt_obj.get('id'), 
                                    child_qt_level_for_this_qt + 1, # Level for children of this *newly_added_qt_obj*
                                    newly_added_qt_obj.get('id')    # Parent ID for children of *newly_added_qt_obj*
                                ))
                elif isinstance(further_qts_quoting_this_qt, dict) and 'error' in further_qts_quoting_this_qt:
                     app.logger.error(f"[DEBUG fetch_recursive_qt_data] Error fetching QTs for QT_ID={qt_being_processed_id}: {further_qts_quoting_this_qt['error']}")
        else:
            app.logger.info(f"[DEBUG fetch_recursive_qt_data] Max depth reached for children of QT_ID={qt_being_processed_id}. Not fetching further QTs quoting it.")

    # --- Remove old aggressive logging if it was here ---
    # No longer calling fetch_enriched_tweet_thread in this loop, so associated RAW logging is gone.

    app.logger.info(f"[DEBUG fetch_recursive_qt_data] Finished processing queue. Total tweets collected: {len(all_tweets_collected)}")
    return list(all_tweets_collected.values())    

@app.route('/config')
def config():
    return jsonify(APP_CONFIG)

if __name__ == '__main__':
    # Ensure the app runs with the appropriate host and port for Gunicorn
    # Gunicorn will specify host/port, so app.run() is mainly for local dev
    port = int(os.environ.get("PORT", 8080)) # Default to 8080 if PORT not set
    app.run(debug=True, host='0.0.0.0', port=port) 