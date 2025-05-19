# Directory Map

This document outlines the structure and purpose of files and directories in the Twitter Discourse Analyzer (API Version) project.

## Root Directory (`./`)

*   **`app.py`**: 
    *   **Purpose:** Main Flask application file.
    *   **Contents Overview:** Handles API endpoints (e.g., `/api/analyze_url` for processing tweet URLs, `/` for serving the main page), orchestrates calls to `tweet_fetcher.py` and `llm_analyzer_suite.py` (planned), and serves frontend files. Loads environment variables using `dotenv`. Provides an endpoint `/api/analyze_url` which accepts a POST request with a `tweet_url`, calls `tweet_fetcher.fetch_enriched_tweet_thread` to get the main post and replies, and returns them as JSON. Includes logic to manage async calls from the sync Flask environment.
    *   **Interactions:** Imports from `tweet_fetcher` (specifically `fetch_enriched_tweet_thread` and `extract_tweet_id_from_url`), and will import from `llm_analyzer_suite`. Serves `templates/index.html`. Called by frontend JavaScript.

*   **`tweet_fetcher.py`**:
    *   **Purpose:** Module for interacting with the Open Birdsite DB API.
    *   **Contents Overview:** Contains functions to fetch tweet threads (main tweet and replies) given a tweet ID. Includes URL parsing for tweet ID, API request construction, authentication, and data fetching. *Currently implements tweet ID extraction and basic API call structure to `/rpc/get_main_thread`. Needs response structure analysis and data mapping.*
    *   **Interactions:** Called by `app.py`. Uses `requests` library. Reads API token from `.env`.

*   **`llm_analyzer_suite.py`**:
    *   **Purpose:** Module for performing LLM-based analysis (classification and summarization) on tweet data.
    *   **Contents Overview:** Initializes an Anthropic client using an API key from `.env`. Defines `analyze_tweets(main_post_data, replies_data)` which:
        *   Classifies each reply using `classify_reply` helper for sentiment, agreement, and question status (with JSON output requested from LLM).
        *   Groups replies based on these classifications.
        *   Generates a summary for each group of replies using `summarize_text_anthropic` helper.
        *   Generates an overall summary of the discourse based on the main post and cluster summaries.
        *   Returns a structured dictionary containing the main post details, overall summary, and detailed cluster information (summary and tweets within each cluster).
        *   Includes error handling for LLM calls and basic parsing of LLM responses.
    *   **Interactions:** Called by `app.py`. Uses the `anthropic` library. Reads `ANTHROPIC_API_KEY` from `.env`.

*   **`requirements.txt`**:
    *   **Purpose:** Lists Python project dependencies.
    *   **Contents Overview:** Includes Flask, requests, python-dotenv, anthropic.
    *   **Interactions:** Used by `pip install -r requirements.txt` to set up the environment.

*   **`.env`**:
    *   **Purpose:** Stores environment variables, specifically API keys.
    *   **Contents Overview:** `ANTHROPIC_API_KEY`, `OPEN_BIRDSITE_DB_TOKEN`. **Note: This file is in `.gitignore` and should not be committed to version control.**
    *   **Interactions:** Read by `python-dotenv` in `app.py`, `tweet_fetcher.py`, and `llm_analyzer_suite.py`.

*   **`test_anthropic.py`**:
    *   **Purpose:** A small script to test the Anthropic API key and basic client functionality independently of the Flask app.
    *   **Contents Overview:** Loads `ANTHROPIC_API_KEY` from `.env`, initializes the Anthropic client, and attempts a simple `messages.create` call. Prints success or error messages to the console.
    *   **Interactions:** Reads `.env`. Uses `anthropic` and `python-dotenv` libraries. Not directly part of the Flask application flow.

*   **`llm-docs/dev-plan.md`**:
    *   **Purpose:** Outlines the development plan, phases, and tasks for the project.
    *   **Contents Overview:** Detailed steps for building the application.
    *   **Interactions:** Reference document for developers and llms.

*   **`llm-docs/directory-map.md`** (this file):
    *   **Purpose:** Describes the project's file and directory structure.
    *   **Contents Overview:** This mapping.
    *   **Interactions:** Reference document for developers and llms.

*   **`static/`** (directory):
    *   **Purpose:** Contains static assets for the frontend (CSS, JavaScript, images).
    *   **Interactions:** Served by Flask.

*   **`templates/`** (directory):
    *   **Purpose:** Contains HTML templates for the frontend.
    *   **Interactions:** Rendered by Flask.

## `static/` Directory

*   **`style.css`**:
    *   **Purpose:** Main CSS file for styling the web application.
    *   **Contents Overview:** Styles for page layout (body, container), input elements (text input, button), loading indicator, error messages, and the overall analysis results section. Includes styles for displaying the main post, overall summary, and individual cluster columns/boxes. Defines how tweets within clusters are styled (using `.tweet-item`). Base styles were copied from `old_code/static/style.css` and adapted for the new HTML structure and class names. Contains commented-out sentiment-specific color classes for clusters that can be reactivated later.
    *   **Interactions:** Linked in `templates/index.html`.

*   **`script.js`**:
    *   **Purpose:** Frontend JavaScript for user interactions and dynamic content updates.
    *   **Contents Overview:** Adds an event listener to the 'Analyze' button. On click, it retrieves the tweet URL, shows a loading indicator, and sends a POST request to the `/api/analyze_url` backend endpoint. It then handles the JSON response by calling functions to display the main post (`displayMainPost`), overall summary (`displayOverallSummary`), and reply clusters (`displayClusters`). Includes helper functions for showing/hiding loading indicators and error messages, and for clearing previous results. The display functions currently use basic HTML placeholders and will be adapted later to use a `<tweet-component>` for rendering tweets.
    *   **Interactions:** Included in `templates/index.html`. Makes API calls to `app.py`. Manipulates DOM elements in `index.html` to display results.

## `templates/` Directory

*   **`index.html`**:
    *   **Purpose:** The main HTML page for the application.
    *   **Contents Overview:** Contains a title, link to `static/style.css`, an input field (`tweetUrlInput`) for the tweet URL, an "Analyze" button (`analyzeButton`), a loading indicator (`loadingIndicator`), an error message div (`error-message`), and placeholder divs for displaying the original tweet (`main-post-display`), overall summary (`overall-summary`), and reply clusters (`clusters-columns-container`). Includes a script tag for `static/script.js`. Uses Flask's `url_for` for static asset linking.
    *   **Interactions:** Served by `app.py` at the root URL. Uses `static/style.css` for styling and `static/script.js` for dynamic functionality and API calls.

*   `.env.example`: Example environment variable file.
*   `config.json`: (Not committed, created locally) Configuration file for enabling/disabling features like AI analysis and graph visualization. Follows the structure of `config.example.json`.
*   `config.example.json`: Example configuration file showing available feature toggles.

## llm-docs/