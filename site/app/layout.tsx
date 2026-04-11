import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import { ThemeProvider } from '@/components/theme-provider'
import { FooterLinks } from '@/components/footer'
import { SiteNavbar } from '@/components/site-navbar'
import { BlogSearchProvider } from '@/components/blog-search-context'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'MT-AutoOptimize Wiki',
  description: 'MT-AutoOptimize project wiki built with Next.js and Velite.',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(t==='light')return;document.documentElement.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ThemeProvider>
          <BlogSearchProvider>
            <div className="flex min-h-screen flex-col">
              <SiteNavbar />
              <main className="flex-1 pt-2">{children}</main>
              <FooterLinks />
            </div>
          </BlogSearchProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
