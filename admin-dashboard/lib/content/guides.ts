/**
 * Bilingual setup guide content for /user/guide.
 *
 * Mirrors the bot's format_guide_android/ios/windows templates. URLs are
 * canonical GitHub releases (auto-redirect to latest). Update here if you
 * switch to App Store / TestFlight links for any platform.
 *
 * Backend's .env.production holds its own copy of these URLs (used by the
 * bot's /guide:android etc.). Keep them in sync when changing.
 */

export interface GuideClient {
  name: string
  url: string
  free: boolean
}

export interface GuideContent {
  recommendedClients: GuideClient[]
  steps: string[]
  troubleshooting: string[]
}

export type Platform = 'android' | 'ios' | 'windows'
export type GuideLang = 'fa' | 'en'

// Canonical URLs (kept in sync with worker_api/app/core/config.py defaults
// and the values populated in .env.production on the VM).
const URLS = {
  throneAndroid: 'https://github.com/PoneyClairDeLune/Throne/releases/latest',
  throneIos: 'https://github.com/PoneyClairDeLune/Throne/releases/latest',
  throneWindows: 'https://github.com/PoneyClairDeLune/Throne/releases/latest',
  hiddifyAndroid: 'https://github.com/hiddify/hiddify-next/releases/latest',
  hiddifyIos: 'https://github.com/hiddify/hiddify-next/releases/latest',
  hiddifyWindows: 'https://github.com/hiddify/hiddify-next/releases/latest',
  nekoboxAndroid: 'https://github.com/MatsuriDayo/NekoBoxForAndroid/releases/latest',
  nekorayWindows: 'https://github.com/MatsuriDayo/nekoray/releases/latest',
  streisandIos: 'https://github.com/GFWGuardian/Streisand/releases',
} as const

export const guides: Record<GuideLang, Record<Platform, GuideContent>> = {
  fa: {
    android: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneAndroid, free: true },
        { name: 'Hiddify', url: URLS.hiddifyAndroid, free: true },
        { name: 'NekoBox', url: URLS.nekoboxAndroid, free: true },
      ],
      steps: [
        'یکی از کلاینت‌های بالا را نصب کنید.',
        'اپ را باز کنید و روی «+» بزنید.',
        'گزینه «Subscription URL» را انتخاب کنید.',
        'لینک اشتراک خود را کپی و وارد کنید.',
        'روی «Update» بزنید.',
        'یک کشور را انتخاب کنید.',
        'دکمه اتصال را بزنید. ✓',
      ],
      troubleshooting: [
        'قطع می‌شود: DNS را روی 1.1.1.1 تنظیم کنید.',
        'کند است: کشور دیگری را امتحان کنید.',
        'کار نمی‌کند: Safemode را فعال کنید.',
      ],
    },
    ios: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneIos, free: true },
        { name: 'Hiddify', url: URLS.hiddifyIos, free: true },
        { name: 'Streisand', url: URLS.streisandIos, free: true },
      ],
      steps: [
        'یکی از کلاینت‌های بالا را نصب کنید.',
        'اپ را باز کنید.',
        'روی «+» بزنید → «Add Subscription».',
        'لینک اشتراک را کپی و وارد کنید.',
        'روی «Update» بزنید.',
        'کشور موردنظر را انتخاب کنید.',
        'دکمه اتصال را بزنید. ✓',
      ],
      troubleshooting: [
        'برای اولین اتصال، iOS اجازه افزودن VPN می‌خواهد — تأیید کنید.',
        'اگر اتصال برقرار نشد: Settings → General → VPN & Device Management را بررسی کنید.',
      ],
    },
    windows: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneWindows, free: true },
        { name: 'Nekoray', url: URLS.nekorayWindows, free: true },
        { name: 'Hiddify', url: URLS.hiddifyWindows, free: true },
      ],
      steps: [
        'فایل نصبی را دانلود و اجرا کنید.',
        'اپ را باز کنید.',
        'منوی Program → «Add profile from subscription URL».',
        'لینک اشتراک را وارد و Update بزنید.',
        'سرور موردنظر را از لیست انتخاب کنید.',
        'روی «Start» بزنید. ✓',
        'برای فعال کردن پروکسی سیستم: حالت «Tun Mode» یا «System Proxy» را روشن کنید.',
      ],
      troubleshooting: [
        'اگر سایت‌ها باز نمی‌شوند: System Proxy را بررسی کنید.',
        'اگر خطای cert داد: Settings → Allow Insecure را فعال کنید.',
      ],
    },
  },
  en: {
    android: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneAndroid, free: true },
        { name: 'Hiddify', url: URLS.hiddifyAndroid, free: true },
        { name: 'NekoBox', url: URLS.nekoboxAndroid, free: true },
      ],
      steps: [
        'Install one of the clients above.',
        'Open the app, tap "+".',
        'Select "Subscription URL".',
        'Copy your subscription link and paste here.',
        'Tap "Update".',
        'Pick a country.',
        'Tap connect. ✓',
      ],
      troubleshooting: [
        'Drops? Set DNS to 1.1.1.1.',
        'Slow? Try a different country.',
        'Not working? Enable Safemode in app settings.',
      ],
    },
    ios: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneIos, free: true },
        { name: 'Hiddify', url: URLS.hiddifyIos, free: true },
        { name: 'Streisand', url: URLS.streisandIos, free: true },
      ],
      steps: [
        'Install one of the clients above.',
        'Open the app.',
        'Tap "+" → "Add Subscription".',
        'Paste your subscription link.',
        'Tap "Update".',
        'Pick a country.',
        'Tap connect. ✓',
      ],
      troubleshooting: [
        'First connection: iOS will ask to add VPN profile — approve.',
        'If connection fails: check Settings → General → VPN & Device Management.',
      ],
    },
    windows: {
      recommendedClients: [
        { name: 'Throne', url: URLS.throneWindows, free: true },
        { name: 'Nekoray', url: URLS.nekorayWindows, free: true },
        { name: 'Hiddify', url: URLS.hiddifyWindows, free: true },
      ],
      steps: [
        'Download and run the installer.',
        'Open the app.',
        'Program menu → "Add profile from subscription URL".',
        'Paste your subscription link and tap Update.',
        'Pick a server from the list.',
        'Tap "Start". ✓',
        'Enable "Tun Mode" or "System Proxy" for system-wide routing.',
      ],
      troubleshooting: [
        'Sites not loading? Check System Proxy.',
        'Cert error? Enable Settings → Allow Insecure.',
      ],
    },
  },
}

export const platformMeta: Record<Platform, { icon: string; faName: string; enName: string }> = {
  android: { icon: '🤖', faName: 'اندروید', enName: 'Android' },
  ios: { icon: '🍎', faName: 'آیفون', enName: 'iOS' },
  windows: { icon: '💻', faName: 'ویندوز', enName: 'Windows' },
}
