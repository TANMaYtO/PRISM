import type { Metadata } from "next";
import { Space_Mono, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space-mono",
});

const geistSans = Geist({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-geist",
});

const geistMono = Geist_Mono({
  weight: ["400"],
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "PRISM - Code Review",
  description: "Autonomous pull-request intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${spaceMono.variable} ${geistSans.variable} ${geistMono.variable}`}>
      <body className="antialiased font-body bg-void text-primary">
        {children}
      </body>
    </html>
  );
}
