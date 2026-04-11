import path from "node:path";
import { test, expect } from "@playwright/test";

const FIXTURE_PATH = path.join(
  process.cwd(),
  "tests",
  "fixtures",
  "mission-note.md"
);

test("workspace loads and can create a new session", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByText("Local chat, files, and grounded answers")
  ).toBeVisible();

  await page.getByTestId("new-session-button").click();

  await expect(page).toHaveURL(/session=/);
  await expect(page.getByTestId("chat-composer")).toBeVisible();
});

test("model settings, file upload, streaming answer, and sources sidebar work", async ({
  page,
}) => {
  await page.goto("/settings");

  await expect(
    page.getByText("Local model configuration")
  ).toBeVisible();
  await page.getByTestId("settings-model-select").selectOption("mock-chat:latest");
  await page.getByTestId("settings-save-button").click();
  await expect(page.getByText(/Connected\./)).toBeVisible();

  await page.goto("/");
  await page.getByTestId("new-session-button").click();
  await expect(page).toHaveURL(/session=/);

  await page.getByTestId("composer-model-select").selectOption("mock-chat:latest");
  const uploadResponsePromise = page.waitForResponse((response) =>
    response.url().includes("/api/files/upload")
  );
  await page.getByTestId("composer-file-input").setInputFiles(FIXTURE_PATH);
  const uploadResponse = await uploadResponsePromise;
  expect(uploadResponse.ok()).toBeTruthy();
  await expect(page.getByText("Mission Note")).toBeVisible();

  await page
    .getByTestId("chat-composer")
    .fill("When does the launch window open? Use my uploaded note.");
  await page.getByTestId("composer-submit").click();

  await expect(page.getByText("Internal Search")).toBeVisible();
  await expect(
    page.getByText("I found the answer in your local files.")
  ).toBeVisible();

  await page.getByTestId("sources-button").click();
  await expect(page.getByTestId("source-sidebar")).toBeVisible();
  await expect(page.getByText("Cited First")).toBeVisible();
  await expect(
    page
      .getByTestId("source-sidebar")
      .getByRole("heading", { name: "Mission Note" })
  ).toBeVisible();
});
