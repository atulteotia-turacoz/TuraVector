-- Organisation workspaces (universities, organisations, individuals).
-- New tables only: the Django tables are left untouched. Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS org_organisation (
    id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    slug           VARCHAR(220) NOT NULL,
    kind           VARCHAR(20)  NOT NULL,              -- university | organisation | individual
    website        VARCHAR(300) NOT NULL DEFAULT '',
    logo           VARCHAR(300) NOT NULL DEFAULT '',   -- path relative to MEDIA_ROOT
    status         VARCHAR(20)  NOT NULL,              -- pending | active | rejected | suspended
    join_code      VARCHAR(20)  NULL,
    created_by_id  BIGINT       NULL,
    approved_by_id BIGINT       NULL,
    approved_at    DATETIME(6)  NULL,
    created_at     DATETIME(6)  NOT NULL,
    updated_at     DATETIME(6)  NOT NULL,
    UNIQUE KEY org_organisation_slug_uniq (slug),
    UNIQUE KEY org_organisation_join_code_uniq (join_code),
    KEY org_organisation_status_idx (status),
    CONSTRAINT org_organisation_created_by_fk FOREIGN KEY (created_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL,
    CONSTRAINT org_organisation_approved_by_fk FOREIGN KEY (approved_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS org_membership (
    id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id BIGINT      NOT NULL,
    user_id         BIGINT      NOT NULL,
    role            VARCHAR(20) NOT NULL,              -- admin | member
    status          VARCHAR(20) NOT NULL,              -- active | pending | rejected
    added_by_id     BIGINT      NULL,
    created_at      DATETIME(6) NOT NULL,
    updated_at      DATETIME(6) NOT NULL,
    UNIQUE KEY org_membership_user_uniq (user_id),     -- one workspace per user
    KEY org_membership_org_idx (organisation_id, status),
    CONSTRAINT org_membership_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id) ON DELETE CASCADE,
    CONSTRAINT org_membership_user_fk FOREIGN KEY (user_id) REFERENCES authentication_user (id) ON DELETE CASCADE,
    CONSTRAINT org_membership_added_by_fk FOREIGN KEY (added_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Turacoz team (system users) assigned to client workspaces as PoC or Reviewer.
CREATE TABLE IF NOT EXISTS org_assignment (
    id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    organisation_id BIGINT       NOT NULL,             -- the client university / organisation
    user_id         BIGINT       NOT NULL,             -- a system (Turacoz) user
    role            VARCHAR(20)  NOT NULL,             -- poc | reviewer
    designation     VARCHAR(150) NOT NULL DEFAULT '',
    added_by_id     BIGINT       NULL,
    created_at      DATETIME(6)  NOT NULL,
    updated_at      DATETIME(6)  NOT NULL,
    UNIQUE KEY org_assignment_uniq (organisation_id, user_id, role),
    KEY org_assignment_user_idx (user_id),
    CONSTRAINT org_assignment_org_fk FOREIGN KEY (organisation_id) REFERENCES org_organisation (id) ON DELETE CASCADE,
    CONSTRAINT org_assignment_user_fk FOREIGN KEY (user_id) REFERENCES authentication_user (id) ON DELETE CASCADE,
    CONSTRAINT org_assignment_added_by_fk FOREIGN KEY (added_by_id) REFERENCES authentication_user (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
