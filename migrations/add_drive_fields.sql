-- Migration: Add Google Drive fields to webhook_events table
-- Date: 2025-01-XX
-- Description: Adds drive_file_id and drive_file_url columns to store Google Drive document references

-- Add drive_file_id column (VARCHAR 255 for Google Drive file IDs)
ALTER TABLE webhook_events ADD COLUMN drive_file_id VARCHAR(255);

-- Add drive_file_url column (TEXT for full Google Drive URLs)
ALTER TABLE webhook_events ADD COLUMN drive_file_url TEXT;

-- Create index on drive_file_id for faster lookups
CREATE INDEX idx_webhook_events_drive_file_id ON webhook_events(drive_file_id);

-- Verify columns were added
SELECT column_name, data_type, character_maximum_length, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'webhook_events' 
  AND column_name IN ('drive_file_id', 'drive_file_url');
