import { useState } from 'react'
import { useAuthStore } from '../store/authStore'

export function Login() {
  const { login } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSignIn() {
    setLoading(true)
    setError('')
    try {
      await login()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (!msg.includes('popup-closed')) setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#eceef2' }}>
      <div className="bg-white rounded-2xl shadow-xl p-10 w-full max-w-sm text-center">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl font-bold mx-auto mb-6"
          style={{ background: '#3b5fc0', color: '#fff' }}
        >
          ₮
        </div>

        <h1 className="text-2xl font-extrabold tracking-tight mb-1" style={{ color: '#0f172a' }}>
          Personal Finance Suite
        </h1>
        <p className="text-sm mb-8" style={{ color: '#5c6473' }}>
          Your data is private and stored securely in the cloud.
        </p>

        {error && (
          <p className="text-xs mb-4 px-3 py-2 rounded-lg bg-red-50 text-red-700">{error}</p>
        )}

        <button
          onClick={handleSignIn}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 py-3 px-5 rounded-xl border border-[#d1d5db] bg-white font-semibold text-[#0f172a] hover:bg-[#f4f6f9] transition-colors text-sm disabled:opacity-60"
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-[#3b5fc0] border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
          )}
          {loading ? 'Signing in…' : 'Sign in with Google'}
        </button>

        <p className="text-xs mt-6" style={{ color: '#5c6473' }}>
          No account setup required. Sign in with any Google account.
        </p>
      </div>
    </div>
  )
}
