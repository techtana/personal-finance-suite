import { useSettingsStore } from '../store/settingsStore'
import { useAuthStore } from '../store/authStore'
import type { Theme, SidebarStyle, Density, AppSettings } from '../types'

type Tab = 'general' | 'appearance' | 'notifications' | 'account'

import { useState } from 'react'

export function Settings() {
  const { settings, updateSettings } = useSettingsStore()
  const { tokens, signOut, driveClient } = useAuthStore()
  const [tab, setTab] = useState<Tab>('general')

  const update = (patch: Partial<AppSettings>) => updateSettings(patch, driveClient ?? undefined)

  const TABS: { id: Tab; label: string }[] = [
    { id: 'general', label: 'General' },
    { id: 'appearance', label: 'Appearance' },
    { id: 'account', label: 'Account' },
  ]

  const ACCENT_PRESETS = [
    '#3b5fc0', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  ]

  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: '#0f172a' }}>Settings</h1>
        <p className="text-sm mt-1" style={{ color: '#5c6473' }}>App preferences · appearance · account</p>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-[#d1d5db] mb-8 gap-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="px-5 py-3 text-sm font-semibold border-b-2 -mb-px transition-colors"
            style={{
              borderBottomColor: tab === t.id ? '#3b5fc0' : 'transparent',
              color: tab === t.id ? '#3b5fc0' : '#5c6473',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* General */}
      {tab === 'general' && (
        <div className="space-y-6 max-w-xl">
          <SettingRow label="Currency" hint="ISO 4217 code used for all display values">
            <input
              className="fi"
              value={settings.currency}
              onChange={(e) => update({ currency: e.target.value })}
            />
          </SettingRow>

          <SettingRow label="Locale" hint="Affects number and date formatting">
            <input
              className="fi"
              value={settings.locale}
              onChange={(e) => update({ locale: e.target.value })}
            />
          </SettingRow>

          <SettingRow
            label="Divergence Alert Threshold"
            hint="Show reconciliation alert when actual vs predicted exceeds this %"
          >
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                max={100}
                className="fi w-24"
                value={settings.divergenceAlertPct / 100}
                onChange={(e) => update({ divergenceAlertPct: Math.round(parseFloat(e.target.value) * 100) })}
              />
              <span className="text-sm" style={{ color: '#5c6473' }}>%</span>
            </div>
          </SettingRow>

          <SettingRow label="Start of Week">
            <ToggleGroup
              options={[{ value: '0', label: 'Sunday' }, { value: '1', label: 'Monday' }]}
              value={String(settings.startOfWeek)}
              onChange={(v) => update({ startOfWeek: +v as 0 | 1 })}
            />
          </SettingRow>
        </div>
      )}

      {/* Appearance */}
      {tab === 'appearance' && (
        <div className="space-y-8 max-w-xl">
          <SettingRow label="Theme">
            <ToggleGroup
              options={[
                { value: 'light', label: 'Light' },
                { value: 'dark', label: 'Dark' },
                { value: 'system', label: 'System' },
              ]}
              value={settings.theme}
              onChange={(v) => update({ theme: v as Theme })}
            />
          </SettingRow>

          <SettingRow label="Accent Color">
            <div className="flex items-center gap-2 flex-wrap">
              {ACCENT_PRESETS.map((c) => (
                <button
                  key={c}
                  onClick={() => update({ accentColor: c })}
                  className="w-8 h-8 rounded-full border-2 transition-all"
                  style={{
                    background: c,
                    borderColor: settings.accentColor === c ? '#0f172a' : 'transparent',
                    boxShadow: settings.accentColor === c ? '0 0 0 2px #fff, 0 0 0 4px #0f172a' : 'none',
                  }}
                />
              ))}
              <input
                type="color"
                value={settings.accentColor}
                onChange={(e) => update({ accentColor: e.target.value })}
                className="w-8 h-8 rounded-full border border-[#d1d5db] cursor-pointer overflow-hidden"
                title="Custom color"
              />
            </div>
          </SettingRow>

          <SettingRow label="Sidebar Style">
            <ToggleGroup
              options={[
                { value: 'icon-label', label: 'Icon + Label' },
                { value: 'icon-only', label: 'Icon Only' },
              ]}
              value={settings.sidebarStyle}
              onChange={(v) => update({ sidebarStyle: v as SidebarStyle })}
            />
          </SettingRow>

          <SettingRow label="Density">
            <ToggleGroup
              options={[
                { value: 'comfortable', label: 'Comfortable' },
                { value: 'compact', label: 'Compact' },
              ]}
              value={settings.density}
              onChange={(v) => update({ density: v as Density })}
            />
          </SettingRow>

          <SettingRow label="Font Size">
            <ToggleGroup
              options={[
                { value: 'sm', label: 'Small' },
                { value: 'md', label: 'Medium' },
                { value: 'lg', label: 'Large' },
              ]}
              value={settings.fontSize}
              onChange={(v) => update({ fontSize: v as 'sm' | 'md' | 'lg' })}
            />
          </SettingRow>
        </div>
      )}

      {/* Account */}
      {tab === 'account' && (
        <div className="max-w-xl space-y-6">
          {tokens ? (
            <>
              <div className="flex items-center gap-4 p-5 bg-white border border-[#d1d5db] rounded-xl">
                {tokens.picture && (
                  <img src={tokens.picture} alt={tokens.name} className="w-12 h-12 rounded-full" />
                )}
                <div>
                  <div className="text-sm font-bold" style={{ color: '#0f172a' }}>{tokens.name}</div>
                  <div className="text-xs mt-0.5" style={{ color: '#5c6473' }}>{tokens.email}</div>
                </div>
              </div>

              <div className="p-5 bg-white border border-[#d1d5db] rounded-xl">
                <div className="text-sm font-bold mb-1" style={{ color: '#0f172a' }}>Google Drive Storage</div>
                <div className="text-xs mb-3" style={{ color: '#5c6473' }}>
                  All data is stored in a folder named "Personal Finance Suite" in your Google Drive.
                  Only files created by this app are accessible.
                </div>
                <div className="text-xs font-mono px-2 py-1.5 rounded" style={{ background: '#f4f6f9', color: '#3b5fc0' }}>
                  drive.file scope · no other files can be read
                </div>
              </div>

              <button
                onClick={signOut}
                className="px-4 py-2 rounded-lg text-sm font-semibold border border-[#d1d5db] text-[#991b1b] hover:bg-[#fee2e2] transition-colors"
              >
                Sign Out
              </button>
            </>
          ) : (
            <p className="text-sm" style={{ color: '#5c6473' }}>Not signed in.</p>
          )}
        </div>
      )}
    </>
  )
}

function SettingRow({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="block text-sm font-semibold mb-1.5" style={{ color: '#0f172a' }}>{label}</label>
      {hint && <p className="text-xs mb-2" style={{ color: '#5c6473' }}>{hint}</p>}
      {children}
    </div>
  )
}

function ToggleGroup({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex border border-[#d1d5db] rounded-lg overflow-hidden w-fit">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-4 py-2 text-sm transition-colors"
          style={{
            background: value === opt.value ? '#3b5fc0' : '#fff',
            color: value === opt.value ? '#fff' : '#0f172a',
            fontWeight: value === opt.value ? 600 : 400,
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

