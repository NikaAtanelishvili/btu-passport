import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Outfit } from "next/font/google";

import { SiteFooter, SiteHeader } from "@/components/site-header";

import "./globals.css";
import { Providers } from "./providers";

// Outfit for headings (900 paired with 200), Inter for body, JetBrains Mono for IDs and codes.
const outfit = Outfit({ variable: "--font-outfit", subsets: ["latin"] });
const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "BTU AI Skills Passport",
  description: "Issue and verify BTU AI Skills Digital Passports",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${outfit.variable} ${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>
          <SiteHeader />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 has-[[data-admin-shell]]:max-w-7xl sm:px-6 sm:py-12">{children}</main>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
