import { create } from 'zustand'
import { onAuthChange, signIn, signOut, type User } from '../lib/auth'
import { FirestoreClient } from '../lib/firestore'

interface AuthState {
  user: User | null
  firestoreClient: FirestoreClient | null
  initialized: boolean

  init: () => void
  login: () => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  firestoreClient: null,
  initialized: false,

  init: () => {
    onAuthChange((user) => {
      set({
        user,
        firestoreClient: user ? new FirestoreClient(user.uid) : null,
        initialized: true,
      })
    })
  },

  login: async () => {
    await signIn()
    // onAuthChange fires automatically and updates state
  },

  logout: async () => {
    await signOut()
  },
}))
