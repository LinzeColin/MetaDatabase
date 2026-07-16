import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  applicationName: "EEI 商域图谱",
  title: "商域图谱 | Enterprise Ecosystem Intelligence",
  description: "企业商业版图与供应链递归探索系统",
  icons: {
    icon: [
      { url: "/eei-app-icon.svg", type: "image/svg+xml" },
      { url: "/eei-app-icon.png", sizes: "1024x1024", type: "image/png" }
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }]
  },
  appleWebApp: {
    title: "EEI 商域图谱",
    capable: true,
    statusBarStyle: "black-translucent"
  }
};

// HEAD_INIT anti-flicker contract (S9PAT01): the theme attribute is stamped
// on <html> synchronously before first paint, so a stored preference can
// never flash the wrong theme. Falls back to deep-space (the empire default).
const THEME_HEAD_INIT = `(function () {
  try {
    var stored = window.localStorage.getItem("eei.theme.v1");
    var theme = stored === "daylight" || stored === "deep-space" ? stored : "deep-space";
    document.documentElement.setAttribute("data-theme", theme);
  } catch (error) {
    document.documentElement.setAttribute("data-theme", "deep-space");
  }
})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-theme="deep-space" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_HEAD_INIT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
