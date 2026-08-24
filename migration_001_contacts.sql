-- Migration 001: Add contacts table
-- Run once: sudo mariadb ozeki_app < migration_001_contacts.sql

CREATE TABLE IF NOT EXISTS contacts (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(255)  NOT NULL,
    phone_number VARCHAR(30)   NOT NULL,
    group_tag    VARCHAR(100)  DEFAULT NULL,
    notes        VARCHAR(500)  DEFAULT NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_contacts_phone (phone_number)
);
