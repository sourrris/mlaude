import { Page, Locator, expect } from "@playwright/test";

export class SettingsPage {
  readonly page: Page;
  readonly modelSelect: Locator;
  readonly saveButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.modelSelect = page.getByTestId("settings-model-select");
    this.saveButton = page.getByTestId("settings-save-button");
  }

  async selectModel(modelName: string) {
    await this.modelSelect.selectOption(modelName);
  }

  async saveSettings() {
    await this.saveButton.click();
    await expect(this.page.getByText(/Connected\./)).toBeVisible();
  }

  async expectConnected() {
    await expect(this.page.getByText(/Connected\./)).toBeVisible();
  }
}
