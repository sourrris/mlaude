import { Page, Locator, expect } from "@playwright/test";

export class SidebarPage {
  readonly page: Page;
  readonly newSessionButton: Locator;
  readonly chatSearchInput: Locator;
  readonly filesLink: Locator;
  readonly settingsLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.newSessionButton = page.getByTestId("new-session-button");
    this.chatSearchInput = page.getByTestId("chat-search-input");
    this.filesLink = page.getByTestId("files-link");
    this.settingsLink = page.getByTestId("settings-link");
  }

  async createNewSession() {
    await this.newSessionButton.click();
    await expect(this.page).toHaveURL(/session=/);
  }

  async goToFiles() {
    await this.filesLink.click();
    await expect(this.page).toHaveURL(/\/files/);
  }

  async goToSettings() {
    await this.settingsLink.click();
    await expect(this.page).toHaveURL(/\/settings/);
  }

  async searchChats(query: string) {
    await this.chatSearchInput.fill(query);
  }

  async selectSession(title: string) {
    await this.page.getByRole("button", { name: title }).click();
  }

  async expectSessionActive(title: string) {
    await expect(
      this.page.getByRole("button", { name: title })
    ).toHaveClass(/bg-white/);
  }
}
