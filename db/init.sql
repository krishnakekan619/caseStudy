-- ─── Database initialisation ────────────────────────────────────────────────
-- This script runs once when the PostgreSQL container starts for the first time.
-- SQLAlchemy in each service will CREATE TABLE IF NOT EXISTS on startup,
-- so this script focuses on the user, extensions, and seed data.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Seed stocks ─────────────────────────────────────────────────────────────
-- The stock-listing service creates the table on first boot.
-- Seed data is inserted safely with ON CONFLICT DO NOTHING.

INSERT INTO stocks (symbol, name, sector, current_price, change_pct, volume, market_cap)
VALUES
  ('AAPL', 'Apple Inc.',              'Technology',   189.50,  1.20, 54321000, 2940000.0),
  ('MSFT', 'Microsoft Corporation',   'Technology',   415.30,  0.85, 23100000, 3090000.0),
  ('GOOGL','Alphabet Inc.',           'Technology',   175.40, -0.30, 18700000, 2190000.0),
  ('AMZN', 'Amazon.com Inc.',         'Consumer',     185.60,  2.10, 31200000, 1930000.0),
  ('TSLA', 'Tesla Inc.',              'Automotive',   175.10, -1.50, 78900000,  557000.0),
  ('NVDA', 'NVIDIA Corporation',      'Technology',   875.40,  3.20, 43100000, 2160000.0),
  ('JPM',  'JPMorgan Chase & Co.',    'Finance',      198.70,  0.60, 11200000,  574000.0),
  ('V',    'Visa Inc.',               'Finance',      274.30,  0.40,  6800000,  563000.0),
  ('JNJ',  'Johnson & Johnson',       'Healthcare',   152.80, -0.20,  8100000,  368000.0),
  ('WMT',  'Walmart Inc.',            'Retail',        66.50,  0.70, 14500000,  536000.0)
ON CONFLICT (symbol) DO NOTHING;
