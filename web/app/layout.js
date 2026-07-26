import "./globals.css";
import SwRegister from "./sw-register";

export const metadata = {
  title: "냉장고 알리미",
  description: "TDD 기반 MVP 프론트엔드",
  manifest: "/manifest.webmanifest",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>
        <SwRegister />
        {children}
      </body>
    </html>
  );
}
