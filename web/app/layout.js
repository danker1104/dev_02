import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import SwRegister from "./sw-register";

const displayFont = Space_Grotesk({ subsets: ["latin"] });
const monoFont = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"] });

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
      <body className={`${displayFont.className} ${monoFont.variable}`}>
        <SwRegister />
        {children}
      </body>
    </html>
  );
}
