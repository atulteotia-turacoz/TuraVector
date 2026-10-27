-- Tools catalogue, subscription plans and workspace subscriptions. New tables only. Safe to run repeatedly.

-- Every tool / service a workspace can use: the built-in TuraVector dashboards, the other Tura
-- applications and any application added later from the admin.
CREATE TABLE IF NOT EXISTS platform_tool (
    id            BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `key`         VARCHAR(60)   NOT NULL,              -- content_lab | other_documents | ext_* | custom
    name          VARCHAR(150)  NOT NULL,
    description   VARCHAR(500)  NOT NULL DEFAULT '',
    features      JSON          NULL,                  -- ["…", "…"] bullet points on the cards
    kind          VARCHAR(20)   NOT NULL DEFAULT 'app', -- dashboard (inside TuraVector) | app (opens another application)
    url           VARCHAR(500)  NOT NULL DEFAULT '',   -- app link (built-in apps take theirs from settings)
    icon          VARCHAR(40)   NOT NULL DEFAULT '',   -- icon name shown on the card
    is_builtin    TINYINT(1)    NOT NULL DEFAULT 0,    -- built-in tools can't be deleted or re-keyed
    is_free       TINYINT(1)    NOT NULL DEFAULT 0,    -- every user gets it without a plan
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    sort_order    INT           NOT NULL DEFAULT 0,
    updated_by_id BIGINT        NULL,
    created_at    DATETIME(6)   NOT NULL,
    updated_at    DATETIME(6)   NOT NULL,
    UNIQUE KEY platform_tool_key_uniq (`key`),
    CONSTRAINT platform_tool_updated_by_fk FOREIGN KEY (updated_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A plan: a set of tools at a price for a period.
CREATE TABLE IF NOT EXISTS subscription_plan (
    id             BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(150)  NOT NULL,
    description    VARCHAR(500)  NOT NULL DEFAULT '',
    price          DECIMAL(12,2) NOT NULL DEFAULT 0,     -- 0 = free
    currency       VARCHAR(3)    NOT NULL DEFAULT 'INR',
    billing_period VARCHAR(20)   NOT NULL DEFAULT 'monthly', -- monthly | quarterly | half_yearly | yearly | lifetime
    trial_days     INT           NOT NULL DEFAULT 0,
    audience       VARCHAR(20)   NOT NULL DEFAULT 'all',  -- individual | organisation | all
    is_featured    TINYINT(1)    NOT NULL DEFAULT 0,
    is_active      TINYINT(1)    NOT NULL DEFAULT 1,
    sort_order     INT           NOT NULL DEFAULT 0,
    tax_percent    DECIMAL(5,2)  NOT NULL DEFAULT 18.00, -- GST added on top of the price
    sac_code       VARCHAR(20)   NOT NULL DEFAULT '',    -- printed on the tax invoice
    updated_by_id  BIGINT        NULL,
    created_at     DATETIME(6)   NOT NULL,
    updated_at     DATETIME(6)   NOT NULL,
    UNIQUE KEY subscription_plan_name_uniq (name),
    CONSTRAINT subscription_plan_updated_by_fk FOREIGN KEY (updated_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS subscription_plan_tool (
    id      BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    tool_id BIGINT NOT NULL,
    UNIQUE KEY subscription_plan_tool_uniq (plan_id, tool_id),
    CONSTRAINT subscription_plan_tool_plan_fk FOREIGN KEY (plan_id) REFERENCES subscription_plan (id) ON DELETE CASCADE,
    CONSTRAINT subscription_plan_tool_tool_fk FOREIGN KEY (tool_id) REFERENCES platform_tool (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A workspace's (individual or university / organisation) subscription to a plan. Price, period and
-- tools are copied from the plan when subscribing, so later plan changes don't alter what was bought.
CREATE TABLE IF NOT EXISTS org_subscription (
    id               BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id  BIGINT        NOT NULL,
    plan_id          BIGINT        NULL,
    plan_name        VARCHAR(150)  NOT NULL,
    tool_keys        JSON          NULL,
    price            DECIMAL(12,2) NOT NULL DEFAULT 0,
    currency         VARCHAR(3)    NOT NULL DEFAULT 'INR',
    billing_period   VARCHAR(20)   NOT NULL,
    status           VARCHAR(20)   NOT NULL,             -- pending (awaiting payment) | active | cancelled
    is_trial         TINYINT(1)    NOT NULL DEFAULT 0,
    source           VARCHAR(20)   NOT NULL DEFAULT 'self', -- signup | self | admin
    starts_at        DATETIME(6)   NULL,
    ends_at          DATETIME(6)   NULL,                 -- NULL = no end (lifetime)
    gateway          VARCHAR(30)   NOT NULL DEFAULT '',
    gateway_order_id VARCHAR(100)  NOT NULL DEFAULT '',
    payment_ref      VARCHAR(100)  NOT NULL DEFAULT '',
    paid_at          DATETIME(6)   NULL,
    notes            VARCHAR(500)  NOT NULL DEFAULT '',
    tax_percent      DECIMAL(5,2)  NOT NULL DEFAULT 0,
    tax_amount       DECIMAL(12,2) NOT NULL DEFAULT 0,     -- GST charged on top of price
    tax_mode         VARCHAR(10)   NOT NULL DEFAULT '',    -- intra | inter | overseas
    invoice_id       BIGINT        NULL,                   -- the tax invoice issued when it was paid
    cancelled_at     DATETIME(6)   NULL,                   -- cancelled by the workspace: runs until ends_at
    created_by_id    BIGINT        NULL,
    created_at       DATETIME(6)   NOT NULL,
    updated_at       DATETIME(6)   NOT NULL,
    KEY org_subscription_org_idx (organisation_id, status),
    KEY org_subscription_order_idx (gateway_order_id),
    CONSTRAINT org_subscription_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id) ON DELETE CASCADE,
    CONSTRAINT org_subscription_plan_fk FOREIGN KEY (plan_id) REFERENCES subscription_plan (id) ON DELETE SET NULL,
    CONSTRAINT org_subscription_created_by_fk FOREIGN KEY (created_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
