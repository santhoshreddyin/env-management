import type { Meta } from '../api/platform';
import type { Field } from './common';

/** Environment form fields (ENV-01/02/04/05/12, TDM-05, INT-02). */
export function environmentFields(meta: Meta | undefined, parents: { id: number; name: string }[] = []): Field[] {
  return [
    { key: 'name', label: 'Name', required: true },
    { key: 'env_type', label: 'Type', type: 'select', options: meta?.env_types ?? [], required: true },
    { key: 'description', label: 'Description', type: 'multiline' },
    { key: 'tier', label: 'Tier', type: 'select', options: meta?.tiers ?? [] },
    { key: 'purpose', label: 'Purpose' },
    { key: 'owner', label: 'Owner' },
    { key: 'delivery_manager', label: 'Delivery manager' },
    { key: 'technical_contact', label: 'Technical contact' },
    { key: 'support_group', label: 'Support group' },
    { key: 'programme', label: 'Programme / portfolio' },
    { key: 'cost_centre', label: 'Cost centre' },
    { key: 'platform', label: 'Platform', type: 'select', options: meta?.platforms ?? [] },
    { key: 'hosting_location', label: 'Cloud account / data centre' },
    { key: 'region', label: 'Region' },
    { key: 'network_zone', label: 'Network zone' },
    { key: 'parent_id', label: 'Parent environment', type: 'select', options: parents.map((p) => ({ value: p.id, label: p.name })) },
    { key: 'family', label: 'Environment family' },
    { key: 'tags', label: 'Tags (comma-separated)', type: 'tags' },
    { key: 'health_check_url', label: 'Health check URL', help: 'http(s)://… or tcp://host:port' },
    { key: 'run_cost', label: 'Run cost per month', type: 'number' },
    { key: 'chargeback_model', label: 'Chargeback model', type: 'select', options: ['fixed', 'per-booking', 'usage', 'none'] },
    { key: 'cmdb_id', label: 'CMDB id' },
    { key: 'licence_notes', label: 'Licence constraints', type: 'multiline' },
    { key: 'data_controls', label: 'Data controls', type: 'multiline' },
    { key: 'shared_infrastructure', label: 'Shared infrastructure', type: 'checkbox' },
    { key: 'sensitive_data', label: 'Holds sensitive data', type: 'checkbox' },
    { key: 'production_derived_data', label: 'Holds production-derived data', type: 'checkbox' },
  ];
}
