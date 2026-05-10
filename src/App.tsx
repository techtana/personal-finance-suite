import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { useDataStore } from './store/dataStore'
import { useSettingsStore } from './store/settingsStore'

import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { AuthCallback } from './pages/AuthCallback'
import { Dashboard } from './pages/Dashboard'
import { Transactions } from './pages/Transactions'
import { Equity } from './pages/Equity'
import { Accounts } from './pages/Accounts'
import { Loans } from './pages/Loans'
import { Timeline } from './pages/Timeline'
import { Settings } from './pages/Settings'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { tokens, initialized } = useAuthStore()
  if (!initialized) return <LoadingScreen />
  if (!tokens) return <Navigate to="/login" replace />
  return <>{children}</>
}

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#eceef2' }}>
      <div className="text-center">
        <div className="inline-block w-8 h-8 border-4 border-[#3b5fc0] border-t-transparent rounded-full animate-spin mb-3" />
        <p className="text-sm" style={{ color: '#5c6473' }}>Loading…</p>
      </div>
    </div>
  )
}

function AppLoader({ children }: { children: React.ReactNode }) {
  const { driveClient } = useAuthStore()
  const { loadAll, loading } = useDataStore()
  const { loadFromDrive } = useSettingsStore()

  useEffect(() => {
    if (!driveClient) return
    loadAll(driveClient)
    loadFromDrive(driveClient)
  }, [driveClient, loadAll, loadFromDrive])

  if (loading) return <LoadingScreen />
  return <>{children}</>
}

export function App() {
  const { init } = useAuthStore()

  useEffect(() => {
    init()
  }, [init])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          element={
            <RequireAuth>
              <AppLoader>
                <Layout />
              </AppLoader>
            </RequireAuth>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="transactions" element={<Transactions />} />
          <Route path="equity" element={<Equity />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="loans" element={<Loans />} />
          <Route path="timeline" element={<Timeline />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
