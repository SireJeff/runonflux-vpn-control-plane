/** Toman<->USD conversion mirroring worker_api services.billing.conversion. */
export function usdToTomans(usd: number, rate: number): number {
  if (!rate || rate <= 0 || !usd || usd <= 0) return 0
  return Math.round(usd * rate)
}

export function tomansToUsd(tomans: number, rate: number): number {
  if (!rate || rate <= 0 || !tomans || tomans <= 0) return 0
  return Math.round((tomans / rate) * 100) / 100
}
