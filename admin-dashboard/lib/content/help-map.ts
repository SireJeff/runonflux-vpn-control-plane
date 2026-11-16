export const superHelpMap: Record<string, string> = {
  '/super/dashboard': '1-concepts',
  '/super/admins': '4-managing-resellers',
  '/super/orders': '5-wire-orders--platform-settings',
  '/super/apps': '7-flux-apps-bot-oversight-analytics--troubleshooting',
  '/super/domains': '6-tld--dns-management',
  '/super/analytics': '7-flux-apps-bot-oversight-analytics--troubleshooting',
  '/super/settings': '5-wire-orders--platform-settings',
}

export const dashboardHelpMap: Record<string, string> = {
  '/dashboard': '2-getting-started',
  '/dashboard/users': '6-managing-end-users--troubleshooting',
  '/dashboard/wallet': '3-wallet--billing',
  '/dashboard/analytics': '2-getting-started',
  '/dashboard/bot-config': '4-your-telegram-bot--what-end-users-see',
  '/dashboard/packages': '5-packages-orders--referral',
  '/dashboard/orders': '5-packages-orders--referral',
  '/dashboard/referral': '5-packages-orders--referral',
  '/dashboard/settings': '2-getting-started',
}

export function helpAnchorForPath(pathname: string): { href: string } | null {
  if (pathname.startsWith('/super')) {
    const anchor = superHelpMap[pathname]
    return anchor ? { href: `/super/help#${anchor}` } : null
  }
  if (pathname.startsWith('/dashboard')) {
    const anchor = dashboardHelpMap[pathname]
    return anchor ? { href: `/dashboard/help#${anchor}` } : null
  }
  return null
}
