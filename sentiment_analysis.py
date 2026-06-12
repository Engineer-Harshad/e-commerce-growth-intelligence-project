"""
Sentiment Analysis Pipeline
----------------------------
Fetches customer reviews from MySQL, applies NLTK VADER sentiment scoring,
categorizes sentiment using a hybrid text-score + star-rating logic,
and exports the enriched dataset to CSV for Power BI ingestion.
"""

import os
import time
import logging
import pandas as pd
import nltk
import mysql.connector
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from dotenv import load_dotenv

# ============================================================
# LOGGING SETUP
# Creates logs/ folder in project root if it does not exist,
# then writes all logs to logs/sentiment_analysis.log
# Console handler added so logs are visible in terminal too.
# ============================================================

logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)

log_file_path = os.path.join(logs_dir, 'sentiment_analysis.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# ============================================================
# ENVIRONMENT + NLTK SETUP
# ============================================================

load_dotenv()
logger.info("Environment variables loaded from .env")

nltk.download('vader_lexicon', quiet=True)
logger.info("VADER lexicon ready")


# ============================================================
# FUNCTIONS
# ============================================================

def fetch_data_from_sql():
    """
    Connects to MySQL using .env credentials and fetches customer_reviews table.
    Returns a DataFrame. Raises on connection or query failure.
    """
    logger.info("Attempting MySQL connection...")
    start = time.time()

    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
        logger.info("MySQL connection established (%.2fs)", time.time() - start)
    except mysql.connector.Error as e:
        logger.error("MySQL connection failed: %s", e)
        raise

    query = """
        SELECT ReviewID, CustomerID, ProductID, ReviewDate, Rating, ReviewText
        FROM customer_reviews
    """

    try:
        df = pd.read_sql(query, conn)
        logger.info("Query executed. Rows fetched: %d (%.2fs)", len(df), time.time() - start)
    except Exception as e:
        logger.error("Query execution failed: %s", e)
        conn.close()
        raise
    finally:
        conn.close()
        logger.info("MySQL connection closed")

    return df


def calculate_sentiment(review):
    """Returns VADER compound score: -1 (most negative) to +1 (most positive)."""
    try:
        sia = SentimentIntensityAnalyzer()
        return sia.polarity_scores(review)['compound']
    except Exception as e:
        logger.warning("Sentiment scoring failed for review text. Returning 0.0. Error: %s", e)
        return 0.0


def categorize_sentiment(score, rating):
    """
    Hybrid categorization using both VADER compound score and star rating.
    Handles cases where text tone and numeric rating conflict (Mixed Positive/Negative).
    Thresholds: score > 0.05 = Positive text, score < -0.05 = Negative text.
    """
    if score > 0.05:
        if rating >= 4:
            return 'Positive'
        elif rating == 3:
            return 'Mixed Positive'
        else:
            return 'Mixed Negative'
    elif score < -0.05:
        if rating <= 2:
            return 'Negative'
        elif rating == 3:
            return 'Mixed Negative'
        else:
            return 'Mixed Positive'
    else:
        if rating >= 4:
            return 'Positive'
        elif rating <= 2:
            return 'Negative'
        else:
            return 'Neutral'


def sentiment_bucket(score):
    """Buckets compound score into four ranges for dashboard-level aggregation."""
    if score >= 0.5:
        return '0.5 to 1.0'
    elif 0.0 <= score < 0.5:
        return '0.0 to 0.49'
    elif -0.5 <= score < 0.0:
        return '-0.49 to 0.0'
    else:
        return '-1.0 to -0.5'


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    pipeline_start = time.time()
    logger.info("========== Sentiment Analysis Pipeline Started ==========")

    # --- Step 1: Fetch data ---
    try:
        customer_reviews_df = fetch_data_from_sql()
    except Exception:
        logger.critical("Pipeline aborted: could not fetch data from MySQL")
        raise SystemExit(1)

    # --- Step 2: Sentiment scoring ---
    logger.info("Applying VADER sentiment scoring...")
    step_start = time.time()
    customer_reviews_df['SentimentScore'] = customer_reviews_df['ReviewText'].apply(calculate_sentiment)
    logger.info("Sentiment scoring complete (%.2fs)", time.time() - step_start)

    # --- Step 3: Sentiment categorization ---
    logger.info("Categorizing sentiment using hybrid score + rating logic...")
    step_start = time.time()
    customer_reviews_df['SentimentCategory'] = customer_reviews_df.apply(
        lambda row: categorize_sentiment(row['SentimentScore'], row['Rating']), axis=1
    )
    logger.info("Categorization complete (%.2fs)", time.time() - step_start)

    # --- Step 4: Sentiment bucketing ---
    logger.info("Applying sentiment score bucketing...")
    customer_reviews_df['SentimentBucket'] = customer_reviews_df['SentimentScore'].apply(sentiment_bucket)

    # --- Step 5: Category distribution summary ---
    distribution = customer_reviews_df['SentimentCategory'].value_counts().to_dict()
    logger.info("Sentiment distribution: %s", distribution)

    # --- Step 6: Export to CSV ---
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fact_customer_reviews_with_sentiment.csv')
    logger.info("Exporting enriched dataset to CSV...")
    step_start = time.time()

    try:
        customer_reviews_df.to_csv(output_path, index=False)
        logger.info("CSV exported successfully: %s (%.2fs)", output_path, time.time() - step_start)
    except Exception as e:
        logger.error("CSV export failed: %s", e)
        raise

    logger.info("Total rows processed: %d", len(customer_reviews_df))
    logger.info("Total pipeline duration: %.2fs", time.time() - pipeline_start)
    logger.info("========== Pipeline Finished ==========")

    print(customer_reviews_df.head())