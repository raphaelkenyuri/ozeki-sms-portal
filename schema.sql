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
