import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://mydairy.linzezhang.com"),
  title: "个人工作台",
  description: "把生活里的小事，温柔地放在一起。",
  applicationName: "个人工作台",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    url: "/",
    siteName: "个人工作台",
    title: "个人工作台",
    description: "把生活里的小事，温柔地放在一起。",
  },
  twitter: {
    card: "summary",
    title: "个人工作台",
    description: "把生活里的小事，温柔地放在一起。",
  },
  icons: {
    icon: "/private-reference-assets/runtime/app-icon-192.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
