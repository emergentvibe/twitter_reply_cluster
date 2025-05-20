# Development Plan: Twitter Discourse Analyzer (API Version)

This document outlines the development plan for a new version of the Twitter Discourse Analyzer. This version will use the Open Birdsite DB API for fetching tweet data instead of Selenium-based scraping.

**Objective:** Create a web application where a user can submit a Twitter post URL. The backend will fetch the main tweet, its replies, and quote tweets using the Open Birdsite DB API, analyze the discourse using an LLM (Anthropic Claude) for classification and summarization, and then display the clustered replies/quote tweets and summaries on the frontend.

**API Details:**
*   **Base URL:** `https://fabxmporizzqflnftavs.supabase.co`
*   **Data Sources:** `tweets_w_conversation_id` view, `tweets` table, `account` table, `profile` table, `quote_tweets` materialized view, `enriched_tweets` view.
*   **Authentication:** Bearer Token in `Authorization` header. (Token provided by user).

## Phase 0: Project Restructuring & Initial Setup

1.  **[COMPLETED]** Move existing Selenium-based application code to an `old_code/` directory.
2.  **[COMPLETED]** Create this `dev-plan.md` in the project root.
3.  **[COMPLETED]** Initialize new project structure in the root directory:
    *   `app.py` (Flask backend)
    *   `tweet_fetcher.py` (Module for Open Birdsite DB API interaction)
    *   `llm_analyzer_suite.py` (Combined/adapted LLM classification and summarization logic)
    *   `templates/` directory
        *   `templates/index.html` (Frontend HTML)
    *   `static/` directory
        *   `static/style.css` (CSS, can adapt from `old_code/static/style.css`)
        *   `static/script.js` (Frontend JS, can adapt from `old_code/static/script.js`)
    *   `.env` (To store API keys: Anthropic and Open Birdsite DB token)
    *   `requirements.txt` (Flask, requests, python-dotenv, anthropic)
    *   `directory-map.md` (To be created and maintained)

## Phase 1: Backend - API Interaction (`tweet_fetcher.py`)

1.  **[COMPLETED]** Create `tweet_fetcher.py`:
    *   **[COMPLETED]** Store API base URL and authentication token (loaded from `.env`).
    *   **[COMPLETED]** Implement `get_tweet_thread(tweet_id)` function (now `_fetch_raw_tweet_thread` internally, with `fetch_enriched_tweet_thread` as the main public function):
        *   Input: `tweet_id` (string).
        *   **[COMPLETED]** Constructs URL for `/rpc/get_main_thread?p_conversation_id={tweet_id}` (handled by Supabase client).
        *   **[COMPLETED]** Makes a GET request with appropriate `Authorization` header (handled by Supabase client).
        *   **[COMPLETED]** Crucial: Investigate the structure of the response from `/rpc/get_main_thread`. Determine if it includes necessary author details (username, display name, avatar) directly, or if we need to use `select` parameters (if `/rpc/` calls support them) or make subsequent calls to `/tweets` or `/account` to enrich the data.
            *   *Outcome: `get_main_thread` provides basic tweet structure. Enrichment is needed from `tweets`, `account`, and `profile` tables.* 
        *   **[COMPLETED]** The goal is to obtain a list of tweet dictionaries, each containing:
            *   `id` (string, tweet ID)
            *   `text` (string)
            *   `author_handle` (string, e.g., "@username")
            *   `author_display_name` (string)
            *   `avatar_url` (string, URL to profile picture)
            *   `timestamp` (string, ISO 8601 format)
            *   `like_count` (integer)
            *   `retweet_count` (integer)
            *   `reply_to_tweet_id` (string, ID of the tweet this is a reply to, if any)
            *   *Other fields from `get_main_thread` like `conversation_id` are also included.*
    *   **[COMPLETED]** Implement helper functions to fetch details from `/tweets`, `/account`, `/profile` asynchronously (now using batch fetching).
    *   **[COMPLETED]** Orchestrate these calls in `fetch_enriched_tweet_thread`.
    *   **[COMPLETED]** Ensure robust error handling and logging for API interactions (significantly improved with batch fetching; further specific logging can be added as needed).

## Phase 2: Backend - LLM Analysis Adaptation (`llm_analyzer_suite.py`)

1.  **[COMPLETED]** Create `llm_analyzer_suite.py`:
    *   **[COMPLETED]** This module will adapt the logic from `old_code/llm_classifier.py` and `old_code/llm_summarizer.py` (logic recreated based on plan).
    *   **[COMPLETED]** Function `analyze_tweets(main_post_data, replies_data)`:
        *   Input:
            *   `main_post_data`: Dictionary for the main tweet (fetched by `tweet_fetcher.py`).
            *   `replies_data`: List of dictionaries for the replies (fetched by `tweet_fetcher.py`).
        *   **[COMPLETED]** Classification Sub-Phase:
            *   Iterate through `replies_data`.
            *   For each reply, construct a prompt for the LLM (Anthropic Claude) including original post text, parent tweet text (if applicable and easily determinable from data), and current reply text.
            *   Classify: sentiment, agreement, question (same as before).
            *   Store these classifications directly in the reply's dictionary.
        *   **[COMPLETED]** Summarization Sub-Phase:
            *   Group classified reply dictionaries (e.g., "positive\_agrees").
            *   For each group:
                *   LLM call to generate a concise summary of tweets in that group.
                *   Collect all tweets belonging to the group (full data + classifications).
            *   Generate overall discourse summary using LLM (main post text + cluster summaries).
        *   **[COMPLETED]** Output Construction:
            *   Construct the final Python dictionary:
                *   `main_post_id`
                *   `main_post_text`
                *   `main_post_author_handle`
                *   `main_post_author_display_name` (added from implementation)
                *   `main_post_likes`
                *   `main_post_timestamp`
                *   `main_post_avatar_url` (*if available*)
                *   `overall_summary`
                *   `cluster_details`: Dictionary of cluster names -> { "summary": "...", "tweets": [...] }
                    *   Each tweet in the "tweets" list should be a dictionary with all its attributes (ID, text, author, likes, timestamp, avatar, LLM classifications).
    *   **[COMPLETED]** Load Anthropic API key from `.env`.
    *   **[COMPLETED]** Ensure error handling for LLM API calls.

## Phase 3: Backend - Flask API Endpoint (`app.py`)

1.  **[COMPLETED]** Create `app.py`:
    *   **[COMPLETED]** Initialize Flask application.
    *   **[COMPLETED]** Load environment variables from `.env` (API keys).
    *   **[COMPLETED]** Define `POST /api/analyze_url` endpoint:
        *   **[COMPLETED]** Accepts JSON: `{"tweet_url": "..."}`.
        *   **[COMPLETED]** Extract `tweet_id` using helper from `tweet_fetcher.py`.
        *   **[COMPLETED]** Call `tweet_fetcher.fetch_enriched_tweet_thread(tweet_url)` to get the main post and replies.
        *   **[COMPLETED]** Call `tweet_fetcher.fetch_quote_tweets` (added in Phase 6).
        *   **[COMPLETED]** Separate the main post data from the replies data.
        *   **[COMPLETED]** Call `llm_analyzer_suite.analyze_tweets(main_post_data, replies_data)`.
        *   **[COMPLETED]** Return the resulting JSON from `analyze_tweets` with a 200 status (or error status if LLM analysis fails).
        *   **[COMPLETED]** Handle potential errors from `tweet_fetcher` or `llm_analyzer_suite` and return appropriate error responses (e.g., 400 for bad URL, 500 for internal errors).
    *   **[COMPLETED]** Define route `/` to serve `templates/index.html`.

## Phase 4: Frontend Development (`templates/index.html`, `static/script.js`, `static/style.css`)

1.  **[COMPLETED]** Create `templates/index.html`:
    *   **[COMPLETED]** Simple HTML structure with:
        *   Input field for tweet URL.
        *   "Analyze" button.
        *   `<div id="main-post-display"></div>` for the main tweet.
        *   `<div id="overall-summary"></div>`.
        *   `<div id="clusters-container"></div>` (which will contain `#clusters-columns-container`).
    *   **[COMPLETED]** Include link to `static/style.css`.
    *   **[COMPLETED]** Include script tags for `tweet-component.js` (external) and `static/script.js` (local).

2.  **[COMPLETED]** Adapt `static/script.js`:
    *   **[COMPLETED]** Event listener for "Analyze" button.
    *   **[COMPLETED]** On click:
        *   **[COMPLETED]** Get URL from input.
        *   **[COMPLETED]** Show a loading indicator.
        *   **[COMPLETED]** `fetch('/api/analyze_url', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tweet_url: url}) })`.
        *   **[COMPLETED]** Handle response:
            *   **[COMPLETED]** If successful, parse JSON.
            *   **[COMPLETED]** Call `displayMainPost(data.main_post_text, data.main_post_id, data.main_post_author_handle, data.main_post_likes, data.main_post_timestamp, data.main_post_avatar_url)`. (Adjust `displayMainPost` to accept and use avatar).
            *   **[COMPLETED]** Call `displayOverallSummary(data.overall_summary)`.
            *   **[COMPLETED]** Call `displayClusters(data.cluster_details)`. (Ensure `tweet-component` in `displayClusters` can also handle `avatar_url`).
        *   **[COMPLETED]** Handle errors (e.g., display error message to user).
        *   **[COMPLETED]** Hide loading indicator.
    *   **[COMPLETED]** The `displayMainPost` and `displayClusters` (specifically the part creating `<tweet-component>`) functions will need to be updated to use the `avatar_url` if present in the data, passing it to the `avatar` attribute of the component. (Initial version created, adaptation for tweet-component later)

3.  **[COMPLETED]** Adapt `static/style.css`:
    *   **[COMPLETED]** Copy styles from `old_code/static/style.css`.
    *   **[COMPLETED]** Ensure styles for `tweet-component` (if any specific ones were added beyond the component's own styling) and the cluster layout are still appropriate.

## Phase 5: Dependencies and Documentation

1.  **[COMPLETED]** Create `requirements.txt`:
    *   **[COMPLETED]** `Flask`
    *   **[COMPLETED]** `requests`
    *   **[COMPLETED]** `python-dotenv`
    *   **[COMPLETED]** `anthropic`
    *   **[COMPLETED]** `supabase` (added during Phase 1)
2.  **[COMPLETED]** Create and maintain `directory-map.md`:** Document the purpose and content of each new file.
3.  **[COMPLETED]** Update `.env_example`** (if creating one) with needed variables: `ANTHROPIC_API_KEY`, `OPEN_BIRDSITE_DB_TOKEN`, `OPEN_BIRDSITE_DB_BASE_URL`. (User to manage actual `.env` and `.env.example`)

## Phase 6: Quote Tweet Implementation

1.  **[COMPLETED]** Investigated methods to fetch quote tweets.
2.  **[COMPLETED]** Identified and utilized the `quote_tweets` materialized view and `enriched_tweets` view from Open Birdsite DB.
3.  **[COMPLETED]** Implemented `tweet_fetcher.fetch_quote_tweets` to efficiently get quote tweets using the `enriched_tweets` view.
4.  **[COMPLETED]** Integrated quote tweet fetching into `app.py`.
5.  **[COMPLETED]** Added `tweet_type: 'quote_tweet'` flag.
6.  **[COMPLETED]** Ensured quote tweets are processed by `llm_analyzer_suite.analyze_tweets` similarly to replies.
7.  **[COMPLETED]** Added UI indicator in `static/script.js` to distinguish quote tweets in the display.

## Phase 7: Repository Finalization & Documentation

1.  **[COMPLETED]** Cleaned up repository:
    *   **[COMPLETED]** Created/Updated `.gitignore` to exclude `venv/`, `__pycache__/`, `.DS_Store`, `.cursor/`, and the actual `.env` file.
    *   **[COMPLETED]** User deleted obsolete test scripts (`test_anthropic.py`, `test_quote_tweet_fetcher.py`).
    *   **[PENDING USER REVIEW]** `Scalar API Reference.json` (large reference file, can be kept locally but perhaps not committed/deployed).
    *   **[PENDING USER REVIEW]** `old_code/` directory (can be deleted if fully superseded or archived).
2.  **[COMPLETED]** Added `README.md` with project overview, setup, and usage instructions.
3.  **[COMPLETED]** Added `LICENSE` file (MIT License, user to fill in copyright year/name).
4.  **[COMPLETED]** Created `.env.example` file to show required environment variables.

## Phase 8: Graph Visualization

### Sub-Phase 8.1: Initial Graph Implementation (Cytoscape.js)

1.  **[COMPLETED]** **Backend (`graph_visualizer.py`):**
    *   **[COMPLETED]** Implemented `create_reply_graph` to build a NetworkX graph from tweet data (main post, replies, quote tweets).
    *   **[COMPLETED]** Added node attributes: `id`, `text`, `author`, `display_name`, `type` (main_post, reply, quote_tweet), `likes`, `timestamp`, `classification`.
    *   **[COMPLETED]** Added edge attributes: `relationship` ('reply', 'quotes').
    *   **[COMPLETED]** Implemented `analyze_graph` to compute basic graph metrics (total tweets, replies, main post identification, reply depth, most replied to, author stats).
    *   **[COMPLETED]** Implemented `process_tweet_data` to convert NetworkX graph to Cytoscape.js compatible JSON (`cytoscape_elements`).
2.  **[COMPLETED]** **Backend (`app.py`):**
    *   **[COMPLETED]** Integrated `process_tweet_data` into the `/api/analyze_url` endpoint.
    *   **[COMPLETED]** Included `graph_metrics` and `cytoscape_elements` in the API response.
3.  **[COMPLETED]** **Frontend (`templates/index.html` & `static/script.js` & `static/styles.css`):**
    *   **[COMPLETED]** Added Cytoscape.js library.
    *   **[COMPLETED]** Dynamically created a `div` container for the graph.
    *   **[COMPLETED]** Initialized Cytoscape.js with data from the API.
    *   **[COMPLETED]** Implemented node styling:
        *   Color by `type` (main_post: red, quote_tweet: green, reply: blue).
        *   Label by `author` and short `text` snippet (with text wrapping).
        *   Size by `likes`.
    *   **[COMPLETED]** Implemented edge styling (simple lines with arrows).
    *   **[COMPLETED]** Applied 'cose' layout with extensive parameter tuning for clarity and node separation (e.g., `idealEdgeLength` based on relationship type, `nodeRepulsion`, `numIter`).
    *   **[COMPLETED]** Added tap event on nodes to display tweet details in a separate div.
    *   **[COMPLETED]** Displayed graph metrics below the graph.
    *   **[COMPLETED]** Resolved issues with graph container height and rendering visibility.

### Sub-Phase 8.2: Enhanced Graph Visualization with D3.js

**Objective:** Replace Cytoscape.js with D3.js to implement a custom force-directed layout with more granular control over forces, enabling specific interactions like attraction to axes/points and differential repulsion based on node types or relationships.

1.  **Setup & Initial Rendering:**
    *   **[COMPLETED]** Add D3.js library to the project (e.g., via CDN in `index.html`).
    *   **[COMPLETED]** Backend (`graph_visualizer.py` - Re-evaluate): Assess if the current `cytoscape_elements` format is directly usable by D3.js (D3 typically expects `nodes` and `links` arrays). If not, create a new function or adapt `process_tweet_data` to output D3-compatible graph data (e.g., `{ nodes: [...], links: [...] }`). Ensure node objects include all necessary attributes (`id`, `text`, `author`, `type`, `likes`, etc.) and link objects include `source` (id), `target` (id), and `relationship`. (Note: `save_graph_data_json` function in `graph_visualizer.py` to be manually deleted by user).
    *   **[COMPLETED]** Frontend (`static/script.js` - Major Refactor):
        *   **[COMPLETED]** Remove Cytoscape.js initialization and rendering logic. (Note: Block of Cytoscape helper functions to be manually deleted by user).
        *   **[COMPLETED]** Set up an SVG container for D3.js visualization.
        *   **[COMPLETED]** Implement basic D3.js rendering: draw SVG circles for nodes and lines for edges based on the D3-compatible data.
2.  **Basic Force Simulation (`d3-force`):**
    *   **[COMPLETED]** Initialize `d3.forceSimulation()`.
    *   **[COMPLETED]** Add core forces:
        *   **[COMPLETED]** `d3.forceLink()`: To position nodes based on edge connections (use `id`s for source/target).
        *   **[COMPLETED]** `d3.forceManyBody()`: For node repulsion (charge force).
        *   **[COMPLETED]** `d3.forceCenter()`: To keep the graph centered in the SVG container.
    *   **[COMPLETED]** Implement the simulation tick function to update node/edge positions.
3.  **Styling and Basic Interactions:**
    *   **[COMPLETED]** Apply node styling using D3 attributes:
        *   **[COMPLETED]** Fill color based on `type` (main_post, reply, quote_tweet).
        *   **[COMPLETED]** Radius based on `likes`.
        *   **[COMPLETED]** Add text labels for `author` (and potentially short text snippets if feasible with D3 text elements).
    *   **[COMPLETED]** Style edges (lines). (Currently basic grey lines, with different types for 'reply' vs 'quote_to_actual_reply')
    *   **[COMPLETED]** Implement zoom and pan functionality for the SVG container.
    *   **[COMPLETED]** Implement node click/tap event to display tweet details (reuse/adapt existing `#tweet-detail-display` logic).
4.  **Custom Force Implementation:**
    *   **[COMPLETED]** Identify the main post node (e.g., based on `type: 'main_post'`).
    *   **[COMPLETED]** Implement `d3.forceX()` and `d3.forceY()` to attract/position nodes:
        *   **[COMPLETED]** Force to pull the main post towards a specific point (e.g., center of SVG, or a conceptual (0,0)).
        *   **[COMPLETED]** Force(s) to align/attract specific node types (e.g., replies vs. quote tweets) along certain axes or lines relative to the main post or other reference points. (Initial implementation: vertical separation for replies/quotes).
        *   *Example: Replies might have a force pulling them towards a circular orbit around their parent, while quote tweets are pushed to a different region or along a specific axis.* 
    *   **[COMPLETED]** Customize `d3.forceManyBody()` or link forces to achieve differential repulsion/attraction if needed (e.g., stronger repulsion between quote tweets, or between quote tweets and the main post, compared to replies). (Initial implementation: stronger repulsion for quote tweets).
    *   **[COMPLETED]** Iterate on force strengths and parameters to achieve the desired layout for clarity and semantic representation. (Significant iteration and tuning performed for main post replies, QT positioning, QT reply positioning, and roots of external conversations).
5.  **Testing and Refinement:**
    *   **[IN PROGRESS - SIGNIFICANT ITERATION DONE]** Test with various thread structures (few replies, many replies, many quotes, deep threads).
    *   **[TO_DO]** Optimize performance if needed, especially for larger graphs.
    *   **[IN PROGRESS - SIGNIFICANT ITERATION DONE]** Refine visual appearance and interactivity.

## Phase 9: Feature Toggles

1.  **[COMPLETED]** **Configuration Files:**
    *   **[COMPLETED]** Created `config.example.json` with `enable_ai_analysis` and `enable_graph_visualization` flags.
    *   **[COMPLETED]** Created `config.json` (intended for local modification, added to `.gitignore`).
2.  **[COMPLETED]** **Backend (`app.py`):**
    *   **[COMPLETED]** Implemented `load_app_config()` to read `config.json` with fallbacks to defaults.
    *   **[COMPLETED]** Conditionally execute `analyze_tweets` based on `APP_CONFIG['enable_ai_analysis']`.
    *   **[COMPLETED]** Conditionally execute `process_tweet_data` based on `APP_CONFIG['enable_graph_visualization']`.
    *   **[COMPLETED]** Ensure `analysis_results` includes appropriate placeholders or messaging if features are disabled (e.g., `overall_summary: "AI analysis disabled"`, empty `d3_graph_data` with status).
3.  **[COMPLETED]** **Frontend (`static/script.js`):**
    *   **[COMPLETED]** Modified `displayAnalysisData` to check for disabled status in `d3_graph_data` and `graph_metrics` and hide/update UI elements accordingly.
    *   **[COMPLETED]** Updated `displayOverallSummary` and `displayGraphMetrics` to show disabled messages if present in the data.
4.  **[COMPLETED]** **Documentation:**
    *   **[COMPLETED]** Added `config.json` to `.gitignore`.
    *   **[COMPLETED]** Added `config.json` and `config.example.json` to `directory-map.md`.

## Phase 10: Recursive Quote Tweet Fetching & Visualization

**Objective:** Extend the application to fetch and visualize replies to quote tweets, and subsequent levels of quote tweets, up to a configurable depth.

1.  **Configuration:**
    *   **[COMPLETED]** Add `recursive_qt_max_depth` to `config.json` and `config.example.json` (default: 5).
    *   **[COMPLETED]** Update `app.py` (`load_app_config`) to load this new setting.

2.  **Backend (`tweet_fetcher.py` & `app.py`):
    *   **[COMPLETED]** Refactor fetching logic in `app.py` (e.g., within `analyze_url_route` or a new helper async function) to handle recursive fetching for quote tweets and their replies.
        *   This function will manage a list/set of processed tweet IDs to avoid re-processing and cycles.
        *   For each newly discovered quote tweet (up to `recursive_qt_max_depth`):
            *   Fetch its direct replies (e.g., by using `fetch_enriched_tweet_thread` treating the QT as a temporary main post, then adapting parentage).
            *   Fetch its direct quote tweets (using `fetch_quote_tweets`).
            *   Newly fetched tweets are added to a global list for processing.
    *   **[COMPLETED]** Modify tweet data objects being collected:
        *   Ensure each tweet has a unique `id`.
        *   Add `qt_level` (integer: 0 for QTs of the original post, 1 for QTs of Level 0 QTs, etc.). Replies to a QT can inherit the `qt_level` of their parent QT or have it incremented.
        *   Add `parent_tweet_id` (string: the ID of the tweet this tweet is a reply to, or the ID of the tweet this QT is quoting). This should correctly point to the immediate parent.
        *   Add `actual_reply_to_id` (string: the ID of the tweet this tweet is a direct reply to, irrespective of QT relationships).
        *   `tweet_type` remains ('main_post', 'reply', 'quote_tweet'). Logic to preserve 'quote_tweet' type and correctly identify 'main_post' for roots of external conversations has been implemented.
    *   **[COMPLETED]** `app.py` (`analyze_url_route`):
        *   The main list `all_tweets_for_processing` (sent to `graph_visualizer.py`) must contain all unique tweets from all levels with the new attributes (`qt_level`, `parent_tweet_id`, `actual_reply_to_id`).
        *   LLM analysis scope remains unchanged for now (only original main post and its direct replies/quotes).

3.  **Graph Visualization (`graph_visualizer.py`):**
    *   **[COMPLETED]** Update `create_reply_graph` to add a `qt_level` attribute to each node (defaulting to -1 if not present in input data, which should be 0 for main post and its direct interactions, and 1+ for recursive QTs).
    *   **[COMPLETED]** Update edge creation logic to link nodes to their `parent_tweet_id` for both 'reply' and 'quote_tweet' types.
    *   **[COMPLETED]** Added secondary edge creation logic based on `actual_reply_to_id` to represent direct reply chains within conversation threads that might also be linked via QTs.

4.  **Frontend D3.js Visualization Update (`static/script.js`):**
    *   **[COMPLETED]** Modify the D3 force simulation in `initializeD3Graph`.
    *   **[COMPLETED]** Use the `qt_level` attribute on nodes for their horizontal (`forceX`) positioning.
        *   Main post (`qt_level: 0` or `id === mainPostId`) remains fixed at the center (`fx`, `fy`).
        *   Replies to main post (`qt_level: 0`) are pulled towards the center's X-coordinate (with adjustments to prevent strict left-side clustering).
        *   Quote tweets (`qt_level: 1`) are pulled to a vertical line to the right of the main post.
        *   Recursively fetched QTs (`qt_level: 2, 3, ...`) are pulled to subsequent vertical lines, each further to the right.
        *   Roots of external conversations linked via QTs are positioned on the appropriate QT level's vertical line.
        *   *Note: Force parameters (X-offsets, strengths) were adjusted iteratively and may require further tuning based on visual results with diverse datasets.*
    *   **[COMPLETED]** Ensure link distances/strengths and repulsion forces are appropriately configured to work well with the new `qt_level` based layout (e.g., replies to QTs should cluster around their parent QT on its vertical line). (Significant iteration completed).

5.  **Testing and Refinement:**
    *   **[IN PROGRESS - SIGNIFICANT ITERATION DONE]** Test with tweets that have multiple levels of quote tweets and replies to quote tweets.
    *   **[IN PROGRESS - ITERATION DONE, FURTHER TUNING POSSIBLE]** Tune force parameters (X positions, link distances/strengths, charge) for clarity.
    *   **[TO_DO]** Monitor for and address performance issues with increased data.
    *   **[COMPLETED]** Handle potential infinite loops or excessive recursion in fetching (though `recursive_qt_max_depth` and processed ID tracking should prevent this).

## Future Enhancements (Post-MVP)

*   Add specific CSS styling for the `(Quote Tweet)` indicator in the UI.
*   More robust error handling and user feedback on the frontend for edge cases.
*   UI/UX Refinements:
    *   More polished loading states/animations.
    *   Improved visual distinction or layout for clusters.
    *   Direct links to original tweets/quote tweets on X.com.
*   Deployment strategy and execution (e.g., Docker, PaaS like Heroku/Render).
*   Caching results for previously analyzed URLs to save API calls and time.
*   Deeper LLM Analysis Options:
    *   Allowing users to choose different LLM models or tweak prompts (advanced).
    *   Extracting key themes or topics beyond just sentiment/agreement.
    *   Identifying influential users within the replies/quotes.
*   Consideration for very large threads: frontend pagination or virtualization for tweet lists if performance becomes an issue.
*   Develop a more formal test suite for backend logic. 