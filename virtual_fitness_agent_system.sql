-- 基于多智能体的虚拟游戏化全民健身智能辅助系统
-- MySQL 数据库结构脚本
-- 数据库名: virtual_fitness_agent_system
-- 使用方式:
--   mysql -uroot -p123456 < virtual_fitness_agent_system.sql

CREATE DATABASE IF NOT EXISTS `virtual_fitness_agent_system`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `virtual_fitness_agent_system`;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `dictionaries`;
DROP TABLE IF EXISTS `reports`;
DROP TABLE IF EXISTS `agent_logs`;
DROP TABLE IF EXISTS `tips`;
DROP TABLE IF EXISTS `levels`;
DROP TABLE IF EXISTS `point_logs`;
DROP TABLE IF EXISTS `user_badges`;
DROP TABLE IF EXISTS `badges`;
DROP TABLE IF EXISTS `challenge_records`;
DROP TABLE IF EXISTS `challenges`;
DROP TABLE IF EXISTS `recommendation_records`;
DROP TABLE IF EXISTS `environment_snapshots`;
DROP TABLE IF EXISTS `venues`;
DROP TABLE IF EXISTS `motion_metrics`;
DROP TABLE IF EXISTS `pose_records`;
DROP TABLE IF EXISTS `sessions`;
DROP TABLE IF EXISTS `exercise_standards`;
DROP TABLE IF EXISTS `exercises`;
DROP TABLE IF EXISTS `user_profiles`;
DROP TABLE IF EXISTS `users`;

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE `users` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
  `username` VARCHAR(100) UNIQUE NOT NULL COMMENT '登录用户名',
  `password` VARCHAR(255) NOT NULL COMMENT '登录密码，原型阶段明文保存',
  `nickname` VARCHAR(100) NOT NULL COMMENT '昵称',
  `age` INT DEFAULT 20 COMMENT '年龄',
  `fitness_level` VARCHAR(50) DEFAULT 'beginner' COMMENT '体能水平: beginner/intermediate/advanced',
  `injuries` TEXT COMMENT '伤病史',
  `preference` VARCHAR(255) DEFAULT '综合训练' COMMENT '运动偏好',
  `location` VARCHAR(255) DEFAULT '校园东区' COMMENT '当前位置',
  `points` INT DEFAULT 0 COMMENT '总积分',
  `level` INT DEFAULT 1 COMMENT '当前等级',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户基础信息表';

CREATE TABLE `user_profiles` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '画像ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `height_cm` DOUBLE COMMENT '身高cm',
  `weight_kg` DOUBLE COMMENT '体重kg',
  `bmi` DOUBLE COMMENT 'BMI',
  `weekly_goal` TEXT COMMENT '每周训练目标',
  `risk_level` VARCHAR(50) DEFAULT 'low' COMMENT '风险等级',
  `preferred_time` VARCHAR(100) COMMENT '偏好训练时间',
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  CONSTRAINT `fk_user_profiles_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户扩展画像表';

CREATE TABLE `exercises` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '动作ID',
  `name` VARCHAR(100) UNIQUE NOT NULL COMMENT '动作名称',
  `category` VARCHAR(100) NOT NULL COMMENT '动作分类',
  `difficulty` INT NOT NULL COMMENT '难度等级',
  `target` VARCHAR(255) NOT NULL COMMENT '训练目标',
  `equipment` VARCHAR(255) NOT NULL COMMENT '所需器材',
  `standard_json` TEXT NOT NULL COMMENT '动作标准JSON'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='动作库表';

CREATE TABLE `exercise_standards` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '动作标准ID',
  `exercise_id` INT NOT NULL COMMENT '动作ID',
  `metric_name` VARCHAR(100) NOT NULL COMMENT '指标名称',
  `ideal_value` DOUBLE COMMENT '理想值',
  `min_value` DOUBLE COMMENT '最小安全值',
  `max_value` DOUBLE COMMENT '最大安全值',
  `unit` VARCHAR(50) COMMENT '单位',
  `risk_hint` TEXT COMMENT '风险提示',
  CONSTRAINT `fk_exercise_standards_exercise`
    FOREIGN KEY (`exercise_id`) REFERENCES `exercises` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='动作评分标准表';

CREATE TABLE `sessions` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '训练记录ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `exercise_name` VARCHAR(100) NOT NULL COMMENT '训练动作',
  `score` INT NOT NULL COMMENT '训练得分',
  `duration` INT NOT NULL COMMENT '训练时长，单位秒',
  `points` INT NOT NULL COMMENT '本次获得积分',
  `feedback` TEXT NOT NULL COMMENT '训练反馈',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '训练时间',
  CONSTRAINT `fk_sessions_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='训练记录表';

CREATE TABLE `pose_records` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '姿态记录ID',
  `session_id` INT COMMENT '训练记录ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `exercise_name` VARCHAR(100) NOT NULL COMMENT '动作名称',
  `confidence` DOUBLE COMMENT '识别置信度',
  `stability_score` DOUBLE COMMENT '稳定性评分',
  `knee_angle` DOUBLE COMMENT '膝关节角度',
  `hip_angle` DOUBLE COMMENT '髋关节角度',
  `shoulder_balance` DOUBLE COMMENT '肩部平衡',
  `raw_landmarks_json` TEXT COMMENT 'MediaPipe关键点JSON',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
  CONSTRAINT `fk_pose_records_session`
    FOREIGN KEY (`session_id`) REFERENCES `sessions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_pose_records_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='姿态识别记录表';

CREATE TABLE `motion_metrics` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '动作指标ID',
  `session_id` INT NOT NULL COMMENT '训练记录ID',
  `metric_name` VARCHAR(100) NOT NULL COMMENT '指标名称',
  `metric_value` DOUBLE NOT NULL COMMENT '指标值',
  `score` INT COMMENT '指标得分',
  `status` VARCHAR(50) COMMENT '指标状态',
  `correction_advice` TEXT COMMENT '纠错建议',
  CONSTRAINT `fk_motion_metrics_session`
    FOREIGN KEY (`session_id`) REFERENCES `sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='动作细分指标表';

CREATE TABLE `venues` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '场馆ID',
  `name` VARCHAR(100) UNIQUE NOT NULL COMMENT '场馆名称',
  `location` VARCHAR(255) NOT NULL COMMENT '场馆位置',
  `equipment` VARCHAR(255) NOT NULL COMMENT '器材配置',
  `capacity` INT NOT NULL COMMENT '容量',
  `crowd_index` INT NOT NULL COMMENT '拥挤度',
  `air_quality` INT NOT NULL COMMENT '空气质量指数',
  `open_hours` VARCHAR(100) NOT NULL COMMENT '开放时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场馆表';

CREATE TABLE `environment_snapshots` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '环境快照ID',
  `venue_id` INT NOT NULL COMMENT '场馆ID',
  `crowd_index` INT NOT NULL COMMENT '拥挤度',
  `air_quality` INT NOT NULL COMMENT '空气质量',
  `temperature` DOUBLE NOT NULL COMMENT '温度',
  `weather` VARCHAR(100) NOT NULL COMMENT '天气',
  `captured_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '采集时间',
  CONSTRAINT `fk_environment_venue`
    FOREIGN KEY (`venue_id`) REFERENCES `venues` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场馆环境快照表';

CREATE TABLE `recommendation_records` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '推荐记录ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `recommendation_type` VARCHAR(100) NOT NULL COMMENT '推荐类型: exercise/venue/plan',
  `target_id` INT NOT NULL COMMENT '推荐对象ID',
  `target_name` VARCHAR(255) NOT NULL COMMENT '推荐对象名称',
  `match_score` DOUBLE NOT NULL COMMENT '匹配分',
  `reason` TEXT COMMENT '推荐理由',
  `agent_name` VARCHAR(100) COMMENT '推荐智能体名称',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '推荐时间',
  CONSTRAINT `fk_recommendation_records_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='推荐记录表';

CREATE TABLE `challenges` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '关卡ID',
  `title` VARCHAR(255) UNIQUE NOT NULL COMMENT '关卡标题',
  `exercise_name` VARCHAR(100) NOT NULL COMMENT '关联动作',
  `goal_text` TEXT NOT NULL COMMENT '关卡目标',
  `difficulty` INT NOT NULL COMMENT '关卡难度',
  `reward_points` INT NOT NULL COMMENT '奖励积分',
  `scene` VARCHAR(255) NOT NULL COMMENT '虚拟场景'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='训练关卡表';

CREATE TABLE `challenge_records` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '闯关记录ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `challenge_id` INT NOT NULL COMMENT '关卡ID',
  `session_id` INT COMMENT '训练记录ID',
  `status` VARCHAR(50) NOT NULL COMMENT '状态',
  `score` INT COMMENT '得分',
  `combo_count` INT DEFAULT 0 COMMENT '连击次数',
  `completed_at` DATETIME COMMENT '完成时间',
  CONSTRAINT `fk_challenge_records_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_challenge_records_challenge`
    FOREIGN KEY (`challenge_id`) REFERENCES `challenges` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_challenge_records_session`
    FOREIGN KEY (`session_id`) REFERENCES `sessions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='闯关记录表';

CREATE TABLE `badges` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '徽章ID',
  `name` VARCHAR(100) UNIQUE NOT NULL COMMENT '徽章名称',
  `condition_text` TEXT NOT NULL COMMENT '达成条件',
  `icon` VARCHAR(100) NOT NULL COMMENT '图标',
  `reward_points` INT DEFAULT 0 COMMENT '奖励积分'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='徽章表';

CREATE TABLE `user_badges` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户徽章ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `badge_id` INT NOT NULL COMMENT '徽章ID',
  `earned_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '获得时间',
  UNIQUE KEY `uq_user_badge` (`user_id`, `badge_id`),
  CONSTRAINT `fk_user_badges_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_user_badges_badge`
    FOREIGN KEY (`badge_id`) REFERENCES `badges` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户徽章关联表';

CREATE TABLE `point_logs` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '积分流水ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `source_type` VARCHAR(100) NOT NULL COMMENT '积分来源类型',
  `source_id` INT COMMENT '来源ID',
  `points_change` INT NOT NULL COMMENT '积分变化',
  `total_points` INT NOT NULL COMMENT '变化后总积分',
  `description` TEXT COMMENT '说明',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  CONSTRAINT `fk_point_logs_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='积分流水表';

CREATE TABLE `levels` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '等级规则ID',
  `level` INT UNIQUE NOT NULL COMMENT '等级',
  `min_points` INT NOT NULL COMMENT '最低积分',
  `title` VARCHAR(100) NOT NULL COMMENT '等级名称',
  `unlock_text` TEXT COMMENT '解锁说明'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='等级规则表';

CREATE TABLE `agent_logs` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '智能体日志ID',
  `user_id` INT COMMENT '用户ID',
  `agent_name` VARCHAR(100) NOT NULL COMMENT '智能体名称',
  `action` VARCHAR(255) NOT NULL COMMENT '动作',
  `result` TEXT NOT NULL COMMENT '结果',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  CONSTRAINT `fk_agent_logs_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体运行日志表';

CREATE TABLE `reports` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '报告ID',
  `user_id` INT NOT NULL COMMENT '用户ID',
  `report_type` VARCHAR(100) NOT NULL COMMENT '报告类型',
  `session_count` INT DEFAULT 0 COMMENT '训练次数',
  `average_score` DOUBLE DEFAULT 0 COMMENT '平均得分',
  `weak_exercise` VARCHAR(100) COMMENT '薄弱动作',
  `summary` TEXT NOT NULL COMMENT '报告摘要',
  `suggestion` TEXT COMMENT '建议',
  `generated_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
  CONSTRAINT `fk_reports_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='训练报告表';

CREATE TABLE `tips` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '提示ID',
  `title` VARCHAR(255) NOT NULL COMMENT '标题',
  `content` TEXT NOT NULL COMMENT '内容',
  `tag` VARCHAR(100) NOT NULL COMMENT '标签'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科学健身提示表';

CREATE TABLE `dictionaries` (
  `id` INT PRIMARY KEY AUTO_INCREMENT COMMENT '字典ID',
  `dict_type` VARCHAR(100) NOT NULL COMMENT '字典类型',
  `dict_key` VARCHAR(100) NOT NULL COMMENT '字典键',
  `dict_value` VARCHAR(255) NOT NULL COMMENT '字典值',
  `sort_order` INT DEFAULT 0 COMMENT '排序',
  `enabled` TINYINT DEFAULT 1 COMMENT '是否启用'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统字典表';

CREATE INDEX `idx_users_username` ON `users` (`username`);
CREATE INDEX `idx_user_profiles_user` ON `user_profiles` (`user_id`);
CREATE INDEX `idx_exercises_category` ON `exercises` (`category`, `difficulty`);
CREATE INDEX `idx_exercise_standards_exercise` ON `exercise_standards` (`exercise_id`);
CREATE INDEX `idx_sessions_user_time` ON `sessions` (`user_id`, `created_at` DESC);
CREATE INDEX `idx_pose_records_user_time` ON `pose_records` (`user_id`, `created_at` DESC);
CREATE INDEX `idx_motion_metrics_session` ON `motion_metrics` (`session_id`);
CREATE INDEX `idx_venues_location` ON `venues` (`location`);
CREATE INDEX `idx_environment_venue_time` ON `environment_snapshots` (`venue_id`, `captured_at` DESC);
CREATE INDEX `idx_recommendation_user_type` ON `recommendation_records` (`user_id`, `recommendation_type`, `created_at` DESC);
CREATE INDEX `idx_challenge_records_user` ON `challenge_records` (`user_id`, `status`);
CREATE INDEX `idx_user_badges_user` ON `user_badges` (`user_id`);
CREATE INDEX `idx_point_logs_user_time` ON `point_logs` (`user_id`, `created_at` DESC);
CREATE INDEX `idx_agent_logs_user_time` ON `agent_logs` (`user_id`, `created_at` DESC);
CREATE INDEX `idx_reports_user_type` ON `reports` (`user_id`, `report_type`, `generated_at` DESC);
CREATE INDEX `idx_dictionaries_type` ON `dictionaries` (`dict_type`, `sort_order`);

INSERT INTO `users` (`username`, `password`, `nickname`, `age`, `fitness_level`, `injuries`, `preference`, `location`, `points`, `level`)
VALUES ('demo', '123456', '李同学', 20, 'beginner', '', '综合训练', '校园东区', 0, 1);

INSERT INTO `levels` (`level`, `min_points`, `title`, `unlock_text`) VALUES
(1, 0, '新手体验者', '解锁基础动作和入门体感关卡'),
(2, 120, '稳定训练者', '解锁核心训练任务'),
(3, 240, '节奏挑战者', '解锁连续训练徽章'),
(4, 420, '高阶闯关者', '解锁高阶综合挑战'),
(5, 650, '全民健身达人', '解锁完整个性化训练计划');

INSERT INTO `dictionaries` (`dict_type`, `dict_key`, `dict_value`, `sort_order`, `enabled`) VALUES
('fitness_level', 'beginner', '新手', 1, 1),
('fitness_level', 'intermediate', '进阶', 2, 1),
('fitness_level', 'advanced', '熟练', 3, 1),
('exercise_category', 'strength', '力量', 1, 1),
('exercise_category', 'aerobic', '有氧', 2, 1),
('exercise_category', 'core', '核心', 3, 1),
('exercise_category', 'flexibility', '柔韧', 4, 1),
('risk_level', 'low', '低风险', 1, 1),
('risk_level', 'medium', '中风险', 2, 1),
('risk_level', 'high', '高风险', 3, 1);

INSERT INTO `tips` (`title`, `content`, `tag`) VALUES
('热身先行', '正式训练前进行 5-8 分钟动态热身，可降低拉伤风险。', '安全'),
('动作质量优先', '评分低于 70 时建议降低速度，先保证动作幅度和关节方向。', '纠错'),
('循序渐进', '新手每周增加训练量不宜超过 10%，避免过度疲劳。', '计划');
