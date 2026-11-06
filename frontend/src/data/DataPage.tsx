import DownloadIcon from '@mui/icons-material/Download';
import { Alert, Box, Button, Paper, Stack, Tab, Tabs, Typography } from '@mui/material';
import { useState } from 'react';
import { flowsApi } from '../api/flows';
import { useFlowConfig, useMe } from '../flows/queries';
import AuditLog from './AuditLog';
import ImportPanel from './ImportPanel';
import IntegrationsEditor from './IntegrationsEditor';
import SystemsEditor from './SystemsEditor';
import VersionHistory from './VersionHistory';

export default function DataPage() {
  const me = useMe();
  const config = useFlowConfig();
  const isMaintainer = me.data?.roles.includes('maintainer') ?? false;
  const tabs = isMaintainer ? ['import', 'history', 'systems', 'integrations', 'audit'] : ['history'];
  const [tab, setTab] = useState('import');
  const current = tabs.includes(tab) ? tab : tabs[0];

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ md: 'center' }}>
          <Box>
            <Typography variant="h6" component="h1">
              Integration data
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Metadata only: never store credentials or payload data here.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button startIcon={<DownloadIcon />} href={flowsApi.exportUrl('xlsx')}>
              Excel
            </Button>
            <Button startIcon={<DownloadIcon />} href={flowsApi.exportUrl('json')}>
              JSON
            </Button>
            <Button startIcon={<DownloadIcon />} href={flowsApi.templateUrl()}>
              Empty template
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {!isMaintainer && me.isSuccess && (
        <Alert severity="info">You have view access. Importing and editing require the maintainer role.</Alert>
      )}

      <Paper variant="outlined">
        <Tabs value={current} onChange={(_, v) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider', px: 1 }}>
          {tabs.includes('import') && <Tab value="import" label="Import" />}
          <Tab value="history" label="Version history" />
          {tabs.includes('systems') && <Tab value="systems" label="Systems" />}
          {tabs.includes('integrations') && <Tab value="integrations" label="Integrations" />}
          {tabs.includes('audit') && <Tab value="audit" label="Audit log" />}
        </Tabs>
        <Box sx={{ p: 2, overflowX: 'auto' }}>
          {current === 'import' && <ImportPanel />}
          {current === 'history' && <VersionHistory canEdit={isMaintainer} />}
          {current === 'systems' && config.data && <SystemsEditor config={config.data} />}
          {current === 'integrations' && config.data && <IntegrationsEditor config={config.data} />}
          {current === 'audit' && <AuditLog />}
        </Box>
      </Paper>
    </Stack>
  );
}
