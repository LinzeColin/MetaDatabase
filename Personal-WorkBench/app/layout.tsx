import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人日程",
  description: "把生活里的小事，温柔地放在一起。",
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
