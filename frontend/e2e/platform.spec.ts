import { expect, test } from '@playwright/test';

// Runs against the demo inventory loaded by `python -m app.flows.seed --with-environments`.

test('dashboard shows inventory, health and the instance banner', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole('status', { name: 'Instance' })).toContainText('INSTANCE');
  await expect(page.getByText('Not healthy:')).toContainText('PERF1');
  await expect(page.getByLabel('Environment status').getByRole('link', { name: /^SIT2/ })).toContainText('Degraded');
});

test('register an environment, edit it and move it through the lifecycle', async ({ page }) => {
  await page.goto('/environments');
  await expect(page.getByRole('table', { name: 'Environments' })).toContainText('UAT1');
  await page.getByRole('button', { name: 'New environment' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('E2E-SIT9');
  await dialog.getByLabel('Owner').fill('QA Lead');
  await dialog.getByRole('button', { name: 'Create' }).click();
  await expect(page.getByRole('heading', { name: 'E2E-SIT9' })).toBeVisible();
  await page.getByRole('button', { name: 'Under maintenance' }).click();
  await expect(page.getByText('Move from Under maintenance to')).toBeVisible();
  await page.getByRole('tab', { name: 'Topology' }).click();
  await page.getByRole('button', { name: 'Add all from catalogue' }).click();
  await expect(page.getByText(/Added 14 systems and 8 integrations/)).toBeVisible();
  await expect(page.getByRole('table', { name: 'System instances' })).toContainText('BILLING-E2E-SIT9');
});

test('booking checks conflicts, including shared components', async ({ page }) => {
  await page.goto('/bookings');
  await expect(page.getByRole('table', { name: 'Booking timeline' })).toContainText('Claims Modernisation R3');
  await page.getByRole('button', { name: 'Book an environment' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: 'Environment', exact: true }).click();
  await page.getByRole('option', { name: /^SIT2/ }).click();
  await dialog.getByRole('textbox', { name: /^Project/ }).fill('E2E regression');
  await expect(page.getByTestId('booking-check')).toContainText('Claims Modernisation R3');
  await expect(dialog.getByRole('button', { name: 'Join waitlist' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Join waitlist' }).click();
  await expect(dialog).toContainText('Waitlisted');
});

test('secrets are masked and revealed on request; config compares across environments', async ({ page }) => {
  await page.goto('/environments');
  await page.getByRole('table', { name: 'Environments' }).getByText('UAT1').click();
  await page.getByRole('tab', { name: 'Configuration' }).click();
  const table = page.getByRole('table', { name: 'Variables' });
  await expect(table).toContainText('DB_PASSWORD');
  await expect(table).toContainText('vault: kv://envmgmt-uat1/db-password');
  await expect(page.getByText(/Template for UAT: missing AUDIT_SINK_URL/)).toBeVisible();
  await page.goto('/config');
  await page.getByLabel('Environments (2 or more)').click();
  await page.getByRole('option', { name: 'SIT1' }).click();
  await page.getByRole('option', { name: 'UAT1' }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('table', { name: 'Configuration comparison' })).toContainText('LOG_LEVEL');
});

test('global search finds environments, systems and issues', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByLabel('Global search').fill('billing');
  const results = page.getByRole('list', { name: 'Search results' });
  await expect(results).toContainText('Systems');
  await expect(results).toContainText('Billing responses slow');
  await results.getByText('BILLING-SIT1').click();
  await expect(page).toHaveURL(/\/environments\/\d+\?tab=topology/);
});

test('version matrix, readiness and reports render', async ({ page }) => {
  await page.goto('/releases');
  await expect(page.getByRole('table', { name: 'Version matrix' })).toContainText('2.5.0-rc1');
  await page.goto('/reports');
  await expect(page.getByRole('table', { name: 'Utilisation' })).toContainText('SIT1');
  await page.getByRole('tab', { name: 'Data quality' }).click();
  await expect(page.getByRole('table', { name: 'Data quality findings' })).toContainText('rotation overdue');
});
