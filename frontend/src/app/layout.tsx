import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Football-IQ | Toledo Football Analytics",
  description:
    "Toledo Football computer vision platform — practice film intelligence, player tracking, and coaching analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
