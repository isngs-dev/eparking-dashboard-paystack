-- Administrators now choose user passwords directly. New and existing users
-- must not be forced through the first-login change-password screen.

ALTER TABLE eparking.users
    ALTER COLUMN must_change_password SET DEFAULT FALSE;

UPDATE eparking.users
SET must_change_password = FALSE,
    updated_at = now()
WHERE must_change_password = TRUE;
