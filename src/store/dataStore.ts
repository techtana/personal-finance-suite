// Central data store — loads all JSON files from Drive, holds them in memory,
// and provides write-through save functions.

import { create } from 'zustand'
import type {
  Account,
  RecurringTransaction,
  OneTimeTransaction,
  BlanketExpense,
  RsuGrant,
  EsppPlan,
  Snapshot,
  Loan,
} from '../types'
import type { DriveClient } from '../lib/drive'

interface DataState {
  // ── Data ──────────────────────────────────────────────────────────────────
  accounts: Account[]
  recurring: RecurringTransaction[]
  oneTime: OneTimeTransaction[]
  blanketExpenses: BlanketExpense[]
  rsuGrants: RsuGrant[]
  esppPlans: EsppPlan[]
  snapshots: Snapshot[]
  loans: Loan[]

  // ── Status ────────────────────────────────────────────────────────────────
  loading: boolean
  error: string | null

  // ── Actions ───────────────────────────────────────────────────────────────
  loadAll: (client: DriveClient) => Promise<void>

  saveAccounts: (client: DriveClient, accounts: Account[]) => Promise<void>
  saveTransactions: (
    client: DriveClient,
    recurring: RecurringTransaction[],
    oneTime: OneTimeTransaction[],
  ) => Promise<void>
  saveBlanket: (client: DriveClient, blanket: BlanketExpense[]) => Promise<void>
  saveEquity: (client: DriveClient, grants: RsuGrant[], plans: EsppPlan[]) => Promise<void>
  saveSnapshots: (client: DriveClient, snapshots: Snapshot[]) => Promise<void>
  saveLoans: (client: DriveClient, loans: Loan[]) => Promise<void>

  // ── Local mutators (optimistic, call save* to persist) ────────────────────
  setAccounts: (accounts: Account[]) => void
  setRecurring: (recurring: RecurringTransaction[]) => void
  setOneTime: (oneTime: OneTimeTransaction[]) => void
  setBlanket: (blanket: BlanketExpense[]) => void
  setRsuGrants: (grants: RsuGrant[]) => void
  setEsppPlans: (plans: EsppPlan[]) => void
  setSnapshots: (snapshots: Snapshot[]) => void
  setLoans: (loans: Loan[]) => void
}

export const useDataStore = create<DataState>((set) => ({
  accounts: [],
  recurring: [],
  oneTime: [],
  blanketExpenses: [],
  rsuGrants: [],
  esppPlans: [],
  snapshots: [],
  loans: [],
  loading: false,
  error: null,

  loadAll: async (client) => {
    set({ loading: true, error: null })
    try {
      await client.loadFileIndex()

      const [
        acctFile,
        txFile,
        blanketFile,
        equityFile,
        snapFile,
        loansFile,
      ] = await Promise.all([
        client.read<{ accounts: Account[] }>('accounts'),
        client.read<{ recurring: RecurringTransaction[]; oneTime: OneTimeTransaction[] }>('transactions'),
        client.read<{ blanketExpenses: BlanketExpense[] }>('blanketExpenses'),
        client.read<{ rsuGrants: RsuGrant[]; esppPlans: EsppPlan[] }>('equity'),
        client.read<{ snapshots: Snapshot[] }>('snapshots'),
        client.read<{ loans: Loan[] }>('loans'),
      ])

      set({
        accounts: acctFile.accounts ?? [],
        recurring: txFile.recurring ?? [],
        oneTime: txFile.oneTime ?? [],
        blanketExpenses: blanketFile.blanketExpenses ?? [],
        rsuGrants: equityFile.rsuGrants ?? [],
        esppPlans: equityFile.esppPlans ?? [],
        snapshots: snapFile.snapshots ?? [],
        loans: loansFile.loans ?? [],
        loading: false,
      })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },

  saveAccounts: async (client, accounts) => {
    set({ accounts })
    await client.write('accounts', { accounts })
  },

  saveTransactions: async (client, recurring, oneTime) => {
    set({ recurring, oneTime })
    await client.write('transactions', { recurring, oneTime })
  },

  saveBlanket: async (client, blanketExpenses) => {
    set({ blanketExpenses })
    await client.write('blanketExpenses', { blanketExpenses })
  },

  saveEquity: async (client, rsuGrants, esppPlans) => {
    set({ rsuGrants, esppPlans })
    await client.write('equity', { rsuGrants, esppPlans })
  },

  saveSnapshots: async (client, snapshots) => {
    set({ snapshots })
    await client.write('snapshots', { snapshots })
  },

  saveLoans: async (client, loans) => {
    set({ loans })
    await client.write('loans', { loans })
  },

  setAccounts: (accounts) => set({ accounts }),
  setRecurring: (recurring) => set({ recurring }),
  setOneTime: (oneTime) => set({ oneTime }),
  setBlanket: (blanketExpenses) => set({ blanketExpenses }),
  setRsuGrants: (rsuGrants) => set({ rsuGrants }),
  setEsppPlans: (esppPlans) => set({ esppPlans }),
  setSnapshots: (snapshots) => set({ snapshots }),
  setLoans: (loans) => set({ loans }),
}))
