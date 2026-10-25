import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TVL YouTube Extractor",
  description:
    "Turn any YouTube video into a story-timeline summary with frames, clips, and a bilingual transcript.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
