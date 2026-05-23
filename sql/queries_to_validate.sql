SELECT * FROM portfolio_db.transactions LIMIT 10;

SELECT * FROM portfolio_db.asset_history LIMIT 10;

WITH ranked AS (
  SELECT
    date,
    account,
    asset,
    market_value,
    daily_acb,
    row_number() OVER (PARTITION BY account, asset ORDER BY date DESC) AS rn
  FROM portfolio_db.asset_history
)
SELECT * FROM ranked WHERE rn = 1;
