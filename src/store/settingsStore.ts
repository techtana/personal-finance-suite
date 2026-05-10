import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AppSettings } from '../types'
import type { DriveClient } from '../lib/drive'

const DEFAULTS: AppSettings = {
  currency: 'USD',
  locale: 'en-US',
  theme: 'light',
  accentColor: '#3b5fc0',
  sidebarStyle: 'icon-label',
  density: 'comfortable',
  fontSize: 'md',
  divergenceAlertPct: 500,
  startOfWeek: 0,
}

interface SettingsState {
  settings: AppSettings
  updateSettings: (patch: Partial<AppSettings>, client?: DriveClient) => Promise<void>
  loadFromDrive: (client: DriveClient) => Promise<void>
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULTS,

      updateSettings: async (patch, client) => {
        const next = { ...get().settings, ...patch }
        set({ settings: next })
        if (client) {
          await client.write('settings', { settings: next })
        }
      },

      loadFromDrive: async (client) => {
        try {
          const file = await client.read<{ settings: AppSettings }>('settings')
          if (file.settings) set({ settings: { ...DEFAULTS, ...file.settings } })
        } catch {
          // file might not exist yet — defaults are fine
        }
      },
    }),
    {
      name: 'pfs:settings',
      partialize: (s) => ({ settings: s.settings }),
    },
  ),
)
