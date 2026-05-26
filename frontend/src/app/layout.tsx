import type { Metadata } from "next";
import "./globals.css";
import { AppStateProvider } from "@/lib/app-state";

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
      <body>
        <AppStateProvider>{children}</AppStateProvider>
      </body>
    </html>
  );
}
