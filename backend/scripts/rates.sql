-- Rate cards. New tables only. Safe to run repeatedly.

-- The standard rate card: every billable service with its standard rate.
CREATE TABLE IF NOT EXISTS rate_service (
    id            BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(150)  NOT NULL,
    description   VARCHAR(500)  NOT NULL DEFAULT '',
    unit          VARCHAR(30)   NOT NULL DEFAULT '',  -- per_document | per_page | per_word | per_hour | fixed | '' (none)
    standard_rate DECIMAL(12,2) NOT NULL DEFAULT 0,
    tax_percent   DECIMAL(5,2)  NOT NULL DEFAULT 0,
    currency      VARCHAR(3)    NOT NULL DEFAULT 'INR',
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    sort_order    INT           NOT NULL DEFAULT 0,
    updated_by_id BIGINT        NULL,
    created_at    DATETIME(6)   NOT NULL,
    updated_at    DATETIME(6)   NOT NULL,
    UNIQUE KEY rate_service_name_uniq (name),
    CONSTRAINT rate_service_updated_by_fk FOREIGN KEY (updated_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A university / organisation's own rate card: standard services chosen for it, at its own rates.
CREATE TABLE IF NOT EXISTS rate_card_item (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id BIGINT        NOT NULL,
    service_id      BIGINT        NOT NULL,
    rate            DECIMAL(12,2) NOT NULL,
    notes           VARCHAR(300)  NOT NULL DEFAULT '',
    updated_by_id   BIGINT        NULL,
    created_at      DATETIME(6)   NOT NULL,
    updated_at      DATETIME(6)   NOT NULL,
    UNIQUE KEY rate_card_item_uniq (organisation_id, service_id),
    CONSTRAINT rate_card_item_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id) ON DELETE CASCADE,
    CONSTRAINT rate_card_item_service_fk FOREIGN KEY (service_id) REFERENCES rate_service (id),
    CONSTRAINT rate_card_item_updated_by_fk FOREIGN KEY (updated_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- (scripts/setup_billing.py adds sac_code and tax_overseas to rate_service)
