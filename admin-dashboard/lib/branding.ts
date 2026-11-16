'use client'

import { useState, useEffect } from 'react'

/**
 * Hook for site name that avoids hydration mismatch.
 * Returns 'FluxVPN' during SSR and initial hydration,
 * then updates to 'VPN Panel' on operator5.example.invalid after mount.
 */
export function useSiteName() {
  const [siteName, setSiteName] = useState('FluxVPN')

  useEffect(() => {
    if (window.location.hostname === 'panel.operator5.example.invalid') {
      setSiteName('VPN Panel')
    }
  }, [])

  return siteName
}
