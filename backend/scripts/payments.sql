-- Payment gateway settings (Stripe, Razorpay, CCAvenue). New table only. Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS payment_gateway (
    id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code           VARCHAR(30)  NOT NULL,              -- stripe | razorpay | ccavenue
    name           VARCHAR(100) NOT NULL,
    is_enabled     TINYINT(1)   NOT NULL DEFAULT 0,    -- may be used
    is_active      TINYINT(1)   NOT NULL DEFAULT 0,    -- the one gateway payments go through
    mode           VARCHAR(10)  NOT NULL DEFAULT 'test', -- test | live
    currency       VARCHAR(3)   NOT NULL DEFAULT 'INR',
    public_config  JSON         NULL,                  -- non-secret settings (key id, merchant id…)
    secrets        TEXT         NULL,                  -- Fernet-encrypted JSON of the secret keys
    last_tested_at DATETIME(6)  NULL,
    last_test_ok   TINYINT(1)   NULL,
    last_test_message VARCHAR(500) NOT NULL DEFAULT '',
    updated_by_id  BIGINT       NULL,
    created_at     DATETIME(6)  NOT NULL,
    updated_at     DATETIME(6)  NOT NULL,
    UNIQUE KEY payment_gateway_code_uniq (code),
    CONSTRAINT payment_gateway_updated_by_fk FOREIGN KEY (updated_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
