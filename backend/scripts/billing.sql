-- Billing: requests for rate-card services, invoices and their approval. New tables only.

CREATE TABLE IF NOT EXISTS billing_settings (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    company_name    VARCHAR(200)  NOT NULL DEFAULT '',
    address         VARCHAR(500)  NOT NULL DEFAULT '',
    state           VARCHAR(100)  NOT NULL DEFAULT '',
    state_code      VARCHAR(5)    NOT NULL DEFAULT '',
    country         VARCHAR(100)  NOT NULL DEFAULT 'India',
    gstin           VARCHAR(20)   NOT NULL DEFAULT '',
    pan             VARCHAR(20)   NOT NULL DEFAULT '',
    email           VARCHAR(200)  NOT NULL DEFAULT '',
    phone           VARCHAR(50)   NOT NULL DEFAULT '',
    invoice_prefix  VARCHAR(10)   NOT NULL DEFAULT 'TC',
    bank_details    VARCHAR(1000) NOT NULL DEFAULT '',
    terms           VARCHAR(2000) NOT NULL DEFAULT '',
    sequence_year   VARCHAR(4)    NOT NULL DEFAULT '',   -- financial year of the counter, e.g. 2627
    sequence_next   INT           NOT NULL DEFAULT 1,
    updated_by_id   BIGINT        NULL,
    updated_at      DATETIME(6)   NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS org_billing_profile (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id BIGINT        NOT NULL,
    legal_name      VARCHAR(200)  NOT NULL DEFAULT '',
    address         VARCHAR(500)  NOT NULL DEFAULT '',
    state           VARCHAR(100)  NOT NULL DEFAULT '',
    state_code      VARCHAR(5)    NOT NULL DEFAULT '',
    country         VARCHAR(100)  NOT NULL DEFAULT 'India',
    gstin           VARCHAR(20)   NOT NULL DEFAULT '',
    billing_email   VARCHAR(200)  NOT NULL DEFAULT '',
    billing_cycle   VARCHAR(20)   NOT NULL DEFAULT 'per_submission',   -- per_submission | monthly
    updated_by_id   BIGINT        NULL,
    updated_at      DATETIME(6)   NOT NULL,
    UNIQUE KEY org_billing_profile_org_uniq (organisation_id),
    CONSTRAINT org_billing_profile_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS billing_approver (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT        NOT NULL,
    added_by_id     BIGINT        NULL,
    created_at      DATETIME(6)   NOT NULL,
    UNIQUE KEY billing_approver_user_uniq (user_id),
    CONSTRAINT billing_approver_user_fk FOREIGN KEY (user_id) REFERENCES authentication_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invoice (
    id                  BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    number              VARCHAR(30)   NOT NULL,
    organisation_id     BIGINT        NOT NULL,
    cycle               VARCHAR(20)   NOT NULL,                -- per_submission | monthly
    period_start        DATE          NULL,
    period_end          DATE          NULL,
    status              VARCHAR(30)   NOT NULL,                -- pending_turacoz | pending_client | awaiting_payment | paid | rejected
    tax_mode            VARCHAR(10)   NOT NULL,                -- intra | inter | overseas
    currency            VARCHAR(3)    NOT NULL DEFAULT 'INR',
    subtotal            DECIMAL(14,2) NOT NULL DEFAULT 0,
    cgst                DECIMAL(14,2) NOT NULL DEFAULT 0,
    sgst                DECIMAL(14,2) NOT NULL DEFAULT 0,
    igst                DECIMAL(14,2) NOT NULL DEFAULT 0,
    total               DECIMAL(14,2) NOT NULL DEFAULT 0,
    seller              JSON          NULL,
    buyer               JSON          NULL,
    turacoz_approved_by_id BIGINT     NULL,
    turacoz_approved_at DATETIME(6)   NULL,
    client_approved_by_id  BIGINT     NULL,
    client_approved_at  DATETIME(6)   NULL,
    turacoz_remarks     VARCHAR(1000) NOT NULL DEFAULT '',
    client_remarks      VARCHAR(1000) NOT NULL DEFAULT '',
    gateway             VARCHAR(20)   NOT NULL DEFAULT '',
    gateway_order_id    VARCHAR(100)  NOT NULL DEFAULT '',
    payment_id          VARCHAR(100)  NOT NULL DEFAULT '',
    paid_at             DATETIME(6)   NULL,
    created_at          DATETIME(6)   NOT NULL,
    updated_at          DATETIME(6)   NOT NULL,
    UNIQUE KEY invoice_number_uniq (number),
    KEY invoice_org_status (organisation_id, status),
    CONSTRAINT invoice_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS billing_request (
    id                  BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id     BIGINT        NOT NULL,
    user_id             BIGINT        NOT NULL,
    document_id         BIGINT        NULL,
    document_version_id BIGINT        NULL,
    requirement         TEXT          NULL,
    invoice_id          BIGINT        NULL,
    created_at          DATETIME(6)   NOT NULL,
    KEY billing_request_unbilled (organisation_id, invoice_id),
    CONSTRAINT billing_request_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id),
    CONSTRAINT billing_request_user_fk FOREIGN KEY (user_id) REFERENCES authentication_user (id),
    CONSTRAINT billing_request_invoice_fk FOREIGN KEY (invoice_id) REFERENCES invoice (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS billing_request_item (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    request_id      BIGINT        NOT NULL,
    service_id      BIGINT        NULL,
    name            VARCHAR(150)  NOT NULL,
    unit            VARCHAR(30)   NOT NULL DEFAULT '',
    sac_code        VARCHAR(20)   NOT NULL DEFAULT '',
    quantity        DECIMAL(12,2) NOT NULL DEFAULT 1,
    rate            DECIMAL(12,2) NOT NULL,
    tax_percent     DECIMAL(5,2)  NOT NULL DEFAULT 0,
    tax_overseas    TINYINT(1)    NOT NULL DEFAULT 0,
    CONSTRAINT billing_request_item_req_fk FOREIGN KEY (request_id) REFERENCES billing_request (id) ON DELETE CASCADE,
    CONSTRAINT billing_request_item_service_fk FOREIGN KEY (service_id) REFERENCES rate_service (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invoice_line (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    invoice_id      BIGINT        NOT NULL,
    request_item_id BIGINT        NULL,
    description     VARCHAR(400)  NOT NULL,
    sac_code        VARCHAR(20)   NOT NULL DEFAULT '',
    unit            VARCHAR(30)   NOT NULL DEFAULT '',
    quantity        DECIMAL(12,2) NOT NULL,
    rate            DECIMAL(12,2) NOT NULL,
    amount          DECIMAL(14,2) NOT NULL,
    tax_percent     DECIMAL(5,2)  NOT NULL DEFAULT 0,
    tax_overseas    TINYINT(1)    NOT NULL DEFAULT 0,
    cgst            DECIMAL(14,2) NOT NULL DEFAULT 0,
    sgst            DECIMAL(14,2) NOT NULL DEFAULT 0,
    igst            DECIMAL(14,2) NOT NULL DEFAULT 0,
    CONSTRAINT invoice_line_invoice_fk FOREIGN KEY (invoice_id) REFERENCES invoice (id) ON DELETE CASCADE,
    CONSTRAINT invoice_line_item_fk FOREIGN KEY (request_item_id) REFERENCES billing_request_item (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invoice_event (
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    invoice_id      BIGINT        NOT NULL,
    user_id         BIGINT        NULL,
    action          VARCHAR(40)   NOT NULL,
    note            VARCHAR(1000) NOT NULL DEFAULT '',
    created_at      DATETIME(6)   NOT NULL,
    CONSTRAINT invoice_event_invoice_fk FOREIGN KEY (invoice_id) REFERENCES invoice (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
