-- =============================================
-- Sales IQ - PostgreSQL Initialization Script
-- =============================================
-- This runs automatically on first container start

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Fuzzy text matching
CREATE EXTENSION IF NOT EXISTS "btree_gist";     -- GiST index support

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Enable Row-Level Security helper function
-- This function retrieves the current tenant_id from the session variable
CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS UUID AS $$
BEGIN
  RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::UUID;
EXCEPTION
  WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Create application role for RLS enforcement
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'salesiq_app') THEN
    CREATE ROLE salesiq_app LOGIN PASSWORD 'salesiq_app_dev';
  END IF;
END
$$;

-- Grant necessary permissions
GRANT CONNECT ON DATABASE salesiq TO salesiq_app;
GRANT USAGE ON SCHEMA public TO salesiq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO salesiq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO salesiq_app;

-- Log successful initialization
DO $$
BEGIN
  RAISE NOTICE '✓ Sales IQ database initialized successfully';
  RAISE NOTICE '  - Extensions: uuid-ossp, pgcrypto, pg_trgm, btree_gist, timescaledb';
  RAISE NOTICE '  - RLS helper function: current_tenant_id()';
  RAISE NOTICE '  - Application role: salesiq_app';
END
$$;
