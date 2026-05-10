import { create } from 'zustand'
import {
  loadTokens,
  saveTokens,
  clearTokens,
  refreshAccessToken,
  isExpired,
  type TokenSet,
} from '../lib/auth'
import { DriveClient } from '../lib/drive'

interface AuthState {
  tokens: TokenSet | null
  driveClient: DriveClient | null
  initialized: boolean

  init: () => Promise<void>
  setTokens: (t: TokenSet) => void
  signOut: () => void
  getAccessToken: () => string
}

export const useAuthStore = create<AuthState>((set, get) => ({
  tokens: null,
  driveClient: null,
  initialized: false,

  init: async () => {
    let tokens = loadTokens()
    if (!tokens) {
      set({ initialized: true })
      return
    }
    if (isExpired(tokens)) {
      try {
        tokens = await refreshAccessToken(tokens)
      } catch {
        clearTokens()
        set({ initialized: true })
        return
      }
    }
    const driveClient = new DriveClient(() => get().tokens?.accessToken ?? '')
    set({ tokens, driveClient, initialized: true })
  },

  setTokens: (tokens) => {
    saveTokens(tokens)
    const driveClient = new DriveClient(() => get().tokens?.accessToken ?? '')
    set({ tokens, driveClient })
  },

  signOut: () => {
    clearTokens()
    set({ tokens: null, driveClient: null })
  },

  getAccessToken: () => {
    const { tokens } = get()
    if (!tokens) throw new Error('Not signed in')
    return tokens.accessToken
  },
}))
