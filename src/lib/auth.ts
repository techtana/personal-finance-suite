// Firebase Auth wrapper — Google sign-in via popup.
// No PKCE, no client secret, no token management needed.
// Firebase handles token refresh automatically.

import {
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  type User,
} from 'firebase/auth'
import { auth, googleProvider } from './firebase'

export type { User }

export async function signIn(): Promise<User> {
  const result = await signInWithPopup(auth, googleProvider)
  return result.user
}

export async function signOut(): Promise<void> {
  await firebaseSignOut(auth)
}

export function onAuthChange(cb: (user: User | null) => void): () => void {
  return onAuthStateChanged(auth, cb)
}

export function currentUser(): User | null {
  return auth.currentUser
}
