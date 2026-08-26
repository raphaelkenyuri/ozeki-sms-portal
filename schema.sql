-- SMS Gateway — cache/reporting schema

CREATE TABLE IF NOT EXISTS response_codes (
    code  INT          PRIMARY KEY,
    label VARCHAR(50)  NOT NULL
);

INSERT IGNORE INTO response_codes (code, label) VALUES
    (2, 'Safe'),
    (3, 'Unsafe'),
    (4, 'Out of the country');

CREATE TABLE IF NOT EXISTS addresses_cache (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    ozeki_ref    VARCHAR(100) UNIQUE NOT NULL,   -- address name as Ozeki knows it
    name         VARCHAR(255),
    last_synced  DATETIME     NOT NULL
);

CREATE TABLE IF NOT EXISTS address_members (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    address_ozeki_ref VARCHAR(100) NOT NULL,
    phone_number     VARCHAR(30)  NOT NULL,
    name             VARCHAR(255),
    UNIQUE KEY uq_addr_phone (address_ozeki_ref, phone_number)
);

CREATE TABLE IF NOT EXISTS contacts (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(255)  NOT NULL,
    phone_number VARCHAR(30)   NOT NULL,
    group_tag    VARCHAR(100)  DEFAULT NULL,
    notes        VARCHAR(500)  DEFAULT NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contacts_phone (phone_number)
);

CREATE TABLE IF NOT EXISTS outbound_messages (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    address_ref  VARCHAR(100),                  -- ozeki_ref of the target address
    body         TEXT         NOT NULL,
    ozeki_msg_id VARCHAR(16),                   -- returned by Ozeki sendmessage
    status       VARCHAR(50),
    sent_at      DATETIME     NOT NULL
);

CREATE TABLE IF NOT EXISTS inbound_responses (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    from_number       VARCHAR(30)  NOT NULL,
    raw_message       TEXT         NOT NULL,
    response_code     INT,
    translated_status VARCHAR(50),
    received_at       DATETIME     NOT NULL,
    FOREIGN KEY (response_code) REFERENCES response_codes(code)
);

-- ── Campaigns ────────────────────────────────────────────────────────────────
-- Each send creates one campaign row. Outbound messages and inbound responses
-- are linked to it so per-campaign reporting and deduplication are possible.

CREATE TABLE IF NOT EXISTS campaigns (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    body            TEXT         NOT NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recipient_count INT          NOT NULL DEFAULT 0
);

ALTER TABLE outbound_messages
    ADD COLUMN IF NOT EXISTS campaign_id     INT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(50) DEFAULT NULL;

ALTER TABLE outbound_messages DROP FOREIGN KEY IF EXISTS fk_outbound_campaign;
ALTER TABLE outbound_messages
    ADD CONSTRAINT fk_outbound_campaign
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;

ALTER TABLE inbound_responses
    ADD COLUMN IF NOT EXISTS campaign_id INT DEFAULT NULL;

ALTER TABLE inbound_responses DROP FOREIGN KEY IF EXISTS fk_inbound_campaign;
ALTER TABLE inbound_responses
    ADD CONSTRAINT fk_inbound_campaign
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;

-- ── Contacts — extended fields ───────────────────────────────────────────────

ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS site         VARCHAR(100) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS department   VARCHAR(100) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS email        VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS line_manager VARCHAR(255) DEFAULT NULL;

-- ── Groups ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS `groups` (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500) DEFAULT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_groups (
    contact_id INT NOT NULL,
    group_id   INT NOT NULL,
    PRIMARY KEY (contact_id, group_id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id)   REFERENCES `groups`(id) ON DELETE CASCADE
);

-- ── Indexes ──────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_inbound_campaign  ON inbound_responses (campaign_id, from_number, received_at);
CREATE INDEX IF NOT EXISTS idx_outbound_campaign ON outbound_messages  (campaign_id);

-- ── Campaign extended fields ──────────────────────────────────────────────────

ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS name                 VARCHAR(255) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS response_window_days INT NOT NULL DEFAULT 30;

-- ── Keyword response mapping ──────────────────────────────────────────────────
-- Inbound SMS text is normalized (lowercase, punctuation stripped) and matched
-- against this table. Add rows here to support new keywords without code changes.

CREATE TABLE IF NOT EXISTS response_keywords (
    keyword VARCHAR(50) PRIMARY KEY,
    code    INT NOT NULL,
    FOREIGN KEY (code) REFERENCES response_codes(code) ON DELETE CASCADE
);

INSERT IGNORE INTO response_keywords (keyword, code) VALUES
    ('2', 2), ('two', 2), ('safe', 2),
    ('3', 3), ('three', 3), ('unsafe', 3),
    ('4', 4), ('four', 4), ('ooc', 4), ('out', 4), ('out of country', 4);

-- ── All staff default group ───────────────────────────────────────────────────
-- Every new contact is auto-enrolled in this group. Run the back-fill INSERT
-- once after this migration to enroll contacts that existed before this change.

INSERT IGNORE INTO `groups` (name, description, created_at)
VALUES ('All staff', 'Default group — every contact is enrolled automatically.', NOW());

INSERT IGNORE INTO contact_groups (contact_id, group_id)
SELECT c.id, g.id FROM contacts c JOIN `groups` g ON g.name = 'All staff';
