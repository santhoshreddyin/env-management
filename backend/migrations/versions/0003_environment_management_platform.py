"""environment management platform

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06 13:01:19.610882
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('prefix', sa.String(length=16), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('bulk_operations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=False),
    sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rolled_back_by', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('config_template_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('env_type', sa.String(length=20), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('is_secret', sa.Boolean(), nullable=False),
    sa.Column('default_value', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('config_template_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_config_template_keys_env_type'), ['env_type'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recipient', sa.String(length=200), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('event', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('entity_id', sa.String(length=100), nullable=True),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notification_user_read', ['recipient', 'read'], unique=False)

    op.create_table('promotion_paths',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('stages', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('role_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('principal', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=30), nullable=False),
    sa.Column('scope_type', sa.String(length=20), nullable=False),
    sa.Column('scope_value', sa.String(length=200), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('role_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_role_assignments_principal'), ['principal'], unique=False)

    op.create_table('saved_views',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user', sa.String(length=200), nullable=False),
    sa.Column('page', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('shared', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('saved_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_saved_views_user'), ['user'], unique=False)

    op.create_table('system_profiles',
    sa.Column('system_id', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=True),
    sa.Column('criticality', sa.String(length=20), nullable=True),
    sa.Column('technology', sa.String(length=200), nullable=True),
    sa.Column('owner', sa.String(length=200), nullable=True),
    sa.Column('domain', sa.String(length=200), nullable=True),
    sa.PrimaryKeyConstraint('system_id')
    )
    op.create_table('variable_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variable_id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=True),
    sa.Column('instance_id', sa.Integer(), nullable=True),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user', sa.String(length=200), nullable=False),
    sa.Column('is_secret', sa.Boolean(), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('changes', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('variable_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_variable_history_environment_id'), ['environment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_variable_history_variable_id'), ['variable_id'], unique=False)

    op.create_table('webhooks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=1000), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('events', sa.JSON(), nullable=False),
    sa.Column('secret', sa.String(length=200), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('last_status', sa.String(length=200), nullable=True),
    sa.Column('last_delivery_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('approval_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_by', sa.String(length=200), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('project', sa.String(length=200), nullable=False),
    sa.Column('team', sa.String(length=200), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.String(length=20), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=False),
    sa.Column('approver', sa.String(length=200), nullable=True),
    sa.Column('decided_by', sa.String(length=200), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('series_id', sa.String(length=40), nullable=True),
    sa.Column('escalated', sa.Boolean(), nullable=False),
    sa.Column('expiry_notified', sa.Boolean(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index('ix_booking_env_range', ['environment_id', 'start_at', 'end_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_project'), ['project'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_series_id'), ['series_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_team'), ['team'], unique=False)

    op.create_table('calendar_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('enforce', sa.Boolean(), nullable=False),
    sa.Column('external_ref', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_events_environment_id'), ['environment_id'], unique=False)

    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user', sa.String(length=200), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=True),
    sa.Column('events', sa.JSON(), nullable=False),
    sa.Column('channel', sa.String(length=20), nullable=False),
    sa.Column('email', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_user'), ['user'], unique=False)

    op.create_table('system_instances',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('system_id', sa.String(length=64), nullable=False),
    sa.Column('instance_name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('deployed_version', sa.String(length=100), nullable=True),
    sa.Column('build', sa.String(length=100), nullable=True),
    sa.Column('commit_sha', sa.String(length=100), nullable=True),
    sa.Column('release', sa.String(length=100), nullable=True),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('virtualisation_ref', sa.String(length=300), nullable=True),
    sa.Column('last_verified', sa.Date(), nullable=True),
    sa.Column('verified_by', sa.String(length=200), nullable=True),
    sa.Column('health_status', sa.String(length=20), nullable=False),
    sa.Column('health_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('health_check_url', sa.String(length=500), nullable=True),
    sa.Column('health_override_status', sa.String(length=20), nullable=True),
    sa.Column('health_override_reason', sa.Text(), nullable=True),
    sa.Column('health_override_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('system_instances', schema=None) as batch_op:
        batch_op.create_index('ix_instance_env_system', ['environment_id', 'system_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_instances_environment_id'), ['environment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_instances_system_id'), ['system_id'], unique=False)

    op.create_table('booking_instances',
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instance_id'], ['system_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('booking_id', 'instance_id')
    )
    op.create_table('deployments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('system_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.String(length=100), nullable=False),
    sa.Column('build', sa.String(length=100), nullable=True),
    sa.Column('commit_sha', sa.String(length=100), nullable=True),
    sa.Column('release', sa.String(length=100), nullable=True),
    sa.Column('deployed_by', sa.String(length=200), nullable=False),
    sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pipeline', sa.String(length=200), nullable=True),
    sa.Column('pipeline_run_url', sa.String(length=500), nullable=True),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('rollback_of_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('tool', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instance_id'], ['system_instances.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rollback_of_id'], ['deployments.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.create_index('ix_deploy_env_at', ['environment_id', 'deployed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_instance_id'), ['instance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_system_id'), ['system_id'], unique=False)

    op.create_table('environment_integrations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('integration_id', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('from_instance_id', sa.Integer(), nullable=True),
    sa.Column('to_instance_id', sa.Integer(), nullable=True),
    sa.Column('protocol', sa.String(length=16), nullable=True),
    sa.Column('pattern', sa.String(length=16), nullable=True),
    sa.Column('direction', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('endpoint', sa.String(length=500), nullable=True),
    sa.Column('last_verified', sa.Date(), nullable=True),
    sa.Column('verified_by', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['from_instance_id'], ['system_instances.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['to_instance_id'], ['system_instances.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('environment_integrations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_environment_integrations_environment_id'), ['environment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_environment_integrations_integration_id'), ['integration_id'], unique=False)

    op.create_table('health_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('response_ms', sa.Float(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instance_id'], ['system_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('health_results', schema=None) as batch_op:
        batch_op.create_index('ix_health_env_at', ['environment_id', 'checked_at'], unique=False)

    op.create_table('instance_shares',
    sa.Column('instance_id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instance_id'], ['system_instances.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('instance_id', 'environment_id')
    )
    op.create_table('issues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('instance_id', sa.Integer(), nullable=True),
    sa.Column('booking_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('known_issue', sa.Boolean(), nullable=False),
    sa.Column('workaround', sa.Text(), nullable=True),
    sa.Column('external_system', sa.String(length=30), nullable=True),
    sa.Column('external_ref', sa.String(length=100), nullable=True),
    sa.Column('external_url', sa.String(length=500), nullable=True),
    sa.Column('hours_lost', sa.Float(), nullable=True),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sla_due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sla_notified', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['instance_id'], ['system_instances.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_issues_environment_id'), ['environment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_issues_external_ref'), ['external_ref'], unique=False)
        batch_op.create_index(batch_op.f('ix_issues_status'), ['status'], unique=False)

    op.create_table('test_data_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('source_environment_id', sa.Integer(), nullable=True),
    sa.Column('system_id', sa.String(length=64), nullable=True),
    sa.Column('volume', sa.String(length=100), nullable=True),
    sa.Column('refresh_date', sa.Date(), nullable=True),
    sa.Column('masking_status', sa.String(length=20), nullable=False),
    sa.Column('production_derived', sa.Boolean(), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=True),
    sa.Column('reserved_for_booking_id', sa.Integer(), nullable=True),
    sa.Column('reserved_by', sa.String(length=200), nullable=True),
    sa.Column('reserved_until', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reserved_for_booking_id'], ['bookings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_environment_id'], ['environments.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('test_data_sets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_test_data_sets_environment_id'), ['environment_id'], unique=False)

    op.create_table('data_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['test_data_sets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('data_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_data_jobs_dataset_id'), ['dataset_id'], unique=False)

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prev_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('hash', sa.String(length=64), nullable=True))

    with op.batch_alter_table('environments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('env_type', sa.String(length=20), nullable=False, server_default='DEV'))
        batch_op.add_column(sa.Column('tier', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('purpose', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('owner', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('delivery_manager', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('technical_contact', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('cost_centre', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('programme', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('support_group', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=30), nullable=False, server_default='Available'))
        batch_op.add_column(sa.Column('platform', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('hosting_location', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('region', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('network_zone', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('urls', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('family', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('shared_infrastructure', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('tags', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('attributes', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('run_cost', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('chargeback_model', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('licence_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('requested_by', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('sla_due_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('retirement_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('decommission_checklist', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_by', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('health_status', sa.String(length=20), nullable=False, server_default='Unknown'))
        batch_op.add_column(sa.Column('health_checked_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('health_check_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('health_override_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('health_override_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('health_override_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('sensitive_data', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('production_derived_data', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('data_controls', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('cmdb_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('updated_by', sa.String(length=200), nullable=True))
        batch_op.create_index(batch_op.f('ix_environments_cmdb_id'), ['cmdb_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_environments_env_type'), ['env_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_environments_programme'), ['programme'], unique=False)
        batch_op.create_index(batch_op.f('ix_environments_region'), ['region'], unique=False)
        batch_op.create_index(batch_op.f('ix_environments_status'), ['status'], unique=False)
        batch_op.create_foreign_key('fk_environments_parent_id', 'environments', ['parent_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('variables', schema=None) as batch_op:
        batch_op.add_column(sa.Column('instance_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('owner', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('value_type', sa.String(length=20), nullable=False, server_default='string'))
        batch_op.add_column(sa.Column('sensitivity', sa.String(length=20), nullable=False, server_default='internal'))
        batch_op.add_column(sa.Column('vault_ref', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('last_rotated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('rotation_due_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('rotation_owner', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('row_version', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('updated_by', sa.String(length=200), nullable=True))
        batch_op.alter_column('environment_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.drop_constraint('uq_env_key', type_='unique')
        batch_op.create_index('ix_variable_scope_key', ['environment_id', 'instance_id', 'key'], unique=False)
        batch_op.create_foreign_key('fk_variables_instance_id', 'system_instances', ['instance_id'], ['id'], ondelete='CASCADE')



def downgrade() -> None:
    with op.batch_alter_table('variables', schema=None) as batch_op:
        batch_op.drop_constraint('fk_variables_instance_id', type_='foreignkey')
        batch_op.drop_index('ix_variable_scope_key')
        batch_op.create_unique_constraint('uq_env_key', ['environment_id', 'key'])
        batch_op.alter_column('environment_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_column('updated_by')
        batch_op.drop_column('row_version')
        batch_op.drop_column('rotation_owner')
        batch_op.drop_column('rotation_due_at')
        batch_op.drop_column('last_rotated_at')
        batch_op.drop_column('vault_ref')
        batch_op.drop_column('sensitivity')
        batch_op.drop_column('value_type')
        batch_op.drop_column('owner')
        batch_op.drop_column('description')
        batch_op.drop_column('instance_id')

    with op.batch_alter_table('environments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_environments_parent_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_environments_status'))
        batch_op.drop_index(batch_op.f('ix_environments_region'))
        batch_op.drop_index(batch_op.f('ix_environments_programme'))
        batch_op.drop_index(batch_op.f('ix_environments_env_type'))
        batch_op.drop_index(batch_op.f('ix_environments_cmdb_id'))
        batch_op.drop_column('updated_by')
        batch_op.drop_column('row_version')
        batch_op.drop_column('cmdb_id')
        batch_op.drop_column('data_controls')
        batch_op.drop_column('production_derived_data')
        batch_op.drop_column('sensitive_data')
        batch_op.drop_column('health_override_until')
        batch_op.drop_column('health_override_reason')
        batch_op.drop_column('health_override_status')
        batch_op.drop_column('health_check_url')
        batch_op.drop_column('health_checked_at')
        batch_op.drop_column('health_status')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('decommission_checklist')
        batch_op.drop_column('retirement_date')
        batch_op.drop_column('sla_due_at')
        batch_op.drop_column('requested_at')
        batch_op.drop_column('requested_by')
        batch_op.drop_column('licence_notes')
        batch_op.drop_column('chargeback_model')
        batch_op.drop_column('run_cost')
        batch_op.drop_column('attributes')
        batch_op.drop_column('tags')
        batch_op.drop_column('shared_infrastructure')
        batch_op.drop_column('family')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('urls')
        batch_op.drop_column('network_zone')
        batch_op.drop_column('region')
        batch_op.drop_column('hosting_location')
        batch_op.drop_column('platform')
        batch_op.drop_column('status')
        batch_op.drop_column('support_group')
        batch_op.drop_column('programme')
        batch_op.drop_column('cost_centre')
        batch_op.drop_column('technical_contact')
        batch_op.drop_column('delivery_manager')
        batch_op.drop_column('owner')
        batch_op.drop_column('purpose')
        batch_op.drop_column('tier')
        batch_op.drop_column('env_type')

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_column('hash')
        batch_op.drop_column('prev_hash')

    with op.batch_alter_table('data_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_data_jobs_dataset_id'))

    op.drop_table('data_jobs')
    with op.batch_alter_table('test_data_sets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_test_data_sets_environment_id'))

    op.drop_table('test_data_sets')
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_issues_status'))
        batch_op.drop_index(batch_op.f('ix_issues_external_ref'))
        batch_op.drop_index(batch_op.f('ix_issues_environment_id'))

    op.drop_table('issues')
    op.drop_table('instance_shares')
    with op.batch_alter_table('health_results', schema=None) as batch_op:
        batch_op.drop_index('ix_health_env_at')

    op.drop_table('health_results')
    with op.batch_alter_table('environment_integrations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_environment_integrations_integration_id'))
        batch_op.drop_index(batch_op.f('ix_environment_integrations_environment_id'))

    op.drop_table('environment_integrations')
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deployments_system_id'))
        batch_op.drop_index(batch_op.f('ix_deployments_instance_id'))
        batch_op.drop_index('ix_deploy_env_at')

    op.drop_table('deployments')
    op.drop_table('booking_instances')
    with op.batch_alter_table('system_instances', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_instances_system_id'))
        batch_op.drop_index(batch_op.f('ix_system_instances_environment_id'))
        batch_op.drop_index('ix_instance_env_system')

    op.drop_table('system_instances')
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_user'))

    op.drop_table('subscriptions')
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_events_environment_id'))

    op.drop_table('calendar_events')
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_team'))
        batch_op.drop_index(batch_op.f('ix_bookings_status'))
        batch_op.drop_index(batch_op.f('ix_bookings_series_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_project'))
        batch_op.drop_index('ix_booking_env_range')

    op.drop_table('bookings')
    op.drop_table('approval_requests')
    op.drop_table('webhooks')
    with op.batch_alter_table('variable_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_variable_history_variable_id'))
        batch_op.drop_index(batch_op.f('ix_variable_history_environment_id'))

    op.drop_table('variable_history')
    op.drop_table('system_profiles')
    with op.batch_alter_table('saved_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_views_user'))

    op.drop_table('saved_views')
    with op.batch_alter_table('role_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_role_assignments_principal'))

    op.drop_table('role_assignments')
    op.drop_table('promotion_paths')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_user_read')

    op.drop_table('notifications')
    with op.batch_alter_table('config_template_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_config_template_keys_env_type'))

    op.drop_table('config_template_keys')
    op.drop_table('bulk_operations')
    op.drop_table('app_settings')
    op.drop_table('api_tokens')
