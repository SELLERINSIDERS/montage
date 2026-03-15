import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Toaster } from 'sonner'
import { NuqsAdapter } from 'nuqs/adapters/next/app'
import { TooltipProvider } from '@/components/ui/tooltip'
import { HeaderWithBadge } from '@/components/layout/header-with-badge'
import { ConnectionBanner } from '@/components/layout/connection-banner'
import { ReviewCountProvider } from '@/lib/review-count-context'
import './globals.css'

const inter = Inter({
  variable: '--font-sans',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'VSL Production Dashboard',
  description: 'Video production pipeline dashboard',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark" style={{ colorScheme: 'dark' }}>
      <body className={`${inter.variable} font-sans antialiased`}>
        <NuqsAdapter>
          <ReviewCountProvider>
            <TooltipProvider>
              <ConnectionBanner />
              <HeaderWithBadge />
              <main>{children}</main>
              <Toaster theme="dark" position="bottom-right" />
            </TooltipProvider>
          </ReviewCountProvider>
        </NuqsAdapter>
      </body>
    </html>
  )
}
