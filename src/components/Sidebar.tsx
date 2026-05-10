import { NavLink } from 'react-router-dom'
import { useSettingsStore } from '../store/settingsStore'
import { useAuthStore } from '../store/authStore'

interface NavItem {
  to: string
  icon: string
  label: string
}

const TOP_NAV: NavItem[] = [
  { to: '/',            icon: '⊞',  label: 'Home' },
  { to: '/timeline',   icon: '📈', label: 'Timeline' },
]

const MID_NAV: NavItem[] = [
  { to: '/transactions', icon: '↕',  label: 'Txns' },
  { to: '/equity',       icon: '◈',  label: 'Equity' },
]

const BOT_NAV: NavItem[] = [
  { to: '/accounts', icon: '🏦', label: 'Accounts' },
  { to: '/loans',    icon: '📋', label: 'Loans' },
]

export function Sidebar() {
  const { settings } = useSettingsStore()
  const { logout, user } = useAuthStore()
  const iconOnly = settings.sidebarStyle === 'icon-only'

  return (
    <nav
      className="flex flex-col items-center py-4 gap-0.5 flex-shrink-0 sticky top-0 h-screen"
      style={{ width: 76, background: '#f4f6f9', borderRight: '1px solid #d1d5db' }}
    >
      {/* Logo mark */}
      <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3 text-lg font-bold"
           style={{ background: '#3b5fc0', color: '#fff' }}>
        ₮
      </div>

      {TOP_NAV.map((item) => (
        <NavItem key={item.to} item={item} iconOnly={iconOnly} />
      ))}

      <hr className="w-9 border-t my-1" style={{ borderColor: '#d1d5db' }} />

      {MID_NAV.map((item) => (
        <NavItem key={item.to} item={item} iconOnly={iconOnly} />
      ))}

      <hr className="w-9 border-t my-1" style={{ borderColor: '#d1d5db' }} />

      {BOT_NAV.map((item) => (
        <NavItem key={item.to} item={item} iconOnly={iconOnly} />
      ))}

      {/* Bottom: Settings + avatar */}
      <div className="mt-auto flex flex-col items-center gap-1">
        <NavItem item={{ to: '/settings', icon: '⚙', label: 'Settings' }} iconOnly={iconOnly} />
        {user?.photoURL && (
          <button
            onClick={logout}
            title="Sign out"
            className="w-8 h-8 rounded-full overflow-hidden mt-1 opacity-70 hover:opacity-100 transition-opacity"
          >
            <img src={user.photoURL} alt={user.displayName ?? ''} className="w-full h-full object-cover" />
          </button>
        )}
      </div>
    </nav>
  )
}

function NavItem({ item, iconOnly }: { item: NavItem; iconOnly: boolean }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        [
          'flex flex-col items-center justify-center rounded-xl text-xl gap-0.5 transition-all',
          'no-underline',
          isActive
            ? 'text-[#3b5fc0] bg-[#eef1fb] shadow-[inset_3px_0_0_#3b5fc0]'
            : 'text-[#5c6473] hover:bg-[#eef1fb] hover:text-[#3b5fc0]',
        ].join(' ')
      }
      style={{ width: 60, height: 52 }}
    >
      <span>{item.icon}</span>
      {!iconOnly && (
        <span className="text-[10px] font-semibold leading-none tracking-wide">
          {item.label}
        </span>
      )}
    </NavLink>
  )
}
