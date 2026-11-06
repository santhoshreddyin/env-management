import { expect, test } from '@playwright/test';

test('trace a flow with the dropdowns', async ({ page }) => {
  await page.goto('/flows');
  await page.getByLabel('Upstream system').click();
  await page.getByRole('option', { name: /Broker Portal/ }).click();
  await page.getByLabel('Downstream system').click();
  // FR-1: only valid downstream options for Broker Portal
  await expect(page.getByRole('option')).toHaveCount(1);
  await page.getByRole('option', { name: /Polisy/ }).click();

  // FR-4: two integrations for this pair, the first is selected
  const list = page.getByRole('list', { name: 'Matching integrations' });
  await expect(list.getByRole('button')).toHaveCount(2);
  await expect(page).toHaveURL(/from=Broker\+Portal&to=Polisy&integration=INT-001/);

  // FR-5: numbered, labelled hops on the diagram
  await expect(page.locator('.path-edge-label', { hasText: '3 · SOAP' })).toBeVisible();
  await expect(page.getByRole('list', { name: 'Hops in sequence' }).getByRole('button')).toHaveCount(8);

  // Switch integration, then request-only view (FR-6)
  await list.getByRole('button', { name: /Broker renewal submission/ }).click();
  await expect(page.getByTestId('narrative')).toContainText('POLICY.RENEWAL.REQ');
  await page.getByRole('button', { name: 'Request', exact: true }).click();
  await expect(page.getByRole('list', { name: 'Hops in sequence' }).getByRole('button')).toHaveCount(4);
  await expect(page.locator('.path-edge-label', { hasText: 'reply' })).toHaveCount(0);

  // FR-7: click a hop to see queue details
  await page.locator('.path-edge-label', { hasText: '3 · MQ' }).click();
  await expect(page.getByTestId('detail-panel')).toContainText('QM_HUB01');
});

test('deep link with journey filter', async ({ page }) => {
  await page.goto('/flows?from=Polisy&to=Billing&journey=renewal');
  await expect(page.getByRole('list', { name: 'Matching integrations' }).getByRole('button')).toHaveCount(1);
  await expect(page.getByTestId('narrative')).toContainText('Polisy transfers a file to MFT Server by MFT');
  await expect(page.getByRole('heading', { name: 'Policy premium to billing' })).toBeVisible();
});

test('free exploration of a system', async ({ page }) => {
  await page.goto('/flows');
  await page.locator('.react-flow__node-system', { hasText: 'MQ Hub' }).click();
  const detail = page.getByTestId('detail-panel');
  await expect(detail).toContainText('Intermediary in (4)');
  await expect(page).toHaveURL(/system=MQ\+Hub/);
  await detail.getByRole('button', { name: 'Claims payment' }).click();
  await expect(page).toHaveURL(/integration=INT-008/);
});

test('export the view as PNG', async ({ page }) => {
  await page.goto('/flows?from=Customer%20Web&to=Billing');
  await expect(page.locator('.path-edge-label').first()).toBeVisible();
  await page.getByRole('button', { name: 'Export' }).click();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: 'PNG image' }).click()]);
  expect(download.suggestedFilename()).toBe('flow-INT-004.png');
});
