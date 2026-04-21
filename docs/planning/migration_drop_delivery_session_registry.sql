-- Phase 2 simplification: drop delivery_session_registry (live-session delivery removed)
DROP TABLE IF EXISTS delivery_session_registry;
-- Safe to run: zero code references verified 2026-04-20
