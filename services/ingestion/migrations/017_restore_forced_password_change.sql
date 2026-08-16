-- Passwords chosen by an administrator are temporary. New user rows should
-- default to requiring the user to choose a private password at next login.
-- Existing users are deliberately left unchanged; only a new account or a
-- later admin password reset should re-enable the requirement for that user.

ALTER TABLE eparking.users
    ALTER COLUMN must_change_password SET DEFAULT TRUE;
