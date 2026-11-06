import { expect, test } from '@playwright/test';
import path from 'node:path';

const SAMPLE = path.resolve(import.meta.dirname, '../../backend/sample_data/integration-flows-sample.xlsx');

test('validate a workbook before import', async ({ page }) => {
  await page.goto('/data');
  await page.getByTestId('import-file').setInputFiles(SAMPLE);
  await expect(page.getByText(/Validation passed: 14 systems, 8 integrations, 41 hops/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import' })).toBeEnabled();
});

test('version history and editors are available to maintainers', async ({ page }) => {
  await page.goto('/data');
  await page.getByRole('tab', { name: 'Version history' }).click();
  await expect(page.getByRole('table', { name: 'Version history' })).toContainText('Sample dataset');
  await page.getByRole('tab', { name: 'Integrations' }).click();
  await page.getByRole('button', { name: 'Edit Customer payment' }).click();
  await expect(page.getByRole('dialog')).toContainText('Hops (in order');
});
