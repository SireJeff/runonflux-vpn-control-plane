CREATE TABLE admin_alerts (
	id SERIAL NOT NULL, 
	alert_type VARCHAR(100) NOT NULL, 
	priority VARCHAR(50) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	message TEXT NOT NULL, 
	extra_data JSONB, 
	sent_telegram BOOLEAN, 
	sent_email BOOLEAN, 
	acknowledged BOOLEAN, 
	acknowledged_by INTEGER, 
	acknowledged_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(acknowledged_by) REFERENCES users (id) ON DELETE SET NULL
)

CREATE TABLE admin_bots (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	bot_token_enc BYTEA NOT NULL, 
	bot_username VARCHAR(100) NOT NULL, 
	bot_user_id BIGINT NOT NULL, 
	bot_display_name VARCHAR(100), 
	welcome_message_fa TEXT, 
	welcome_message_en TEXT, 
	card_number VARCHAR(20), 
	card_holder_name VARCHAR(100), 
	crypto_address VARCHAR(255), 
	crypto_network VARCHAR(50), 
	crypto_memo VARCHAR(255), 
	support_phone VARCHAR(20), 
	support_telegram VARCHAR(50), 
	default_macro_region VARCHAR(5) DEFAULT 'eu' NOT NULL, 
	webhook_secret VARCHAR(64) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	webhook_registered_at TIMESTAMP WITHOUT TIME ZONE, 
	last_update_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_bots_admin_id UNIQUE (admin_id), 
	CONSTRAINT uq_admin_bots_bot_user_id UNIQUE (bot_user_id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE
)

CREATE TABLE admin_packages (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	traffic_limit_gb NUMERIC(10, 2) NOT NULL, 
	duration_days INTEGER NOT NULL, 
	price_tomans NUMERIC(12, 2) NOT NULL, 
	region_count SMALLINT DEFAULT '1' NOT NULL, 
	all_regions BOOLEAN DEFAULT 'false' NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	display_order INTEGER DEFAULT '0', 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_packages_admin_name UNIQUE (admin_id, name), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE
)

CREATE TABLE admin_referral_configs (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	is_enabled BOOLEAN NOT NULL, 
	reward_percentage NUMERIC(5, 2) DEFAULT '10.00' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	UNIQUE (admin_id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE
)

CREATE TABLE admin_referral_earnings (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	referrer_user_id INTEGER NOT NULL, 
	referred_user_id INTEGER NOT NULL, 
	order_id INTEGER NOT NULL, 
	commission_percent NUMERIC(5, 2) NOT NULL, 
	amount_tomans NUMERIC(12, 2) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE, 
	FOREIGN KEY(referrer_user_id) REFERENCES admin_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(referred_user_id) REFERENCES admin_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(order_id) REFERENCES user_orders (id) ON DELETE CASCADE
)

CREATE TABLE admin_tld_states (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	pinned_tld_id INTEGER, 
	effective_tld_id INTEGER, 
	source VARCHAR(12) NOT NULL, 
	assigned_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_tld_state_admin_purpose UNIQUE (admin_id, purpose), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE, 
	FOREIGN KEY(pinned_tld_id) REFERENCES registered_tlds (id) ON DELETE SET NULL, 
	FOREIGN KEY(effective_tld_id) REFERENCES registered_tlds (id) ON DELETE SET NULL
)

CREATE TABLE admin_users (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	password_hash VARCHAR(255), 
	password_enc BYTEA, 
	display_name VARCHAR(100), 
	remark TEXT, 
	status VARCHAR(20), 
	traffic_used_bytes BIGINT, 
	traffic_limit_bytes BIGINT, 
	subscription_token VARCHAR(64), 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	last_connection_refresh_at TIMESTAMP WITHOUT TIME ZONE, 
	assigned_domain_id INTEGER, 
	telegram_id BIGINT, 
	telegram_chat_id BIGINT, 
	registered_bot_id INTEGER, 
	current_order_id INTEGER, 
	language VARCHAR(5) DEFAULT 'fa' NOT NULL, 
	referral_code VARCHAR(50), 
	referred_by_user_id INTEGER, 
	wallet_credit_tomans NUMERIC(12, 2) DEFAULT '0' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_admin_user UNIQUE (admin_id, username), 
	CONSTRAINT uq_admin_users_admin_tg UNIQUE (admin_id, telegram_id), 
	CONSTRAINT uq_admin_users_referral_code UNIQUE (admin_id, referral_code), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_domain_id) REFERENCES fdm_domains (id) ON DELETE SET NULL, 
	FOREIGN KEY(registered_bot_id) REFERENCES admin_bots (id) ON DELETE SET NULL, 
	FOREIGN KEY(referred_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL
)

CREATE TABLE admins (
	id SERIAL NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	display_name VARCHAR(100), 
	telegram_id VARCHAR(50), 
	whatsapp_number VARCHAR(20), 
	phone_number VARCHAR(20), 
	wallet_balance NUMERIC(12, 6), 
	status VARCHAR(20), 
	assigned_password VARCHAR(255), 
	notes TEXT, 
	default_macro_region VARCHAR(5) DEFAULT 'eu', 
	approved_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(approved_by) REFERENCES admins (id)
)

CREATE TABLE api_request_metrics_hourly (
	id SERIAL NOT NULL, 
	hour_start TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	request_count INTEGER NOT NULL, 
	total_response_time_ms BIGINT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_api_request_metrics_hourly_hour_start UNIQUE (hour_start)
)

CREATE TABLE auth_logs (
	id BIGSERIAL NOT NULL, 
	user_id INTEGER, 
	event_type VARCHAR(50) NOT NULL, 
	success BOOLEAN, 
	ip_address INET, 
	user_agent TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
)

CREATE TABLE bandwidth_time_series (
	id SERIAL NOT NULL, 
	period_type VARCHAR(10) NOT NULL, 
	period_start TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	total_bytes_uploaded BIGINT, 
	total_bytes_downloaded BIGINT, 
	total_bytes BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id)
)

CREATE TABLE connection_logs (
	id BIGSERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	instance_id INTEGER, 
	connected_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	disconnected_at TIMESTAMP WITHOUT TIME ZONE, 
	bytes_uploaded BIGINT, 
	bytes_downloaded BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id), 
	FOREIGN KEY(instance_id) REFERENCES protocol_instances (id)
)

CREATE TABLE connection_violations (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	max_allowed INTEGER NOT NULL, 
	attempted_connections INTEGER NOT NULL, 
	violation_time TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	action_taken VARCHAR(50), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
)

CREATE TABLE fdm_deployments (
	id SERIAL NOT NULL, 
	flux_app_name VARCHAR(255) NOT NULL, 
	region VARCHAR(2) NOT NULL, 
	domain_pool_size INTEGER, 
	base_domain VARCHAR(255), 
	protocol_name VARCHAR(50), 
	health_check_port INTEGER, 
	socks5_port INTEGER, 
	is_active BOOLEAN, 
	last_sync_at TIMESTAMP WITHOUT TIME ZONE, 
	last_sync_status VARCHAR(50), 
	consecutive_failures INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_deployment_app_region UNIQUE (flux_app_name, region)
)

CREATE TABLE fdm_domains (
	id SERIAL NOT NULL, 
	deployment_id INTEGER NOT NULL, 
	tld_id INTEGER, 
	domain_name VARCHAR(255) NOT NULL, 
	domain_id VARCHAR(20) NOT NULL, 
	current_ip INET, 
	current_instance_id INTEGER, 
	dns_record_id VARCHAR(255), 
	health_status VARCHAR(50), 
	last_health_check TIMESTAMP WITHOUT TIME ZONE, 
	assigned_users_count INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(deployment_id) REFERENCES fdm_deployments (id) ON DELETE CASCADE, 
	FOREIGN KEY(tld_id) REFERENCES registered_tlds (id) ON DELETE SET NULL, 
	UNIQUE (domain_name), 
	FOREIGN KEY(current_instance_id) REFERENCES protocol_instances (id) ON DELETE SET NULL
)

CREATE TABLE fdm_ip_liveness (
	id SERIAL NOT NULL, 
	flux_app_name VARCHAR(255) NOT NULL, 
	ip_address INET NOT NULL, 
	consecutive_failures INTEGER DEFAULT '0' NOT NULL, 
	last_checked_at TIMESTAMP WITHOUT TIME ZONE, 
	last_live_at TIMESTAMP WITHOUT TIME ZONE, 
	demoted_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_fdm_ip_liveness_app_ip UNIQUE (flux_app_name, ip_address)
)

CREATE TABLE fdm_sync_logs (
	id SERIAL NOT NULL, 
	deployment_id INTEGER NOT NULL, 
	sync_started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	sync_completed_at TIMESTAMP WITHOUT TIME ZONE, 
	instances_found INTEGER, 
	instances_healthy INTEGER, 
	domains_updated INTEGER, 
	errors JSONB, 
	status VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(deployment_id) REFERENCES fdm_deployments (id) ON DELETE CASCADE
)

CREATE TABLE flux_app_registrations (
	id SERIAL NOT NULL, 
	app_name VARCHAR(255) NOT NULL, 
	protocol_ports JSONB NOT NULL, 
	is_active BOOLEAN, 
	registered_by INTEGER, 
	last_discovery_at TIMESTAMP WITHOUT TIME ZONE, 
	last_discovery_ips JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	expected_instances INTEGER, 
	spec_components JSONB, 
	spec_geolocation JSONB, 
	last_spec_fetched_at TIMESTAMP WITHOUT TIME ZONE, 
	last_spec_status VARCHAR(50), 
	PRIMARY KEY (id), 
	UNIQUE (app_name)
)

CREATE TABLE ip_change_quota (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	date DATE DEFAULT CURRENT_DATE NOT NULL, 
	changes_used INTEGER, 
	daily_limit INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_date UNIQUE (user_id, date), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

CREATE TABLE ip_change_requests (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	old_instance_id INTEGER, 
	new_instance_id INTEGER, 
	requested_country_code VARCHAR(2), 
	status VARCHAR(50), 
	denial_reason TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	processed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE, 
	FOREIGN KEY(old_instance_id) REFERENCES protocol_instances (id), 
	FOREIGN KEY(new_instance_id) REFERENCES protocol_instances (id)
)

CREATE TABLE payments (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER, 
	amount_usd DECIMAL(10, 2) NOT NULL, 
	payment_method VARCHAR(50) NOT NULL, 
	status VARCHAR(50), 
	transaction_id VARCHAR(255), 
	deposit_to_wallet BOOLEAN, 
	extra_data JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE SET NULL
)

CREATE TABLE platform_settings (
	id SERIAL NOT NULL, 
	key VARCHAR(100) NOT NULL, 
	value TEXT NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	UNIQUE (key)
)

CREATE TABLE protocol_daily_summaries (
	id SERIAL NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	summary_date DATE NOT NULL, 
	total_bytes_uploaded BIGINT, 
	total_bytes_downloaded BIGINT, 
	total_connections INTEGER, 
	unique_users INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_protocol_date UNIQUE (protocol_id, summary_date)
)

CREATE TABLE protocol_instances (
	id SERIAL NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	flux_app_name VARCHAR(255) NOT NULL, 
	component_name VARCHAR(50), 
	instance_number INTEGER NOT NULL, 
	flux_node_name VARCHAR(255), 
	ip_address INET NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	country_name VARCHAR(100) NOT NULL, 
	city VARCHAR(100), 
	last_health_check TIMESTAMP WITHOUT TIME ZONE, 
	health_status VARCHAR(50), 
	is_active BOOLEAN, 
	current_connections INTEGER, 
	max_connections INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_app_component_instance UNIQUE (flux_app_name, component_name, instance_number), 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
)

CREATE TABLE protocols (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	slug VARCHAR(50) NOT NULL, 
	display_name VARCHAR(100), 
	description TEXT, 
	flux_app_name VARCHAR(255), 
	default_port INTEGER, 
	exposed_port INTEGER, 
	is_active BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
)

CREATE TABLE referral_earnings (
	id SERIAL NOT NULL, 
	referrer_id INTEGER NOT NULL, 
	referred_user_id INTEGER NOT NULL, 
	payment_id INTEGER, 
	commission_percent DECIMAL(5, 2) NOT NULL, 
	amount_usd DECIMAL(10, 2) NOT NULL, 
	credited_to_wallet BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(referrer_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(referred_user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL
)

CREATE TABLE registered_tlds (
	id SERIAL NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	dns_provider VARCHAR(20) NOT NULL, 
	zone_id VARCHAR(255), 
	purpose VARCHAR(20) NOT NULL, 
	server_ip VARCHAR(45), 
	is_active BOOLEAN, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_registered_tlds_domain_purpose UNIQUE (domain, purpose)
)

CREATE TABLE renewal_warnings (
	id SERIAL NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	days_before_expiration INTEGER NOT NULL, 
	sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	user_action VARCHAR(50), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_subscription_warning_days UNIQUE (subscription_id, days_before_expiration), 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

CREATE TABLE subscription_plans (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	tier VARCHAR(50) NOT NULL, 
	duration_months INTEGER NOT NULL, 
	price_usd DECIMAL(10, 2) NOT NULL, 
	max_protocols INTEGER, 
	max_connections INTEGER, 
	data_limit_gb INTEGER, 
	daily_ip_changes INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
)

CREATE TABLE subscriptions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	plan_id INTEGER NOT NULL, 
	status VARCHAR(50), 
	is_active BOOLEAN, 
	is_trial BOOLEAN, 
	started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	auto_renew BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(plan_id) REFERENCES subscription_plans (id)
)

CREATE TABLE support_messages (
	id SERIAL NOT NULL, 
	ticket_id INTEGER NOT NULL, 
	sender_id INTEGER NOT NULL, 
	message TEXT NOT NULL, 
	is_admin BOOLEAN, 
	is_internal BOOLEAN, 
	telegram_message_id BIGINT, 
	read_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ticket_id) REFERENCES support_tickets (id) ON DELETE CASCADE, 
	FOREIGN KEY(sender_id) REFERENCES users (id) ON DELETE CASCADE
)

CREATE TABLE support_tickets (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	ticket_number VARCHAR(32), 
	subject VARCHAR(500) NOT NULL, 
	description TEXT, 
	category VARCHAR(50), 
	status VARCHAR(50), 
	priority VARCHAR(50), 
	assigned_to INTEGER, 
	telegram_message_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_to) REFERENCES users (id) ON DELETE SET NULL
)

CREATE TABLE system_settings (
	id INTEGER NOT NULL, 
	trial_days INTEGER NOT NULL, 
	referral_commission_bronze NUMERIC(5, 2) NOT NULL, 
	referral_commission_silver NUMERIC(5, 2) NOT NULL, 
	referral_commission_gold NUMERIC(5, 2) NOT NULL, 
	referral_commission_platinum NUMERIC(5, 2) NOT NULL, 
	maintenance_mode BOOLEAN NOT NULL, 
	max_ip_changes_per_month INTEGER NOT NULL, 
	PRIMARY KEY (id)
)

CREATE TABLE tld_usage_daily (
	id SERIAL NOT NULL, 
	snapshot_date DATE NOT NULL, 
	purpose VARCHAR(20) NOT NULL, 
	tld_id INTEGER, 
	domain_snapshot VARCHAR(255) NOT NULL, 
	active_user_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tld_usage_daily_date_purpose_tld UNIQUE (snapshot_date, purpose, tld_id), 
	FOREIGN KEY(tld_id) REFERENCES registered_tlds (id) ON DELETE SET NULL
)

CREATE TABLE traffic_counters (
	id BIGSERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	protocol VARCHAR(20) NOT NULL, 
	instance_id VARCHAR(64) NOT NULL, 
	last_cumulative_in BIGINT NOT NULL, 
	last_cumulative_out BIGINT NOT NULL, 
	boot_id VARCHAR(64) DEFAULT '' NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_traffic_counter UNIQUE (user_id, protocol, instance_id, boot_id), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id)
)

CREATE TABLE traffic_logs (
	id BIGSERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	admin_id INTEGER NOT NULL, 
	protocol VARCHAR(20) NOT NULL, 
	region_code VARCHAR(5) NOT NULL, 
	bytes_in BIGINT, 
	bytes_out BIGINT, 
	session_started_at TIMESTAMP WITHOUT TIME ZONE, 
	session_ended_at TIMESTAMP WITHOUT TIME ZONE, 
	instance_ip VARCHAR(45), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id)
)

CREATE TABLE translations (
	id SERIAL NOT NULL, 
	key VARCHAR(255) NOT NULL, 
	language VARCHAR(5) NOT NULL, 
	value TEXT NOT NULL, 
	context VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_translation_key_language UNIQUE (key, language)
)

CREATE TABLE trial_activations (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	telegram_user_id BIGINT NOT NULL, 
	telegram_username VARCHAR(255), 
	started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	converted_to_paid BOOLEAN, 
	conversion_date TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

CREATE TABLE usage_alerts (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	threshold_percent INTEGER NOT NULL, 
	data_limit_gb INTEGER NOT NULL, 
	data_used_gb DECIMAL(10, 2) NOT NULL, 
	sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_subscription_threshold UNIQUE (subscription_id, threshold_percent), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE
)

CREATE TABLE usage_metrics_daily (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	usage_date DATE NOT NULL, 
	bytes_uploaded BIGINT NOT NULL, 
	bytes_downloaded BIGINT NOT NULL, 
	connection_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_usage_daily_user_protocol_date UNIQUE (user_id, protocol_id, usage_date), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
)

CREATE TABLE usage_metrics_hourly (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	hour_start TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	bytes_uploaded BIGINT NOT NULL, 
	bytes_downloaded BIGINT NOT NULL, 
	connection_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_usage_hourly_user_protocol_hour UNIQUE (user_id, protocol_id, hour_start), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
)

CREATE TABLE user_adjustments (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	admin_id INTEGER NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	details JSONB NOT NULL, 
	reason TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(admin_id) REFERENCES admins (id)
)

CREATE TABLE user_credentials (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	credential_data JSONB NOT NULL, 
	server_location VARCHAR(100), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_subscription_protocol UNIQUE (subscription_id, protocol_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
)

CREATE TABLE user_credentials_v2 (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	protocol VARCHAR(20) NOT NULL, 
	credential_data JSONB NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_protocol UNIQUE (user_id, protocol), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id) ON DELETE CASCADE
)

CREATE TABLE user_orders (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	admin_id INTEGER NOT NULL, 
	package_id INTEGER, 
	package_snapshot JSONB NOT NULL, 
	macro_region VARCHAR(5) NOT NULL, 
	macro_regions JSONB, 
	amount_tomans NUMERIC(12, 2) NOT NULL, 
	wallet_credit_applied_tomans NUMERIC(12, 2) DEFAULT '0' NOT NULL, 
	status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	receipt_file_id VARCHAR(255), 
	receipt_file_unique_id VARCHAR(255), 
	receipt_local_path VARCHAR(500), 
	reviewer_admin_id INTEGER, 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE, 
	admin_notes TEXT, 
	rejection_reason TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	payment_method VARCHAR(10) DEFAULT 'card' NOT NULL, 
	crypto_txid VARCHAR(255), 
	crypto_link TEXT, 
	amount_usd_snapshot NUMERIC(12, 2), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id) ON DELETE CASCADE, 
	FOREIGN KEY(admin_id) REFERENCES admins (id), 
	FOREIGN KEY(package_id) REFERENCES admin_packages (id) ON DELETE SET NULL, 
	FOREIGN KEY(reviewer_admin_id) REFERENCES admins (id)
)

CREATE TABLE user_protocol_assignments (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	protocol_id INTEGER NOT NULL, 
	instance_id INTEGER NOT NULL, 
	assigned_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_assignment_subscription_protocol UNIQUE (subscription_id, protocol_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_id) REFERENCES protocols (id) ON DELETE CASCADE, 
	FOREIGN KEY(instance_id) REFERENCES protocol_instances (id)
)

CREATE TABLE user_regions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	macro_region VARCHAR(5) NOT NULL, 
	is_primary BOOLEAN DEFAULT 'true' NOT NULL, 
	status VARCHAR(20) DEFAULT 'active' NOT NULL, 
	region_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	activated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_region_user_macro UNIQUE (user_id, macro_region), 
	FOREIGN KEY(user_id) REFERENCES admin_users (id) ON DELETE CASCADE
)

CREATE TABLE users (
	id SERIAL NOT NULL, 
	telegram_user_id BIGINT NOT NULL, 
	telegram_username VARCHAR(255), 
	email VARCHAR(255), 
	flux_wallet_address VARCHAR(255), 
	referral_code VARCHAR(50), 
	referred_by INTEGER, 
	referral_tier VARCHAR(50), 
	total_referrals INTEGER, 
	referral_earnings_usd DECIMAL(10, 2), 
	wallet_balance DECIMAL(10, 2), 
	trial_used BOOLEAN, 
	trial_started_at TIMESTAMP WITHOUT TIME ZONE, 
	trial_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	language VARCHAR(5), 
	notification_enabled BOOLEAN, 
	is_admin BOOLEAN, 
	is_deleted BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITHOUT TIME ZONE, 
	deletion_scheduled_at TIMESTAMP WITHOUT TIME ZONE, 
	refresh_token_jti VARCHAR(255), 
	refresh_token_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(referred_by) REFERENCES users (id) ON DELETE SET NULL, 
	UNIQUE (refresh_token_jti)
)

CREATE TABLE wallet_transactions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount_usd DECIMAL(10, 2) NOT NULL, 
	transaction_type VARCHAR(50) NOT NULL, 
	payment_id INTEGER, 
	subscription_id INTEGER, 
	reference_id VARCHAR(255), 
	status VARCHAR(50), 
	description TEXT, 
	balance_before DECIMAL(10, 2), 
	balance_after DECIMAL(10, 2), 
	extra_data JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL, 
	FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE SET NULL
)

CREATE TABLE wallet_transactions_v2 (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	amount_usd NUMERIC(12, 6) NOT NULL, 
	transaction_type VARCHAR(50) NOT NULL, 
	status VARCHAR(20), 
	description TEXT, 
	reference_id VARCHAR(255), 
	balance_before NUMERIC(12, 6), 
	balance_after NUMERIC(12, 6), 
	extra_data JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id) ON DELETE CASCADE
)

CREATE TABLE wire_orders (
	id SERIAL NOT NULL, 
	admin_id INTEGER NOT NULL, 
	amount_tomans NUMERIC(12, 2) NOT NULL, 
	amount_usd NUMERIC(12, 2), 
	contact_telegram VARCHAR(50) NOT NULL, 
	contact_whatsapp VARCHAR(20), 
	contact_phone VARCHAR(20), 
	notes TEXT, 
	status VARCHAR(20), 
	admin_notes TEXT, 
	reviewed_by INTEGER, 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	payment_method VARCHAR(10) DEFAULT 'wire' NOT NULL, 
	crypto_txid VARCHAR(255), 
	crypto_link TEXT, 
	usd_rate_snapshot NUMERIC(12, 2), 
	PRIMARY KEY (id), 
	FOREIGN KEY(admin_id) REFERENCES admins (id), 
	FOREIGN KEY(reviewed_by) REFERENCES admins (id)
)

CREATE TABLE withdrawal_requests (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount_usd DECIMAL(10, 2) NOT NULL, 
	withdrawal_method VARCHAR(50) NOT NULL, 
	withdrawal_details JSONB NOT NULL, 
	status VARCHAR(50), 
	admin_notes TEXT, 
	processed_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	processed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(processed_by) REFERENCES users (id) ON DELETE SET NULL
)