import type { Metadata } from "next";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Mlaude Workspace",
  description: "A stripped-down local-first AI workspace inspired by Onyx.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
