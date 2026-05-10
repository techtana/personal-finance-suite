import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { handleAuthCallback } from '../lib/auth'
import { useAuthStore } from '../store/authStore'

export function AuthCallback() {
  const navigate = useNavigate()
  const { setTokens } = useAuthStore()
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const error = params.get('error')

    if (error || !code) {
      navigate('/login?error=' + (error ?? 'missing_code'))
      return
    }

    handleAuthCallback(code)
      .then((tokens) => {
        setTokens(tokens)
        navigate('/', { replace: true })
      })
      .catch((err: unknown) => {
        console.error(err)
        navigate('/login?error=token_exchange')
      })
  }, [navigate, setTokens])

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#eceef2' }}>
      <div className="text-center">
        <div className="inline-block w-8 h-8 border-4 border-[#3b5fc0] border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm" style={{ color: '#5c6473' }}>Completing sign-in…</p>
      </div>
    </div>
  )
}
