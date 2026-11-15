-- Campaign API tables (PostgreSQL / Neon). Generated from app/models.py.
-- The API creates these automatically on start-up; this file is for review and manual setup.

CREATE TABLE IF NOT EXISTS campaigns (
	id SERIAL NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	title VARCHAR(120) NOT NULL, 
	summary VARCHAR(280) NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	image_url VARCHAR(500), 
	location VARCHAR(120), 
	business_name VARCHAR(120), 
	offer_text VARCHAR(200), 
	start_date DATE NOT NULL, 
	end_date DATE, 
	status VARCHAR(20) NOT NULL, 
	rejection_reason VARCHAR(500), 
	created_by INTEGER NOT NULL, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_campaigns_type CHECK (type IN ('social_cause', 'business_promotion')), 
	CONSTRAINT ck_campaigns_status CHECK (status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'ARCHIVED'))
);

CREATE INDEX IF NOT EXISTS ix_campaigns_category ON campaigns (category);

CREATE INDEX IF NOT EXISTS ix_campaigns_created_by ON campaigns (created_by);

CREATE INDEX IF NOT EXISTS ix_campaigns_public ON campaigns (status, start_date, end_date);

CREATE TABLE IF NOT EXISTS campaign_joins (
	campaign_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (campaign_id, user_id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_campaign_joins_user_id ON campaign_joins (user_id);

CREATE TABLE IF NOT EXISTS campaign_moderation_log (
	id SERIAL NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	old_status VARCHAR(20), 
	new_status VARCHAR(20) NOT NULL, 
	actor_id INTEGER NOT NULL, 
	reason VARCHAR(500), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE, 
	CONSTRAINT ck_moderation_old_status CHECK (old_status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'ARCHIVED')), 
	CONSTRAINT ck_moderation_new_status CHECK (new_status IN ('DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'ARCHIVED'))
);

CREATE INDEX IF NOT EXISTS ix_campaign_moderation_log_campaign_id ON campaign_moderation_log (campaign_id);
