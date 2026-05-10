// Firestore client — same read/write interface as the old DriveClient.
// Data lives at: users/{uid}/data/{key}  (one document per data type)
// Each document stores the same shape as the old Drive JSON files.

import {
  doc,
  getDoc,
  setDoc,
  collection,
  getDocs,
  writeBatch,
  Timestamp,
} from 'firebase/firestore'
import { db } from './firebase'

export const FILE_NAMES = {
  accounts:       'accounts',
  transactions:   'transactions',
  blanketExpenses:'blanketExpenses',
  equity:         'equity',
  snapshots:      'snapshots',
  loans:          'loans',
  settings:       'settings',
} as const

export type FileKey = keyof typeof FILE_NAMES

const DEFAULTS: Record<FileKey, unknown> = {
  accounts:       { accounts: [] },
  transactions:   { recurring: [], oneTime: [] },
  blanketExpenses:{ blanketExpenses: [] },
  equity:         { rsuGrants: [], esppPlans: [] },
  snapshots:      { snapshots: [] },
  loans:          { loans: [] },
  settings:       {
    settings: {
      currency: 'USD', locale: 'en-US', theme: 'light',
      accentColor: '#3b5fc0', sidebarStyle: 'icon-label',
      density: 'comfortable', fontSize: 'md',
      divergenceAlertPct: 500, startOfWeek: 0,
    },
  },
}

export class FirestoreClient {
  constructor(private uid: string) {}

  private ref(key: FileKey) {
    return doc(db, 'users', this.uid, 'data', FILE_NAMES[key])
  }

  // No-op — Firestore doesn't need a separate index load
  async loadFileIndex(): Promise<void> {}

  async read<T>(key: FileKey): Promise<T> {
    const snap = await getDoc(this.ref(key))
    if (!snap.exists()) {
      // Create with defaults on first access
      await setDoc(this.ref(key), DEFAULTS[key])
      return DEFAULTS[key] as T
    }
    return snap.data() as T
  }

  async write<T extends object>(key: FileKey, data: T): Promise<void> {
    await setDoc(this.ref(key), data)
  }

  // ── Export all user data as a single JSON object ─────────────────────────
  async exportAll(): Promise<Record<string, unknown>> {
    const keys = Object.keys(FILE_NAMES) as FileKey[]
    const entries = await Promise.all(
      keys.map(async (key) => {
        const snap = await getDoc(this.ref(key))
        return [key, snap.exists() ? snap.data() : DEFAULTS[key]] as const
      }),
    )
    return Object.fromEntries(entries)
  }
}
