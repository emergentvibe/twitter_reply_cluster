import os
import re
from dotenv import load_dotenv
from supabase import create_client, Client
from postgrest import APIError as PostgrestAPIError  # Import for specific exception handling
from httpx import HTTPStatusError # For http errors from underlying client
import json
import asyncio

load_dotenv(override=True)

OPEN_BIRDSITE_DB_BASE_URL = os.getenv("OPEN_BIRDSITE_DB_BASE_URL")
OPEN_BIRDSITE_DB_TOKEN = os.getenv("OPEN_BIRDSITE_DB_TOKEN")

# Initialize Supabase client
supabase_client: Client | None = None

# Check for placeholder or missing Supabase credentials
if not OPEN_BIRDSITE_DB_BASE_URL or OPEN_BIRDSITE_DB_BASE_URL.startswith("YOUR_SUPABASE_URL"):
    print(f"Error: OPEN_BIRDSITE_DB_BASE_URL not found or is a placeholder: {OPEN_BIRDSITE_DB_BASE_URL}. Please set it correctly in .env.")
    supabase_client = None # Ensure client is None if URL is bad
elif not OPEN_BIRDSITE_DB_TOKEN or OPEN_BIRDSITE_DB_TOKEN.startswith("YOUR_SUPABASE_TOKEN"):
    print(f"Error: OPEN_BIRDSITE_DB_TOKEN not found or is a placeholder: {OPEN_BIRDSITE_DB_TOKEN}. Please set it correctly in .env.")
    supabase_client = None # Ensure client is None if Token is bad
else:
    try:
        supabase_client = create_client(OPEN_BIRDSITE_DB_BASE_URL, OPEN_BIRDSITE_DB_TOKEN)
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        supabase_client = None

if not supabase_client:
    print("Warning: Supabase client could not be initialized. Tweet fetching will fail.")

def extract_tweet_id_from_url(tweet_url: str) -> str | None:
    """
    Extracts the tweet ID from various Twitter/X URL formats.
    Example URLs:
    - https://twitter.com/username/status/1234567890123456789
    - https://x.com/username/status/1234567890123456789
    - https://x.com/username/status/1234567890123456789?s=20
    """
    match = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", tweet_url)
    if match:
        return match.group(1)
    return None

async def _get_root_conversation_id_async(tweet_id_str: str) -> str | None:
    """Fetches the root conversation_id for a given tweet_id."""
    if not supabase_client:
        print("Error: Supabase client not initialized in _get_root_conversation_id_async.")
        return None
    try:
        # print(f"Fetching conversation_id for tweet_id: {tweet_id_str}")
        response = supabase_client.table("conversations").select("conversation_id").eq("tweet_id", tweet_id_str).maybe_single().execute()
        if response.data and response.data.get("conversation_id"):
            # print(f"Found root_conversation_id: {response.data['conversation_id']} for tweet_id: {tweet_id_str}")
            return response.data["conversation_id"]
        else:
            # Fallback: if not in conversations table, assume the tweet_id itself is the conversation_id (common for root posts)
            # print(f"No specific conversation_id found for {tweet_id_str} in 'conversations' table. Assuming it's a root tweet, using its own ID as conversation_id.")
            return tweet_id_str 
    except PostgrestAPIError as e:
        print(f"PostgrestAPIError fetching conversation_id for {tweet_id_str}: {e.message}")
        return None # Or fallback to tweet_id_str if that's preferred on API error too
    except Exception as e:
        print(f"Unexpected error fetching conversation_id for {tweet_id_str}: {e}")
        return None

async def _fetch_conversation_tweets_raw_async(conversation_id_to_fetch: str) -> list[dict] | dict:
    """Fetches all raw tweets for a given conversation_id from the tweets_w_conversation_id view."""
    if not supabase_client:
        print("Error: Supabase client not initialized in _fetch_conversation_tweets_raw_async.")
        return {"error": "Supabase client not initialized."}
    
    print(f"Fetching all tweets for conversation_id: {conversation_id_to_fetch} from 'tweets_w_conversation_id' view.")
    try:
        response = supabase_client.table("tweets_w_conversation_id").select("*").eq("conversation_id", conversation_id_to_fetch).order("created_at", desc=False).execute()
        
        if response is None:
            print(f"Error: supabase_client.execute() returned None when fetching conversation tweets for {conversation_id_to_fetch}.")
            return {"error": "API call to fetch conversation tweets returned None unexpectedly."}
        
        if response.data:
            if isinstance(response.data, list):
                # print(f"Successfully fetched {len(response.data)} raw tweets for conversation_id: {conversation_id_to_fetch}")
                return response.data
            else:
                print(f"Unexpected data structure from 'tweets_w_conversation_id' for {conversation_id_to_fetch}: {type(response.data)}")
                return {"error": "Unexpected data structure from API.", "details": str(response.data)[:500]}
        else:
            # print(f"No tweets found in 'tweets_w_conversation_id' for conversation_id: {conversation_id_to_fetch}. Empty list returned by API.")
            return [] # Return empty list if no data
            
    except PostgrestAPIError as e:
        print(f"PostgrestAPIError fetching tweets for conversation {conversation_id_to_fetch}: {e.message}")
        return {"error": f"PostgREST API error: {e.message}", "code": e.code, "details": e.details, "hint": e.hint, "status_code": getattr(e, 'status_code', None)}
    except HTTPStatusError as e:
        print(f"HTTPStatusError fetching tweets for conversation {conversation_id_to_fetch}: {e.response.status_code} - {e.response.text}")
        return {"error": f"HTTP Status Error: {e.response.status_code}", "details": e.response.text}
    except Exception as e:
        print(f"Unexpected error fetching tweets for conversation {conversation_id_to_fetch}: {type(e).__name__} - {e}")
        return {"error": f"An unexpected client-side error: {type(e).__name__} - {str(e)}"}

async def _fetch_batch_account_details_async(account_ids: list[str]) -> dict[str, dict]:
    """Fetches account details for a list of account_ids in a single batch call."""
    if not supabase_client or not account_ids:
        return {}
    try:
        # print(f"Fetching batch account details for {len(account_ids)} IDs: {account_ids[:5]}...")
        response = supabase_client.table("account").select("account_id, username, account_display_name").in_("account_id", account_ids).execute()
        if response and response.data:
            return {acc['account_id']: acc for acc in response.data}
        elif response is None:
            print(f"Error: supabase_client.execute() returned None when fetching batch account details.")
        # else: 
            # print(f"No data returned for batch account details. IDs: {account_ids[:5]}...")
        return {}
    except PostgrestAPIError as e:
        print(f"PostgrestAPIError fetching batch account details: {e.message}")
        return {}
    except Exception as e:
        print(f"Unexpected error fetching batch account details: {e}")
        return {}

async def _fetch_batch_profile_details_async(account_ids: list[str]) -> dict[str, dict]:
    """Fetches profile details for a list of account_ids in a single batch call."""
    if not supabase_client or not account_ids:
        return {}
    try:
        # print(f"Fetching batch profile details for {len(account_ids)} IDs: {account_ids[:5]}...")
        response = supabase_client.table("profile").select("account_id, avatar_media_url").in_("account_id", account_ids).execute()
        if response and response.data:
            return {prof['account_id']: prof for prof in response.data}
        elif response is None:
             print(f"Error: supabase_client.execute() returned None when fetching batch profile details.")
        # else:
            # print(f"No data returned for batch profile details. IDs: {account_ids[:5]}...")
        return {}
    except PostgrestAPIError as e:
        print(f"PostgrestAPIError fetching batch profile details: {e.message}")
        return {}
    except Exception as e:
        print(f"Unexpected error fetching batch profile details: {e}")
        return {}

def _enrich_single_tweet(raw_tweet_from_view: dict, accounts_map: dict, profiles_map: dict) -> dict:
    """Enriches a single raw tweet using pre-fetched account and profile details maps."""
    account_id = raw_tweet_from_view.get("account_id")
    tweet_id = raw_tweet_from_view.get("tweet_id")

    account_details = accounts_map.get(account_id) if account_id else None
    profile_details = profiles_map.get(account_id) if account_id else None

    enriched_data = {
        'id': tweet_id,
        'text': raw_tweet_from_view.get('full_text'),
        'timestamp': raw_tweet_from_view.get('created_at'),
        'like_count': raw_tweet_from_view.get('favorite_count', 0),
        'retweet_count': raw_tweet_from_view.get('retweet_count', 0),
        'reply_to_tweet_id': raw_tweet_from_view.get('reply_to_tweet_id'),
        'conversation_id': raw_tweet_from_view.get('conversation_id'),
        'author_handle': None,
        'author_display_name': None,
        'avatar_url': None,
        'account_id': account_id 
    }

    if account_details:
        enriched_data['author_handle'] = account_details.get('username')
        enriched_data['author_display_name'] = account_details.get('account_display_name')
    
    if profile_details:
        enriched_data['avatar_url'] = profile_details.get('avatar_media_url')
    
    return enriched_data

async def fetch_enriched_tweet_thread(tweet_url: str) -> list[dict] | dict:
    """
    Fetches an entire tweet conversation (main tweet and all replies) 
    and enriches each tweet with author and profile details.
    """
    if not supabase_client:
        return {"error": "Supabase client not initialized."}

    extracted_tweet_id = extract_tweet_id_from_url(tweet_url)
    if not extracted_tweet_id:
        return {"error": "Could not extract tweet ID from URL."}
    
    print(f"Extracted Tweet ID: {extracted_tweet_id} from URL: {tweet_url}")

    root_conversation_id = await _get_root_conversation_id_async(extracted_tweet_id)
    if not root_conversation_id:
        # This case should ideally be handled by the fallback in _get_root_conversation_id_async
        # or indicate a more significant issue if even the fallback (extracted_id itself) fails.
        print(f"Critical: Could not determine root conversation ID for extracted_tweet_id: {extracted_tweet_id}")
        return {"error": f"Could not determine root conversation ID for {extracted_tweet_id}."}
    
    # print(f"Determined root conversation ID: {root_conversation_id}")

    raw_tweets_data = await _fetch_conversation_tweets_raw_async(root_conversation_id)

    if isinstance(raw_tweets_data, dict) and "error" in raw_tweets_data:
        return raw_tweets_data # Return error from raw fetch
    
    if not isinstance(raw_tweets_data, list):
        print(f"Fetch for conversation {root_conversation_id} did not return a list. Type: {type(raw_tweets_data)}")
        return {"error": "Tweet conversation fetch did not return a list."}
    
    if not raw_tweets_data:
        print(f"No tweets found for conversation ID: {root_conversation_id}. It might be an invalid ID or a private/deleted conversation.")
        return [] # Return empty list if conversation is empty

    # Batch fetch account and profile details
    unique_account_ids = list(set(tweet.get("account_id") for tweet in raw_tweets_data if tweet.get("account_id")))
    
    # print(f"Found {len(unique_account_ids)} unique account IDs for batch fetching.")
    # accounts_map, profiles_map = {}, {}
    # if unique_account_ids:
    #     accounts_map_task = _fetch_batch_account_details_async(unique_account_ids)
    #     profiles_map_task = _fetch_batch_profile_details_async(unique_account_ids)
    #     accounts_map, profiles_map = await asyncio.gather(accounts_map_task, profiles_map_task)
    
    accounts_map = {}
    profiles_map = {}
    if unique_account_ids:
        # These batch calls are internally synchronous with supabase client but defined as async for gather
        # If they were truly async (e.g. direct httpx), gather would be highly effective.
        # For now, it still organizes the calls.
        batch_results = await asyncio.gather(
            _fetch_batch_account_details_async(unique_account_ids),
            _fetch_batch_profile_details_async(unique_account_ids),
            return_exceptions=True # Important to handle potential errors in batch calls
        )
        
        if isinstance(batch_results[0], dict):
            accounts_map = batch_results[0]
        elif isinstance(batch_results[0], Exception):
            print(f"Error fetching batch account details: {batch_results[0]}")

        if isinstance(batch_results[1], dict):
            profiles_map = batch_results[1]
        elif isinstance(batch_results[1], Exception):
            print(f"Error fetching batch profile details: {batch_results[1]}")

    enriched_tweets = []
    for raw_tweet in raw_tweets_data:
        enriched_tweets.append(_enrich_single_tweet(raw_tweet, accounts_map, profiles_map))

    return enriched_tweets

async def fetch_quote_tweets(supabase_client: Client, tweet_url: str) -> list[dict]:
    """
    Fetches tweets that quote the original tweet.
    It identifies quote tweets by looking for tweets that contain the URL of the original tweet
    but are not direct replies to it.
    """
    if not supabase_client:
        print("Error: Supabase client not initialized in fetch_quote_tweets.")
        return []

    if not tweet_url:
        print("Error: Tweet URL is required to fetch quote tweets.")
        return []

    extracted_tweet_id = extract_tweet_id_from_url(tweet_url)
    if not extracted_tweet_id:
        return {"error": "Could not extract tweet ID from URL."}
    
    print(f"Extracted Tweet ID: {extracted_tweet_id} from URL: {tweet_url}")

    # The enriched_tweets view already joins tweets with accounts, profiles, and quote_tweets.
    # We can directly query it to find tweets that quote our extracted_tweet_id.
    # The 'quoted_tweet_id' column in 'enriched_tweets' comes from the 'quote_tweets' join
    # and indicates the ID of the tweet being quoted by the row's 'tweet_id'.

    print(f"Fetching quote tweets for original tweet ID: {extracted_tweet_id} using 'enriched_tweets' view.")

    try:
        response = supabase_client.table("enriched_tweets") \
            .select("tweet_id, account_id, username, account_display_name, created_at, full_text, retweet_count, favorite_count, reply_to_tweet_id, quoted_tweet_id, avatar_media_url") \
            .eq("quoted_tweet_id", extracted_tweet_id) \
            .execute()

        if not response.data:
            print(f"No quote tweets found for original_tweet_id {extracted_tweet_id} in 'enriched_tweets' view.")
            return []

        enriched_quote_tweets = []
        for item in response.data:
            # Filter out the original tweet itself (shouldn't happen with quoted_tweet_id filter but good practice)
            if str(item.get("tweet_id")) == str(extracted_tweet_id):
                continue
            
            # Filter out direct replies to the original tweet.
            # A quote tweet is not a direct reply to the tweet it's quoting.
            if str(item.get("reply_to_tweet_id")) == str(extracted_tweet_id):
                print(f"Filtered out direct reply ID {item.get('tweet_id')} which was also quoting {extracted_tweet_id}")
                continue

            enriched_quote_tweets.append({
                'id': str(item.get("tweet_id")),\
                'text': item.get('full_text'),\
                'timestamp': item.get('created_at'),\
                'like_count': item.get('favorite_count', 0),\
                'retweet_count': item.get('retweet_count', 0),\
                'reply_to_tweet_id': str(item.get('reply_to_tweet_id')) if item.get('reply_to_tweet_id') else None,\
                'author_handle': item.get('username'),\
                'author_display_name': item.get('account_display_name'),\
                'avatar_url': item.get('avatar_media_url'),\
                'account_id': str(item.get("account_id")),\
                # 'conversation_id': item.get('conversation_id') # Not selected, add if needed later
            })
        
        print(f"Successfully fetched and processed {len(enriched_quote_tweets)} quote tweets from 'enriched_tweets' view.")
        return enriched_quote_tweets

    except PostgrestAPIError as e:
        print(f"PostgrestAPIError while fetching quote tweets from 'enriched_tweets' view: {e.message} (Code: {e.code}, Details: {e.details})")
        import traceback
        traceback.print_exc()
        return []
    except HTTPStatusError as e:
        print(f"HTTPStatusError while fetching quote tweets from 'enriched_tweets' view: {e.response.status_code} - {e.response.text}")
        import traceback
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"An unexpected error occurred while fetching quote tweets from 'enriched_tweets' view: {e}")
        import traceback
        traceback.print_exc()
        return []

async def main_async():
    sample_url = os.getenv("TEST_TWEET_URL", "https://x.com/_brentbaum/status/1923019796427256121") # Original one
    # sample_url = "https://x.com/levelsio/status/1798288092797698307" # A tweet with known replies
    
    if not supabase_client:
        print("Exiting: Supabase client could not be initialized. Check .env file and Supabase credentials.")
        return
    
    print(f"--- Starting analysis for URL: {sample_url} ---")
    final_thread_data = await fetch_enriched_tweet_thread(sample_url)
    
    if isinstance(final_thread_data, list):
        print(f"--- Successfully fetched and enriched thread. Number of items: {len(final_thread_data)} ---")
        if final_thread_data:
            # Sort by timestamp before printing to ensure main tweet is first if not already
            # final_thread_data.sort(key=lambda x: x.get('timestamp', '')) 
            # The fetch already sorts by created_at, so this might be redundant
            
            extracted_id_for_main_tweet_check = extract_tweet_id_from_url(sample_url)
            main_tweet_index = -1
            for i, tweet_data in enumerate(final_thread_data):
                if tweet_data.get('id') == extracted_id_for_main_tweet_check:
                    main_tweet_index = i
                    break
            
            if main_tweet_index != -1:
                print(f"Main tweet (identified at index {main_tweet_index}, ID: {final_thread_data[main_tweet_index].get('id')} from conversation {final_thread_data[main_tweet_index].get('conversation_id')}):")
                try:
                    print(json.dumps(final_thread_data[main_tweet_index], indent=2, ensure_ascii=False))
                except TypeError:
                    print("Could not JSON serialize the main tweet, printing as is:")
                    print(final_thread_data[main_tweet_index])
            else:
                print("Could not definitively identify the main tweet in the fetched list based on original URL.")
                if final_thread_data: # Print the first one if main couldn't be IDed
                    print("Printing first available tweet as a fallback:")
                    print(json.dumps(final_thread_data[0], indent=2, ensure_ascii=False))

            reply_count = 0
            for i, tweet_data in enumerate(final_thread_data):
                if i == main_tweet_index: continue # Skip the main tweet itself
                if reply_count < 2: # Print first 2 replies
                    print(f"Sample reply {reply_count + 1} (Original Index: {i}):")
                    try:
                        print(json.dumps(tweet_data, indent=2, ensure_ascii=False))
                    except TypeError:
                        print(tweet_data)
                    reply_count += 1
                if reply_count >= 2: break
        else:
            print("No items in the returned list after enrichment.")
    elif isinstance(final_thread_data, dict) and "error" in final_thread_data:
        print(f"--- Function call resulted in an error: ---")
        for key, value in final_thread_data.items():
            if value is not None:
                print(f"  {key.capitalize()}: {value}")
    else:
        print(f"--- Failed to fetch thread data or unexpected return type: {type(final_thread_data)} ---")
        print(f"Content (first 200 chars): {str(final_thread_data)[:200]}...")

if __name__ == '__main__':
    asyncio.run(main_async()) 