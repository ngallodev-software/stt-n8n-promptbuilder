-- Phase 2 simplification: drop console_admin_audit_log and console_secret_settings
-- Safe to run after code cleanup verified

DROP TABLE IF EXISTS console_admin_audit_log;
DROP TABLE IF EXISTS console_secret_settings;
