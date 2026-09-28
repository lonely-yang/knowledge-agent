-- 为 kh_document 增加 3 个 MQ 流程子状态列(幂等,可重复执行)
-- 子状态: NULL未开始 / 0解析中 / 1成功 / 2失败
-- 总解析状态(parse_status)在 /pg/check_all 读取时聚合计算,不落库
ALTER TABLE kh_document ADD COLUMN IF NOT EXISTS idx_status SMALLINT;
ALTER TABLE kh_document ADD COLUMN IF NOT EXISTS rag_status SMALLINT;
ALTER TABLE kh_document ADD COLUMN IF NOT EXISTS kg_status SMALLINT;
