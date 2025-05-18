import os
import psycopg2
import psycopg2.extras # For dictionary cursor
import json
from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        return None

def create_cache_table_if_not_exists():
    """Creates the 'analyzed_tweets_cache' table if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analyzed_tweets_cache (
                    tweet_id TEXT PRIMARY KEY,
                    tweet_author_username TEXT NOT NULL,
                    original_tweet_url TEXT NOT NULL,
                    analysis_results_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE OR REPLACE FUNCTION trigger_set_timestamp()
                RETURNS TRIGGER AS $$
                BEGIN
                  NEW.updated_at = NOW();
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_timestamp_analyzed_tweets_cache_trigger') THEN
                        CREATE TRIGGER set_timestamp_analyzed_tweets_cache_trigger
                        BEFORE UPDATE ON analyzed_tweets_cache
                        FOR EACH ROW
                        EXECUTE PROCEDURE trigger_set_timestamp();
                    END IF;
                END
                $$;
            """)
            conn.commit()
            print("'analyzed_tweets_cache' table checked/created successfully with trigger.")
    except psycopg2.Error as e:
        print(f"Error creating/checking table or trigger: {e}")
    finally:
        if conn:
            conn.close()

def save_analysis_to_pg_cache(tweet_id: str, tweet_author_username: str, original_tweet_url: str, analysis_results_json: dict) -> bool:
    """Saves or updates tweet analysis results in the PostgreSQL cache table."""
    conn = get_db_connection()
    if not conn:
        return False
    
    sql = """
    INSERT INTO analyzed_tweets_cache (tweet_id, tweet_author_username, original_tweet_url, analysis_results_json, created_at, updated_at)
    VALUES (%s, %s, %s, %s, NOW(), NOW())
    ON CONFLICT (tweet_id)
    DO UPDATE SET
        tweet_author_username = EXCLUDED.tweet_author_username,
        original_tweet_url = EXCLUDED.original_tweet_url,
        analysis_results_json = EXCLUDED.analysis_results_json,
        updated_at = NOW();
    """
    try:
        with conn.cursor() as cur:
            # Convert analysis_results_json dict to a JSON string for storage
            cur.execute(sql, (tweet_id, tweet_author_username, original_tweet_url, json.dumps(analysis_results_json)))
            conn.commit()
            print(f"Successfully saved/updated analysis for tweet_id: {tweet_id} to PG cache.")
            return True
    except psycopg2.Error as e:
        print(f"PostgreSQL Error saving analysis for {tweet_id}: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"JSON Error encoding analysis_results for {tweet_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_analysis_from_pg_cache(tweet_id: str) -> dict | None:
    """Retrieves tweet analysis results from the PostgreSQL cache table by tweet_id."""
    conn = get_db_connection()
    if not conn:
        return None
    
    sql = "SELECT tweet_id, tweet_author_username, original_tweet_url, analysis_results_json, created_at, updated_at FROM analyzed_tweets_cache WHERE tweet_id = %s;"
    try:
        # psycopg2.extras.DictCursor allows accessing columns by name
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (tweet_id,))
            row = cur.fetchone()
            if row:
                print(f"Successfully fetched analysis for tweet_id: {tweet_id} from PG cache.")
                # The 'analysis_results_json' column is already a dict if JSONB was used and psycopg2 handles it well.
                # If it's a string, it would need json.loads(row['analysis_results_json'])
                return dict(row) # Convert DictRow to a standard dict
            else:
                print(f"No analysis found in PG cache for tweet_id: {tweet_id}.")
                return None
    except psycopg2.Error as e:
        print(f"PostgreSQL Error fetching analysis for {tweet_id} from cache: {e}")
        return None
    finally:
        if conn:
            conn.close()

# Example of calling create_table_if_not_exists on module load, 
# but better to call this explicitly from app startup.
# if __name__ == '__main__':
# create_cache_table_if_not_exists() 
# print("DB Manager loaded. Attempted to create table if it didn't exist.") 