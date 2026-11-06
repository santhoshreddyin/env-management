import AccountTreeIcon from '@mui/icons-material/AccountTree';
import NotificationsIcon from '@mui/icons-material/NotificationsNone';
import SearchIcon from '@mui/icons-material/Search';
import { AppBar, Badge, Box, Chip, IconButton, InputAdornment, List, ListItemButton, ListItemText, ListSubheader, Paper, Popper, Tab, Tabs, TextField, Toolbar, Tooltip, Typography, ClickAwayListener } from '@mui/material';
import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { useAccess, useGet, type Row } from './api/platform';
import DataPage from './data/DataPage';
import FlowExplorerPage from './flows/FlowExplorerPage';
import AdminPage from './platform/AdminPage';
import BookingsPage from './platform/BookingsPage';
import CalendarPage from './platform/CalendarPage';
import CataloguePage from './platform/CataloguePage';
import ConfigPage from './platform/ConfigPage';
import DashboardPage from './platform/DashboardPage';
import EnvironmentDetailPage from './platform/EnvironmentDetailPage';
import EnvironmentsListPage from './platform/EnvironmentsListPage';
import IssuesPage from './platform/IssuesPage';
import ReleasesPage from './platform/ReleasesPage';
import ReportsPage from './platform/ReportsPage';

const NAV = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/environments', label: 'Environments' },
  { path: '/bookings', label: 'Bookings' },
  { path: '/calendar', label: 'Calendar' },
  { path: '/releases', label: 'Releases' },
  { path: '/issues', label: 'Issues' },
  { path: '/config', label: 'Config' },
  { path: '/reports', label: 'Reports' },
  { path: '/flows', label: 'Flow Explorer' },
  { path: '/catalogue', label: 'Catalogue' },
  { path: '/data', label: 'Data' },
  { path: '/admin', label: 'Admin' },
];

const GROUP_LABEL: Record<string, string> = {
  environments: 'Environments', systems: 'Systems', instances: 'System instances', integrations: 'Integrations',
  variables: 'Variables', bookings: 'Bookings', issues: 'Issues', test_data: 'Test data',
};

/** GOV-09: which instance (QA, UAT, Prod) the user is working in. */
function InstanceBanner() {
  const health = useGet<{ environment: string }>('/health');
  const env = (health.data?.environment ?? '').toLowerCase();
  if (!env) return null;
  const prod = env === 'production' || env === 'prod';
  const colour = prod ? '#b91c1c' : env === 'qa' ? '#7c3aed' : env === 'local' ? '#334155' : '#0369a1';
  return (
    <Box role="status" aria-label="Instance" sx={{ bgcolor: colour, color: '#fff', textAlign: 'center', fontSize: 12, py: 0.25, fontWeight: 600, letterSpacing: 0.5 }}>
      {prod ? 'PRODUCTION INSTANCE' : `${env.toUpperCase()} INSTANCE — not production`}
    </Box>
  );
}

function GlobalSearch() {
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);
  const res = useGet<{ results: Record<string, Row[]>; total: number }>(debounced.length >= 2 ? '/search' : null, { q: debounced });
  const groups = Object.entries(res.data?.results ?? {}).filter(([, v]) => v.length);
  return (
    <ClickAwayListener onClickAway={() => setAnchor(null)}>
      <Box>
        <TextField
          size="small"
          placeholder="Search everything"
          value={q}
          onChange={(e) => { setQ(e.target.value); setAnchor(e.currentTarget); }}
          onFocus={(e) => setAnchor(e.currentTarget)}
          inputProps={{ 'aria-label': 'Global search' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
          sx={{ width: { xs: 160, md: 240 } }}
        />
        <Popper open={!!anchor && debounced.length >= 2} anchorEl={anchor} placement="bottom-end" sx={{ zIndex: 1300 }}>
          <Paper elevation={6} sx={{ width: 420, maxHeight: 480, overflow: 'auto' }}>
            <List dense aria-label="Search results">
              {groups.map(([g, items]) => (
                <li key={g}>
                  <ul style={{ padding: 0 }}>
                    <ListSubheader>{GROUP_LABEL[g] ?? g}</ListSubheader>
                    {items.map((i) => (
                      <ListItemButton key={`${g}-${i.id}`} onClick={() => { setAnchor(null); setQ(''); nav(i.link); }}>
                        <ListItemText primary={i.label} secondary={i.detail} />
                      </ListItemButton>
                    ))}
                  </ul>
                </li>
              ))}
              {res.data && res.data.total === 0 && <ListItemText sx={{ px: 2 }} primary="No matches" />}
            </List>
          </Paper>
        </Popper>
      </Box>
    </ClickAwayListener>
  );
}

export default function App() {
  const location = useLocation();
  const me = useAccess();
  const nav = useNavigate();
  const current = NAV.find((n) => location.pathname.startsWith(n.path))?.path ?? false;

  return (
    <Box sx={{ minHeight: '100vh' }}>
      <InstanceBanner />
      <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
        <Toolbar variant="dense" sx={{ gap: 2 }}>
          <AccountTreeIcon color="primary" />
          <Typography variant="h6" component="div" sx={{ fontSize: 18, whiteSpace: 'nowrap', display: { xs: 'none', sm: 'block' } }}>
            Env Management
          </Typography>
          <Tabs value={current} variant="scrollable" scrollButtons="auto" sx={{ flex: 1, minHeight: 48 }} aria-label="Main navigation">
            {NAV.map((n) => (
              <Tab key={n.path} value={n.path} label={n.label} component={Link} to={n.path} sx={{ minHeight: 48, px: 1.5, minWidth: 0 }} />
            ))}
          </Tabs>
          <GlobalSearch />
          <Tooltip title="Notifications">
            <IconButton aria-label="Notifications" onClick={() => nav('/admin?tab=notifications')}>
              <Badge color="error" badgeContent={me.data?.unread_notifications ?? 0}>
                <NotificationsIcon />
              </Badge>
            </IconButton>
          </Tooltip>
          {me.data && <Chip size="small" variant="outlined" label={`${me.data.name} · ${me.data.role.replace('_', ' ')}`} />}
        </Toolbar>
      </AppBar>
      <Box component="main" sx={{ p: 1.5 }}>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/environments" element={<EnvironmentsListPage />} />
          <Route path="/environments/:id" element={<EnvironmentDetailPage />} />
          <Route path="/bookings" element={<BookingsPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/releases" element={<ReleasesPage />} />
          <Route path="/issues" element={<IssuesPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/catalogue" element={<CataloguePage />} />
          <Route path="/flows" element={<FlowExplorerPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Box>
    </Box>
  );
}
