import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Script from "next/script";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FiForesight",
  description: "AI-Based Financial Forecasting",
};

const nrScript = process.env.NEXT_PUBLIC_APP_ENV === 'live'
  ? '/newrelic.live.js'
  : '/newrelic.preview.js'

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
    return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        {children}
        <Script id="newrelic" strategy="afterInteractive" src={nrScript} />
      </body>
    </html>
  );
}