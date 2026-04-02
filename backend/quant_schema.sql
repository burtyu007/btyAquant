
CREATE DATABASE IF NOT EXISTS `quant`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE `quant`;

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `analysis_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `analysis_records` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '分析记录主键 ID',
  `user_id` int NOT NULL COMMENT '所属用户 ID，关联 users.id',
  `symbol` varchar(16) NOT NULL COMMENT '分析标的代码',
  `market` varchar(8) NOT NULL COMMENT '市场标识，例如 a 或 hk',
  `strategy_key` varchar(80) NOT NULL COMMENT '策略注册键，例如 bollinger_mean_reversion',
  `lookback_period` varchar(16) NOT NULL DEFAULT '2y' COMMENT '历史回看区间键，例如 6m、1y、2y',
  `bollinger_window` varchar(16) NOT NULL DEFAULT '20d' COMMENT '布林带窗口键，例如 10d、20d、30d、60d',
  `price_frequency` varchar(16) NOT NULL DEFAULT 'daily' COMMENT '分析使用的K线频率，例如 daily',
  `request_payload` text NOT NULL COMMENT '分析请求参数 JSON',
  `result_payload` text NOT NULL COMMENT '策略分析结果 JSON 快照',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '分析记录创建时间',
  PRIMARY KEY (`id`),
  KEY `ix_analysis_records_market` (`market`),
  KEY `ix_analysis_records_id` (`id`),
  KEY `ix_analysis_records_user_id` (`user_id`),
  KEY `ix_analysis_records_strategy_key` (`strategy_key`),
  KEY `ix_analysis_records_symbol` (`symbol`),
  CONSTRAINT `analysis_records_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='策略分析记录表，保存每次量化分析的请求参数和结果快照';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `market_news`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `market_news` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '消息主键 ID',
  `provider` varchar(32) NOT NULL COMMENT '数据接入方，例如 akshare 或 mx',
  `platform` varchar(64) NOT NULL COMMENT '消息来源平台标识，例如 eastmoney、cls、sina、mx_hot',
  `source` varchar(128) DEFAULT NULL COMMENT '页面展示用的来源名称',
  `title` varchar(255) NOT NULL COMMENT '新闻标题',
  `summary` text COMMENT '新闻摘要或短内容',
  `content` text COMMENT '新闻正文或详细内容',
  `info_type` varchar(64) DEFAULT NULL COMMENT '资讯类型，例如 快讯、要闻、公告',
  `security` varchar(255) DEFAULT NULL COMMENT '关联证券或主题名称',
  `url` varchar(500) DEFAULT NULL COMMENT '原始资讯链接',
  `published_at` datetime DEFAULT NULL COMMENT '资讯发布时间，供站内按时间倒序展示',
  `published_at_text` varchar(64) DEFAULT NULL COMMENT '原始发布时间文本，解析失败时保留',
  `content_hash` varchar(64) NOT NULL COMMENT '基于平台、标题、内容和发布时间生成的去重哈希',
  `raw_payload` text COMMENT '原始消息 JSON 快照，便于排查与回溯',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息入库时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_market_news_content_hash` (`content_hash`),
  KEY `ix_market_news_platform` (`platform`),
  KEY `ix_market_news_id` (`id`),
  KEY `ix_market_news_provider` (`provider`),
  KEY `ix_market_news_published_at` (`published_at`),
  KEY `ix_market_news_title` (`title`)
) ENGINE=InnoDB AUTO_INCREMENT=941 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='财经热点消息表，聚合 AKShare 与 MX 抓取的各平台财经资讯，供站内热点新闻流展示';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `quant_regression_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `quant_regression_history` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '量化回归历史主键 ID',
  `user_id` int NOT NULL COMMENT '所属用户 ID，关联 users.id',
  `symbol` varchar(16) NOT NULL COMMENT '回归标的代码',
  `market` varchar(8) NOT NULL COMMENT '市场标识，例如 a 或 hk',
  `algorithm_key` varchar(80) NOT NULL COMMENT '量化算法键，例如 bollinger_mean_reversion',
  `source_label` varchar(128) DEFAULT NULL COMMENT '回归使用的数据源说明',
  `request_payload` text NOT NULL COMMENT '回归请求参数 JSON',
  `result_payload` text NOT NULL COMMENT '回归结果 JSON，兼容多策略扩展',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '回归记录创建时间',
  PRIMARY KEY (`id`),
  KEY `ix_quant_regression_history_user_id` (`user_id`),
  KEY `ix_quant_regression_history_market` (`market`),
  KEY `ix_quant_regression_history_symbol` (`symbol`),
  KEY `ix_quant_regression_history_id` (`id`),
  KEY `ix_quant_regression_history_algorithm_key` (`algorithm_key`),
  CONSTRAINT `quant_regression_history_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='量化回归历史表，保存基于历史数据的策略回测结果，使用 JSON 结果兼容多种量化算法扩展';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `policy_files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `policy_files` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '自增id',
  `name` varchar(128) NOT NULL DEFAULT '' COMMENT '策略名称',
  `folder` varchar(255) DEFAULT NULL COMMENT '策略目录',
  `readme` varchar(255) NOT NULL DEFAULT '' COMMENT '策略脚本使用文档',
  `path` varchar(255) NOT NULL DEFAULT '' COMMENT '文件路径',
  `results` varchar(255) DEFAULT NULL COMMENT '结果文件',
  `list_show_fields` varchar(500) NOT NULL DEFAULT '' COMMENT '列表展示字段，不超过5个',
  `created_user_id` int unsigned NOT NULL COMMENT '策略创建人',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='量化策略文件表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '用户主键 ID',
  `username` varchar(50) NOT NULL COMMENT '登录用户名，系统内唯一',
  `password_hash` varchar(255) NOT NULL COMMENT '登录密码的 PBKDF2 哈希值',
  `is_admin` tinyint(1) NOT NULL COMMENT '是否为管理员，1 表示管理员',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '账号创建时间',
  `mx_api_key_encrypted` text COMMENT '用户专属 MX API Key 的 RSA 加密密文',
  `is_super_admin` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否为超级管理员，1 表示超级管理员',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_username` (`username`),
  KEY `ix_users_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统用户表，存储登录账号、权限角色和用户专属 MX Key 密文';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `watchlist_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `watchlist_items` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自选记录主键 ID',
  `user_id` int NOT NULL COMMENT '所属用户 ID，关联 users.id',
  `symbol` varchar(16) NOT NULL COMMENT '自选股票代码',
  `market` varchar(8) NOT NULL COMMENT '市场标识，例如 a 或 hk',
  `display_name` varchar(80) DEFAULT NULL COMMENT '股票名称或展示名称',
  `last_price` float DEFAULT NULL COMMENT '最近一次刷新得到的当前价格',
  `last_price_at` datetime DEFAULT NULL COMMENT '最近一次行情刷新时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '自选记录创建时间',
  `open_price` double DEFAULT NULL COMMENT '最近一次刷新得到的开盘价',
  `close_price` double DEFAULT NULL COMMENT '最近一次刷新得到的收盘价或最新收盘参考价',
  `day_high` double DEFAULT NULL COMMENT '最近一次刷新得到的当日最高价',
  `day_low` double DEFAULT NULL COMMENT '最近一次刷新得到的当日最低价',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_watchlist_user_symbol_market` (`user_id`,`symbol`,`market`),
  KEY `ix_watchlist_items_id` (`id`),
  KEY `ix_watchlist_items_user_id` (`user_id`),
  KEY `ix_watchlist_items_market` (`market`),
  KEY `ix_watchlist_items_symbol` (`symbol`),
  CONSTRAINT `watchlist_items_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=55 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户本地自选股表，保存每个用户维护的股票及最近一次刷新行情';
/*!40101 SET character_set_client = @saved_cs_client */;

INSERT INTO `users` (
  `id`,
  `username`,
  `password_hash`,
  `mx_api_key_encrypted`,
  `created_at`,
  `is_admin`,
  `is_super_admin`
) VALUES (
  1,
  'admin',
  'pbkdf2_sha256$600000$f6d7bc62cccc0d6a40ecf2c720ee698d$c2691621ef2aaca31713a2d3f9c0c82854eefc337901b2cba39dbf2298c8d6a9',
  NULL,
  '2026-03-26 10:43:54',
  1,
  1
);

ALTER TABLE `users` AUTO_INCREMENT = 2;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
