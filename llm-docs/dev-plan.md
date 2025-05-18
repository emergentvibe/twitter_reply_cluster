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