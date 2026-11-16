'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useSiteName } from '@/lib/branding'
import { LogOut, Wifi, Activity } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { I18nProvider } from '@/lib/i18n/user-portal'

const endUserNavItems = [
  {
    title: 'Connections',
    href: '/user/connections',
    icon: Wifi,
  },
  {
    title: 'Usage',
    href: '/user/usage',
    icon: Activity,
  },
]

export default function EndUserLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const { logout, user } = useAuth()
  const siteName = useSiteName()

  return (
    <I18nProvider>
    <div className="min-h-screen bg-muted/40">
      {/* Header Bar */}
      <header className="sticky top-0 z-40 border-b bg-background">
        <div className="flex h-14 items-center gap-4 px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <Wifi className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="text-lg font-bold">{siteName}</span>
          </div>

          {/* Navigation Tabs */}
          <nav className="ml-6 flex items-center gap-1">
            {endUserNavItems.map((item) => {
              const Icon = item.icon
              const isActive = pathname === item.href

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.title}</span>
                </Link>
              )
            })}
          </nav>

          {/* Right side - User info + Logout */}
          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="hidden sm:inline text-sm text-muted-foreground">
                {user.display_name || user.username}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="gap-2 text-muted-foreground hover:text-destructive"
              onClick={() => logout()}
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Page Content */}
      <main className="p-6">
        <div className="mx-auto max-w-5xl">{children}</div>
      </main>
    </div>
    </I18nProvider>
  )
}
