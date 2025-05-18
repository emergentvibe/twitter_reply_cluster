import os
import anthropic
from dotenv import load_dotenv
import json
import re

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY.startswith("YOUR_ANTHR") or ANTHROPIC_API_KEY == "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
    print(f"Error: ANTHROPIC_API_KEY not found or is a placeholder: {ANTHROPIC_API_KEY}. Please set it correctly in .env.")
    anthropic_client = None
else:
    try:
        anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    except Exception as e:
        print(f"Error initializing Anthropic client: {e}")
        anthropic_client = None

# Placeholder for actual model name, e.g., "claude-3-opus-20240229" or a smaller/faster one for classification.
# Consider different models for classification vs. summarization if needed.
DEFAULT_MODEL_NAME = "claude-3-haiku-20240307" 
# DEFAULT_MODEL_NAME = "claude-2" # Example, choose appropriate model

def classify_reply(original_post_text: str, reply_text: str, parent_tweet_text: str | None = None) -> dict:
    """
    Classifies a single reply using the LLM.
    Categories: sentiment (positive, negative, neutral), agreement (agrees, disagrees, neutral/unclear).
    """
    if not anthropic_client:
        return {"error": "Anthropic client not initialized."}

    prompt_parts = [
        f"Original Post: {original_post_text}"
    ]
    if parent_tweet_text:
        prompt_parts.append(f"Parent Tweet to this Reply: {parent_tweet_text}")
    
    prompt_parts.append(f"Reply Text: {reply_text}")
    prompt_parts.append("\nAnalyze the Reply in the context of the Original Post (and Parent Tweet, if provided). Please think first about the sentiment of the reply, then the agreement with the Original Post, then respond with the json. Classify the reply based on the following categories:")

    prompt_parts.append("1. Sentiment: Is the reply positive, negative, or neutral?")
    prompt_parts.append("2. Agreement: Does the reply agree, disagree, or is it neutral/unclear towards the Original Post (or Parent Tweet if more relevant)?")
    prompt_parts.append("\nPlease provide your answer as a JSON object with two keys: 'sentiment', and 'agreement'.")
    prompt_parts.append("For 'sentiment', use one of: 'positive', 'negative', 'neutral'.")
    prompt_parts.append("For 'agreement', use one of: 'agrees', 'disagrees', 'neutral'.")
    prompt_parts.append("Example JSON response: {\"sentiment\": \"positive\", \"agreement\": \"agrees\"}")
    
    full_prompt = "\n\n".join(prompt_parts)

    try:
        raw_llm_response = anthropic_client.messages.create(
            model=DEFAULT_MODEL_NAME,
            max_tokens=150, # Adjusted for JSON output
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        ).content[0].text
        
        print(f"--- Raw LLM Response for Classification (reply: '{reply_text[:50]}...') ---\n{raw_llm_response}\n--------------------------------------------------")

        # Attempt to extract JSON from the response
        classifications = None
        try:
            # First, try direct parsing
            classifications = json.loads(raw_llm_response)
        except json.JSONDecodeError as e_direct:
            print(f"Direct JSON parsing failed: {e_direct}. Attempting to extract from markdown or other text.")
            # Try to find JSON within markdown code blocks or as a substring
            match = re.search(r"```json\n({.*?})\n```", raw_llm_response, re.DOTALL)
            if not match: # Try without 'json' hint
                match = re.search(r"```\n({.*?})\n```", raw_llm_response, re.DOTALL)
            if not match: # Try finding any valid JSON object as a substring
                match = re.search(r"({.*?})", raw_llm_response, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                try:
                    classifications = json.loads(json_str)
                    print(f"Successfully extracted and parsed JSON: {json_str}")
                except json.JSONDecodeError as e_extract:
                    print(f"Failed to parse extracted JSON string '{json_str[:100]}...': {e_extract}")
                    raise ValueError(f"Could not parse extracted JSON. Original error: {e_extract}. Raw response was: {raw_llm_response}") from e_extract
            else:
                print("No JSON object found in the response using regex.")
                raise ValueError(f"No parsable JSON found in LLM response. Direct parse error: {e_direct}. Raw response: {raw_llm_response}") from e_direct

        if classifications is None:
            raise ValueError("Classification result is None after attempts to parse.")

        # Validate structure and values (optional but good practice)
        if not all(k in classifications for k in ['sentiment', 'agreement']):
            raise ValueError("Missing one or more required keys in LLM classification response.")

        return classifications
    except json.JSONDecodeError as je: # Catch specifically if extraction fails
        print(f"JSONDecodeError during LLM classification for reply '{reply_text[:50]}...': {je}")
        print(f"Problematic LLM response was: {raw_llm_response}")
        return {
            "sentiment": "error_json_decode",
            "agreement": "error_json_decode",
            "error_detail": str(je),
            "raw_response": raw_llm_response
        }
    except Exception as e:
        print(f"Error during LLM classification for reply '{reply_text[:50]}...': {e}")
        return {
            "sentiment": "error_processing",
            "agreement": "error_processing",
            "error_detail": str(e)
        }

def summarize_text_anthropic(text_to_summarize: str, context: str = "", max_tokens: int = 150) -> str:
    """
    Generates a summary for the given text using the Anthropic API.
    """
    if not anthropic_client:
        return "Error: Anthropic client not initialized."

    prompt = f"Please provide a concise summary of the following text. {context} Text to summarize: \n{text_to_summarize}"
    if not text_to_summarize.strip():
        return "No text provided for summarization."
        
    try:
        response = anthropic_client.messages.create(
            model=DEFAULT_MODEL_NAME, # Or a model better suited for summarization
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        ).content[0].text
        return response.strip()
    except Exception as e:
        print(f"Error during LLM summarization: {e}")
        return f"Error during summarization: {str(e)}"


def analyze_tweets(main_post_data: dict, replies_data: list[dict]) -> dict:
    """
    Analyzes tweet data (main post and replies) using an LLM for classification and summarization.
    """
    if not anthropic_client:
        return {"error": "Anthropic client not initialized, cannot perform analysis."}

    if not main_post_data:
        return {"error": "Main post data is missing."}
    
    main_post_text = main_post_data.get('text', '')

    # --- Define all possible cluster categories and their order ---
    sentiments = ["positive", "neutral", "negative"]
    agreements = ["agrees", "neutral", "disagrees"]
    
    # --- Initialize all potential clusters ---
    clusters = {}
    for s in sentiments:
        for a in agreements:
            cluster_key = f"{s}_{a}"
            clusters[cluster_key] = {"summary": "No replies in this cluster.", "tweets": []}
    # Add a cluster for skipped/empty tweets
    clusters["skipped_empty"] = {"summary": "Replies that were empty.", "tweets": []}
    # Add a cluster for classification errors if needed (though currently handled by not adding to clusters)
    # clusters["error_processing"] = {"summary": "Replies that had a classification error.", "tweets": []}


    # --- Classification Sub-Phase ---
    classified_replies = []
    for reply in replies_data:
        reply_text = reply.get('text', '')
        if not reply_text.strip(): # Skip empty replies
            reply['llm_classification'] = {'sentiment': 'skipped', 'agreement': 'empty'} # Keep distinct from LLM 'neutral'
            # Add to a specific cluster for empty/skipped replies
            clusters["skipped_empty"]["tweets"].append(reply)
            classified_replies.append(reply) # Still add to this list for potential other uses
            continue

        parent_tweet_text = None 
        classifications = classify_reply(
            original_post_text=main_post_text,
            reply_text=reply_text,
            parent_tweet_text=parent_tweet_text
        )
        reply['llm_classification'] = classifications
        classified_replies.append(reply)

    # --- Populate Pre-defined Clusters ---
    for reply in classified_replies:
        classification = reply.get('llm_classification', {})
        
        # Skip replies that were already handled (empty ones) or had errors during classification itself
        if classification.get('sentiment') == 'skipped' or classification.get('error_detail'):
            # If error_detail exists and we want to explicitly cluster them:
            # if classification.get('error_detail'):
            #     clusters["error_processing"]["tweets"].append(reply)
            continue

        sentiment = classification.get('sentiment', 'unknown_sentiment')
        agreement = classification.get('agreement', 'unknown_agreement')
        
        # Ensure we only use defined sentiment/agreement values for keys
        if sentiment not in sentiments: sentiment = "unknown_sentiment_value" # Should not happen if LLM follows prompt
        if agreement not in agreements: agreement = "unknown_agreement_value" # Should not happen
            
        cluster_key = f"{sentiment}_{agreement}"
        
        if cluster_key in clusters: # Add to pre-defined clusters
            clusters[cluster_key]["tweets"].append(reply)
        else:
            # This case is for classifications that don't match the predefined (e.g. if LLM returns something unexpected)
            # Or if we have unknown_sentiment_value / unknown_agreement_value
            if cluster_key not in clusters: # Create a new cluster for unexpected values
                 clusters[cluster_key] = {"summary": "Replies with unexpected classification values.", "tweets": []}
            clusters[cluster_key]["tweets"].append(reply)


    # --- Summarization Sub-Phase ---
    cluster_details_output = {} # This will become the new 'clusters' for the output
    all_cluster_summaries_text = []

    # Iterate in the defined order for consistent output structure
    all_cluster_keys_ordered = [f"{s}_{a}" for s in sentiments for a in agreements]
    if "skipped_empty" in clusters and clusters["skipped_empty"]["tweets"]: # Add if populated
        all_cluster_keys_ordered.append("skipped_empty")
    # Add any other dynamically created cluster keys (e.g., from errors or unexpected LLM responses)
    for key in clusters.keys():
        if key not in all_cluster_keys_ordered:
            all_cluster_keys_ordered.append(key)


    for cluster_name in all_cluster_keys_ordered:
        data = clusters.get(cluster_name) # Get data from our working 'clusters' dict
        if not data: # Should not happen if all_cluster_keys_ordered is built from clusters.keys()
            continue 

        # If the cluster is predefined as empty and still has no tweets, its summary is already set.
        # Only generate a new summary if there are tweets.
        current_summary = data["summary"] # Keep pre-defined summary for empty clusters
        if data["tweets"]:
            texts_for_summary = "\n---\n".join([t.get('text','') for t in data["tweets"][:20]]) # Summarize first 20 tweets
            if texts_for_summary.strip(): # Only summarize if there's actual text
                cluster_summary_prompt_context = f"This cluster represents replies classified as: {cluster_name.replace('_', ' ')}. Summarize these replies in relation to the original post: '{main_post_text[:100]}...'"
                summary = summarize_text_anthropic(texts_for_summary, context=cluster_summary_prompt_context, max_tokens=100)
                current_summary = summary # Update summary if generated
            elif not data["summary"]: # If no predefined summary and no text, set a default
                 current_summary = "No text in replies to summarize."

        cluster_details_output[cluster_name] = {"summary": current_summary, "tweets": data["tweets"]}
        if current_summary and not current_summary.startswith("Error") and current_summary != "No replies in this cluster." and current_summary != "Replies that were empty.":
            all_cluster_summaries_text.append(f"Cluster ({cluster_name.replace('_', ' ')}): {current_summary}")

    # --- Enhanced Overall Discourse Summary Generation ---
    overall_summary_input_parts = [f"Original Post: \"{main_post_text}\"\n"]
    overall_summary_input_parts.append("Key Discussion Points based on Reply Clusters (including their summaries and a prominent reply if available):\n")

    for cluster_name in all_cluster_keys_ordered: # all_cluster_keys_ordered ensures a logical flow
        cluster_data = cluster_details_output.get(cluster_name)
        
        if not cluster_data: 
            continue

        cluster_summary_text = cluster_data.get("summary", "No summary provided for this cluster.")
        
        # Refined handling of placeholder summaries for the overall prompt
        is_placeholder_summary = (
            cluster_summary_text.startswith("Error") or 
            cluster_summary_text == "No replies in this cluster." or 
            cluster_summary_text == "Replies that were empty." or 
            cluster_summary_text == "No text in replies to summarize." or 
            cluster_summary_text == "No text provided for summarization."
        )

        if is_placeholder_summary:
             cluster_description_for_prompt = f"The '{cluster_name.replace('_', ' ')}' cluster had few/no replies or a summarization issue."
        else:
            cluster_description_for_prompt = f"Summary of '{cluster_name.replace('_', ' ')}' replies: \"{cluster_summary_text}\""

        top_tweet_for_prompt = ""
        if cluster_data.get("tweets") and len(cluster_data["tweets"]) > 0:
            sorted_tweets = sorted(cluster_data["tweets"], key=lambda t: t.get('like_count', 0), reverse=True)
            # Ensure there is a top tweet and it has more than 0 likes
            if sorted_tweets and sorted_tweets[0].get('like_count', 0) > 0: 
                top_tweet_text_full = sorted_tweets[0].get('text', '')
                top_tweet_for_prompt = f"  - A prominent reply in this cluster: \"{top_tweet_text_full[:150]}{'...' if len(top_tweet_text_full) > 150 else ''}\""

        overall_summary_input_parts.append(f"\nCluster: {cluster_name.replace('_', ' ')}")
        overall_summary_input_parts.append(f"  - {cluster_description_for_prompt}")
        if top_tweet_for_prompt:
            overall_summary_input_parts.append(top_tweet_for_prompt)

    overall_summary_prompt_input_text = "\n".join(overall_summary_input_parts)

    final_overall_summary_context = (
        "You are an AI assistant creating a summary of a Twitter discussion. "
        "Based on the Original Post, and the provided summaries and prominent replies from different clusters of user responses, "
        "generate a concise overall summary of the entire discourse. "
        "Focus on the main viewpoints, agreements, and disagreements highlighted across the clusters and their top examples."
    )

    overall_summary = summarize_text_anthropic(
        text_to_summarize=overall_summary_prompt_input_text,
        context=final_overall_summary_context,
        max_tokens=300 
    )

    # --- Output Construction ---
    # (Simplified based on dev-plan, ensure all fields are populated)
    output = {
        "main_post_id": main_post_data.get('id'),
        "main_post_text": main_post_data.get('text'),
        "main_post_author_handle": main_post_data.get('author_handle'),
        "main_post_author_display_name": main_post_data.get('author_display_name'), # Added
        "main_post_likes": main_post_data.get('like_count'),
        "main_post_timestamp": main_post_data.get('timestamp'),
        "main_post_avatar_url": main_post_data.get('avatar_url'),
        "overall_summary": overall_summary,
        "cluster_details": cluster_details_output 
    }
    return output

if __name__ == '__main__':
    # Example Usage (requires .env to be set up with ANTHROPIC_API_KEY)
    if not anthropic_client:
        print("Anthropic client not initialized. Cannot run example.")
    else:
        print("Anthropic client initialized. Running example analysis...")
        sample_main_post = {
            "id": "123", 
            "text": "I think AI is the future of technology! What do you all think?",
            "author_handle": "@testuser",
            "author_display_name": "Test User",
            "like_count": 100,
            "timestamp": "2023-01-01T12:00:00Z",
            "avatar_url": "http://example.com/avatar.png"
        }
        sample_replies = [
            {"id": "124", "text": "I totally agree! It's going to revolutionize everything.", "like_count": 10, "timestamp": "2023-01-01T12:05:00Z", "author_handle": "@replyguy1", "author_display_name": "Reply Guy 1", "avatar_url": "http://example.com/avatar1.png"},
            {"id": "125", "text": "I'm not so sure, there are many ethical concerns.", "like_count": 5, "timestamp": "2023-01-01T12:06:00Z", "author_handle": "@skeptic", "author_display_name": "Skeptic Gal", "avatar_url": "http://example.com/avatar2.png"},
            {"id": "126", "text": "What kind of AI are you talking about? Generative AI? AGI?", "like_count": 3, "timestamp": "2023-01-01T12:07:00Z", "author_handle": "@questioner", "author_display_name": "Curious George", "avatar_url": "http://example.com/avatar3.png"},
            {"id": "127", "text": "Strongly disagree. It will lead to job losses.", "like_count": 2, "timestamp": "2023-01-01T12:08:00Z", "author_handle": "@pessimist", "author_display_name": "Pessimistic Pete", "avatar_url": "http://example.com/avatar4.png"},
            {"id": "128", "text": "", "like_count": 0, "timestamp": "2023-01-01T12:09:00Z", "author_handle": "@empty", "author_display_name": "Empty", "avatar_url": "http://example.com/avatar5.png"}, # Empty reply
            {"id": "129", "text": "This is amazing news! AI will solve so many problems!", "like_count": 15, "timestamp": "2023-01-01T12:10:00Z", "author_handle": "@optimist", "author_display_name": "Optimistic Olivia", "avatar_url": "http://example.com/avatar6.png"},
        ]

        analysis_results = analyze_tweets(sample_main_post, sample_replies)
        
        print("\n--- Analysis Results ---")
        print(json.dumps(analysis_results, indent=2))

        # Test classification directly
        print("\n--- Direct Classification Test ---")
        test_classification = classify_reply(sample_main_post['text'], sample_replies[0]['text'])
        print(f"Classification for '{sample_replies[0]['text']}': {json.dumps(test_classification, indent=2)}")
        
        test_classification_q = classify_reply(sample_main_post['text'], sample_replies[2]['text'])
        print(f"Classification for '{sample_replies[2]['text']}': {json.dumps(test_classification_q, indent=2)}")

        # Test summarizer directly
        print("\n--- Direct Summarization Test ---")
        test_summary = summarize_text_anthropic("This is a long piece of text about various things that happened today. The weather was nice, and the birds were singing. We went to the park and had a picnic. It was a good day overall, full of joy and laughter.", "Test context for summarization")
        print(f"Summary: {test_summary}") 