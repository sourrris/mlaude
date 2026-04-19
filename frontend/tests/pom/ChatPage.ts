import { Page, Locator, expect } from "@playwright/test";

export class ChatPage {
  readonly page: Page;
  readonly chatComposer: Locator;
  readonly composerSubmit: Locator;
  readonly composerFileInput: Locator;
  readonly composerModelSelect: Locator;
  readonly sourcesButton: Locator;
  readonly sourceSidebar: Locator;
  readonly messageList: Locator;
  readonly runsToggle: Locator;
  readonly chatToggle: Locator;
  readonly runsPanel: Locator;

  constructor(page: Page) {
    this.page = page;
    this.chatComposer = page.getByTestId("chat-composer");
    this.composerSubmit = page.getByTestId("composer-submit");
    this.composerFileInput = page.getByTestId("composer-file-input");
    this.composerModelSelect = page.getByTestId("composer-model-select");
    this.sourcesButton = page.getByTestId("sources-button");
    this.sourceSidebar = page.getByTestId("source-sidebar");
    this.messageList = page.getByTestId("message-list");
    this.runsToggle = page.getByTestId("session-view-runs");
    this.chatToggle = page.getByTestId("session-view-chat");
    this.runsPanel = page.getByTestId("runs-panel");
  }

  async sendMessage(message: string) {
    await this.chatComposer.fill(message);
    await this.composerSubmit.click();
  }

  async uploadFile(filePath: string) {
    const uploadResponsePromise = this.page.waitForResponse((response) =>
      response.url().includes("/api/files/upload")
    );
    await this.composerFileInput.setInputFiles(filePath);
    const uploadResponse = await uploadResponsePromise;
    expect(uploadResponse.ok()).toBeTruthy();
  }

  async selectModel(modelName: string) {
    await this.composerModelSelect.selectOption(modelName);
  }

  async openSources() {
    await this.sourcesButton.click();
    await expect(this.sourceSidebar).toBeVisible();
  }

  async openRuns() {
    await this.runsToggle.click();
    await expect(this.runsPanel).toBeVisible();
  }

  async expectMessageVisible(text: string | RegExp) {
    await expect(this.page.getByText(text)).toBeVisible();
  }

  async stopStreaming() {
    await this.composerSubmit.click(); // In streaming mode, this is the stop button
  }

  async expectStreaming() {
    await expect(this.page.getByText("Streaming response…")).toBeVisible();
  }
}
