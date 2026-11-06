import AccountTreeIcon from '@mui/icons-material/AccountTree';
import { AppBar, Box, Chip, Tab, Tabs, Toolbar, Typography } from '@mui/material';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import DataPage from './data/DataPage';
import EnvironmentsPage from './env/EnvironmentsPage';
import FlowExplorerPage from './flows/FlowExplorerPage';
import { useMe } from './flows/queries';

const NAV = [
  { path: '/flows', label: 'Flow Explorer' },
  { path: '/data', label: 'Data' },
  { path: '/environments', label: 'Environments' },
];

export default function App() {
  const location = useLocation();
  const me = useMe();
  const current = NAV.find((n) => location.pathname.startsWith(n.path))?.path ?? false;

  return (
    <Box sx={{ minHeight: '100vh' }}>
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
        <Toolbar variant="dense" sx={{ gap: 2 }}>
          <AccountTreeIcon color="primary" />
          <Typography variant="h6" component="div" sx={{ fontSize: 18, whiteSpace: 'nowrap' }}>
            Env Management
          </Typography>
          <Tabs value={current} sx={{ flex: 1, minHeight: 48 }} aria-label="Main navigation">
            {NAV.map((n) => (
              <Tab key={n.path} value={n.path} label={n.label} component={Link} to={n.path} sx={{ minHeight: 48 }} />
            ))}
          </Tabs>
          {me.data && (
            <Chip
              size="small"
              variant="outlined"
              label={`${me.data.name} · ${me.data.roles.includes('maintainer') ? 'maintainer' : 'viewer'}`}
            />
          )}
        </Toolbar>
      </AppBar>
      <Box component="main" sx={{ p: 1.5 }}>
        <Routes>
          <Route path="/" element={<Navigate to="/flows" replace />} />
          <Route path="/flows" element={<FlowExplorerPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/environments" element={<EnvironmentsPage />} />
          <Route path="*" element={<Navigate to="/flows" replace />} />
        </Routes>
      </Box>
    </Box>
  );
}
