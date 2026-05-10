import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="flex min-h-screen" style={{ background: '#eceef2' }}>
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[860px] mx-auto px-10 py-9">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
