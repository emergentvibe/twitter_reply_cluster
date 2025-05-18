# Twitter Reply Cluster Analyzer

This project is a web application that analyzes Twitter (now X) conversations. It fetches a main tweet, its replies, and any quote tweets. It then uses an LLM (via Anthropic's API) to classify the discourse into sentiment/agreement clusters and provides summaries for each cluster and an overall summary of the conversation.

## Features

*   Fetches main tweet, replies, and quote tweets using an open Twitter data archive.
*   Classifies replies and quote tweets based on sentiment (positive, negative, neutral) and agreement (agrees, disagrees, neutral) towards the main post.
*   Generates summaries for each cluster of replies/quote tweets.
*   Provides an overall summary of the entire discourse.
*   Displays results in a user-friendly web interface with collapsible sections for tweet details.
*   Quote tweets are identified and marked in the UI.

## Technology Stack

*   **Backend:** Python with Flask
*   **Data Fetching (Twitter/X):** Data accessed via the Supabase client library, sourced from an open Twitter data archive (see below).
*   **LLM Interaction:** Anthropic API (Claude Haiku model) via the Python `anthropic` SDK.
*   **Frontend:** Vanilla HTML, CSS, and JavaScript.
*   **Dependency Management:** `requirements.txt` for Python packages.

## Data Source & Big Thanks!

This project taps into the awesome **Community Archive** project for its Twitter data. It's an open initiative making a huge amount of Twitter history available for cool projects like this one!

A big shout-out to everyone behind the Community Archive – your work to make this data open is super appreciated!

*   **Check out the Community Archive on GitHub:** [https://github.com/TheExGenesis/community-archive](https://github.com/TheExGenesis/community-archive)
*   The specific data endpoint used by this project is the Supabase instance configured in your `.env` file (`OPEN_BIRDSITE_DB_BASE_URL`).

## Project Structure

(Refer to `llm-docs/directory-map.md` for a detailed overview of files and their purposes.)

*   `app.py`: Main Flask application, API endpoint.
*   `tweet_fetcher.py`: Handles fetching data from the Open Birdsite DB.
*   `llm_analyzer_suite.py`: Handles interaction with the Anthropic LLM for classification and summarization.
*   `static/`: Contains frontend CSS (`style.css`) and JavaScript (`script.js`).
*   `templates/`: Contains frontend HTML (`index.html`).
*   `requirements.txt`: Python dependencies.
*   `.env`: (To be created by user) For API keys and environment variables.
*   `dev-plan.md`: Development plan and progress.
*   `directory-map.md`: Detailed map of project files.

## Setup and Installation

**Set up environment variables:**
Create a `.env` file in the project root and add your API keys:
```env
OPEN_BIRDSITE_DB_BASE_URL="YOUR_SUPABASE_URL"
OPEN_BIRDSITE_DB_TOKEN="YOUR_SUPABASE_PUBLIC_ANON_KEY"
ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY"
```
Replace the placeholder values with your actual credentials.

## Running the Application

1.  **Ensure your virtual environment is activated.**
2.  **Run the Flask development server:**
    ```bash
    flask run
    ```
3.  Open your web browser and navigate to `http://127.0.0.1:5000`.

## Development

*   Update `dev-plan.md` with progress and next steps.
*   Update `directory-map.md` when adding or significantly changing files. 