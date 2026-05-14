import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import './index.css'
import App from './App.tsx'
import { setClerkTokenGetter } from '@/api/client'

// Clerk publishable key — set in Railway env / .env.local
// VITE_-prefixed so Vite exposes it to the client bundle.
const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined

if (!CLERK_PUBLISHABLE_KEY) {
  // Loud warning at boot — if this is missing, Clerk won't initialize and
  // every protected route hangs on "Loading…".
  // eslint-disable-next-line no-console
  console.error(
    'VITE_CLERK_PUBLISHABLE_KEY is not set. Add it to your .env.local (dev) or Railway environment variables (prod).',
  )
}

/**
 * Bridge: wires Clerk's `getToken()` into the axios client so every API call
 * gets a fresh Clerk JWT. Rendered inside <ClerkProvider> so it can use the
 * hook; toggles itself off on unmount to avoid stale closures.
 */
function ClerkTokenBridge() {
  const { getToken } = useAuth()
  useEffect(() => {
    setClerkTokenGetter(() => getToken())
    return () => setClerkTokenGetter(null)
  }, [getToken])
  return null
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY ?? ''}>
      <ClerkTokenBridge />
      <App />
    </ClerkProvider>
  </StrictMode>,
)
