-- ============================================================
-- 知识库结构化改造 - Round 18
-- 迁移时间: 2026-03-29
-- ============================================================

-- 告警规则表
CREATE TABLE IF NOT EXISTS alert_rules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT,
    resource_type TEXT,
    observation_point TEXT,
    condition TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
    recommendation TEXT,
    enabled INTEGER DEFAULT 1,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SOP标准操作程序表
CREATE TABLE IF NOT EXISTS sops (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    alert_rule_id TEXT REFERENCES alert_rules(id) ON DELETE SET NULL,
    steps JSON NOT NULL,
    enabled INTEGER DEFAULT 1,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 案例表
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    alert_rule_id TEXT REFERENCES alert_rules(id) ON DELETE SET NULL,
    symptoms JSON,
    root_cause TEXT,
    solution TEXT,
    outcome TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 向量索引表（用于Chroma向量存储）
CREATE TABLE IF NOT EXISTS knowledge_vectors (
    id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL CHECK (content_type IN ('alert_rule', 'sop', 'case')),
    content_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_alert_rules_severity ON alert_rules(severity);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_sops_alert_rule ON sops(alert_rule_id);
CREATE INDEX IF NOT EXISTS idx_cases_alert_rule ON cases(alert_rule_id);
CREATE INDEX IF NOT EXISTS idx_vectors_content_type ON knowledge_vectors(content_type);
CREATE INDEX IF NOT EXISTS idx_vectors_content_id ON knowledge_vectors(content_id);

-- 触发器：更新updated_at
CREATE TRIGGER IF NOT EXISTS update_alert_rules_timestamp 
AFTER UPDATE ON alert_rules
BEGIN
    UPDATE alert_rules SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_sops_timestamp 
AFTER UPDATE ON sops
BEGIN
    UPDATE sops SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_cases_timestamp 
AFTER UPDATE ON cases
BEGIN
    UPDATE cases SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
