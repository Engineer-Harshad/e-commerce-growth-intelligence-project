-- ============================================================
-- PROJECT : Marketing Analytics
-- DATABASE : portfolioproject_marketinganalytics
-- PURPOSE  : Data cleaning, enrichment, and transformation
--            queries for Power BI ingestion
-- AUTHOR   : Harshad
-- ============================================================


-- ============================================================
-- TABLE   : customers + geography
-- PURPOSE : Enrich customer records with geographic dimensions
--           using a LEFT JOIN to retain customers with no
--           geography match (prevents silent row loss)
-- ============================================================

SELECT
    c.CustomerID,
    c.CustomerName,
    c.Email,
    c.Gender,
    c.Age,
    g.Country,
    g.City
FROM portfolioproject_marketinganalytics.customers AS c
LEFT JOIN portfolioproject_marketinganalytics.geography AS g
    ON c.GeographyID = g.GeographyID;


-- ============================================================
-- TABLE   : products
-- PURPOSE : Derive price tier segmentation for product-level
--           performance analysis in the dashboard
-- LOGIC   : Thresholds (< 50 = Low, 50-200 = Medium, > 200 = High)
--           defined based on the product catalog price distribution
-- ============================================================

SELECT
    ProductID,
    ProductName,
    Price,
    CASE
        WHEN Price < 50              THEN 'Low'
        WHEN Price BETWEEN 50 AND 200 THEN 'Medium'
        ELSE                              'High'
    END AS PriceCategory
FROM portfolioproject_marketinganalytics.products;


-- ============================================================
-- TABLE   : customer_reviews
-- PURPOSE : Standardize review text before sentiment analysis;
--           feed clean output to Python NLTK VADER pipeline
-- ============================================================

SELECT
    ReviewID,
    CustomerID,
    ProductID,
    ReviewDate,
    Rating,
    -- Raw data contains double spaces in ReviewText; replaced with single space
    REPLACE(ReviewText, '  ', ' ') AS ReviewText
FROM portfolioproject_marketinganalytics.customer_reviews;


-- ============================================================
-- TABLE   : engagement_data
-- PURPOSE : Normalize content type labels, split a combined
--           Views-Clicks column into separate metrics, and
--           standardize date format for Power BI compatibility
-- ============================================================

SELECT
    EngagementID,
    ContentID,
    CampaignID,
    ProductID,
    -- Raw data contains malformed value 'Socialmedia'; corrected to
    -- 'Social Media' before uppercasing for consistent category labels
    UPPER(REPLACE(ContentType, 'Socialmedia', 'Social Media')) AS ContentType,
    -- ViewsClicksCombined stores two metrics as 'views-clicks' string;
    -- split into separate columns for independent analysis
    LEFT(ViewsClicksCombined, LOCATE('-', ViewsClicksCombined) - 1)                              AS Views,
    RIGHT(ViewsClicksCombined, LENGTH(ViewsClicksCombined) - LOCATE('-', ViewsClicksCombined))   AS Clicks,
    Likes,
    -- Converted to dd.mm.yyyy to match regional date format used in the dashboard
    DATE_FORMAT(EngagementDate, '%d.%m.%Y') AS EngagementDate
FROM portfolioproject_marketinganalytics.engagement_data
WHERE ContentType != 'Newsletter'; -- Newsletters excluded; not a trackable digital engagement type


-- ============================================================
-- TABLE   : customer_journey
-- PURPOSE : Remove duplicate journey records and impute missing
--           Duration values to preserve funnel completeness
-- LOGIC   :
--   1. ROW_NUMBER() partitioned by natural key columns isolates
--      true duplicates; only the first occurrence is retained
--   2. AVG(Duration) OVER (PARTITION BY VisitDate) imputes nulls
--      with a date-level average to avoid skewing funnel analysis
--      with arbitrary global averages
-- ============================================================

SELECT
    JourneyID,
    CustomerID,
    ProductID,
    VisitDate,
    Stage,
    Action,
    -- Null Duration replaced with date-level average; preserves row
    -- count without distorting stage-level duration aggregations
    COALESCE(Duration, avg_duration) AS Duration
FROM (
    SELECT
        JourneyID,
        CustomerID,
        ProductID,
        VisitDate,
        UPPER(Stage) AS Stage, -- Uppercased for consistent stage label matching in Power BI
        Action,
        Duration,
        AVG(Duration)  OVER (PARTITION BY VisitDate)                                          AS avg_duration,
        ROW_NUMBER()   OVER (
            PARTITION BY CustomerID, ProductID, VisitDate, UPPER(Stage), Action
            ORDER BY JourneyID  -- Retain lowest JourneyID as the canonical record
        )                                                                                      AS row_num
    FROM portfolioproject_marketinganalytics.customer_journey
) AS subquery
WHERE row_num = 1;
