// OAuth 2.0 PKCE flow with Google
// Tokens are stored in localStorage (no server involved).

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string
// Optional — required for "Web application" OAuth client type, not needed for "Desktop app" type
const CLIENT_SECRET = (import.meta.env.VITE_GOOGLE_CLIENT_SECRET as string | undefined) || undefined
const REDIRECT_URI = `${window.location.origin}/auth/callback`
const AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
const TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
const SCOPES = [
  'https://www.googleapis.com/auth/drive.file',
  'https://www.googleapis.com/auth/userinfo.email',
  'https://www.googleapis.com/auth/userinfo.profile',
].join(' ')

const LS_VERIFIER = 'pfs:pkce_verifier'
const LS_TOKENS = 'pfs:tokens'

export interface TokenSet {
  accessToken: string
  refreshToken: string
  expiresAt: number   // epoch ms
  email: string
  name: string
  picture: string
}

// ── PKCE helpers ────────────────────────────────────────────────────────────

function randomBytes(length: number): Uint8Array {
  const buf = new Uint8Array(length)
  crypto.getRandomValues(buf)
  return buf
}

function base64url(buf: Uint8Array): string {
  return btoa(String.fromCharCode(...buf))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

async function sha256(plain: string): Promise<Uint8Array> {
  const enc = new TextEncoder().encode(plain)
  const digest = await crypto.subtle.digest('SHA-256', enc)
  return new Uint8Array(digest)
}

// ── Public API ───────────────────────────────────────────────────────────────

export async function startAuthFlow(): Promise<void> {
  const verifier = base64url(randomBytes(48))
  const challenge = base64url(await sha256(verifier))
  sessionStorage.setItem(LS_VERIFIER, verifier)

  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: 'code',
    scope: SCOPES,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    access_type: 'offline',
    prompt: 'consent',
  })

  window.location.href = `${AUTH_ENDPOINT}?${params}`
}

export async function handleAuthCallback(code: string): Promise<TokenSet> {
  const verifier = sessionStorage.getItem(LS_VERIFIER)
  if (!verifier) throw new Error('PKCE verifier missing — restart sign-in')
  sessionStorage.removeItem(LS_VERIFIER)

  const res = await fetch(TOKEN_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      grant_type: 'authorization_code',
      code_verifier: verifier,
      ...(CLIENT_SECRET ? { client_secret: CLIENT_SECRET } : {}),
    }),
  })

  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Token exchange failed: ${err}`)
  }

  const data = await res.json() as {
    access_token: string
    refresh_token?: string
    expires_in: number
  }

  const userRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
    headers: { Authorization: `Bearer ${data.access_token}` },
  })
  const user = await userRes.json() as { email: string; name: string; picture: string }

  const tokens: TokenSet = {
    accessToken: data.access_token,
    refreshToken: data.refresh_token ?? '',
    expiresAt: Date.now() + data.expires_in * 1000,
    email: user.email,
    name: user.name,
    picture: user.picture,
  }

  saveTokens(tokens)
  return tokens
}

export async function refreshAccessToken(tokens: TokenSet): Promise<TokenSet> {
  const res = await fetch(TOKEN_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: CLIENT_ID,
      grant_type: 'refresh_token',
      refresh_token: tokens.refreshToken,
      ...(CLIENT_SECRET ? { client_secret: CLIENT_SECRET } : {}),
    }),
  })

  if (!res.ok) throw new Error('Token refresh failed — please sign in again')

  const data = await res.json() as { access_token: string; expires_in: number }
  const refreshed: TokenSet = {
    ...tokens,
    accessToken: data.access_token,
    expiresAt: Date.now() + data.expires_in * 1000,
  }
  saveTokens(refreshed)
  return refreshed
}

export function loadTokens(): TokenSet | null {
  try {
    const raw = localStorage.getItem(LS_TOKENS)
    return raw ? (JSON.parse(raw) as TokenSet) : null
  } catch {
    return null
  }
}

export function saveTokens(tokens: TokenSet): void {
  localStorage.setItem(LS_TOKENS, JSON.stringify(tokens))
}

export function clearTokens(): void {
  localStorage.removeItem(LS_TOKENS)
}

export function isExpired(tokens: TokenSet): boolean {
  return Date.now() >= tokens.expiresAt - 60_000   // 60 s buffer
}
