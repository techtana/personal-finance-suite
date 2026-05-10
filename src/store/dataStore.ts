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
import type { FirestoreClient } from '../lib/firestore'

interface DataState {
  accounts: Account[]
  recurring: RecurringTransaction[]
  oneTime: OneTimeTransaction[]
  blanketExpenses: BlanketExpense[]
  rsuGrants: RsuGrant[]
  esppPlans: EsppPlan[]
  snapshots: Snapshot[]
  loans: Loan[]

  loading: boolean
  error: string | null

  loadAll: (client: FirestoreClient) => Promise<void>

  saveAccounts:     (client: FirestoreClient, accounts: Account[]) => Promise<void>
  saveTransactions: (client: FirestoreClient, recurring: RecurringTransaction[], oneTime: OneTimeTransaction[]) => Promise<void>
  saveBlanket:      (client: FirestoreClient, blanket: BlanketExpense[]) => Promise<void>
  saveEquity:       (client: FirestoreClient, grants: RsuGrant[], plans: EsppPlan[]) => Promise<void>
  saveSnapshots:    (client: FirestoreClient, snapshots: Snapshot[]) => Promise<void>
  saveLoans:        (client: FirestoreClient, loans: Loan[]) => Promise<void>

  setAccounts:  (accounts: Account[]) => void
  setRecurring: (recurring: RecurringTransaction[]) => void
  setOneTime:   (oneTime: OneTimeTransaction[]) => void
  setBlanket:   (blanket: BlanketExpense[]) => void
  setRsuGrants: (grants: RsuGrant[]) => void
  setEsppPlans: (plans: EsppPlan[]) => void
  setSnapshots: (snapshots: Snapshot[]) => void
  setLoans:     (loans: Loan[]) => void
}

export const useDataStore = create<DataState>((set) => ({
  accounts: [], recurring: [], oneTime: [], blanketExpenses: [],
  rsuGrants: [], esppPlans: [], snapshots: [], loans: [],
  loading: false, error: null,

  loadAll: async (client) => {
    set({ loading: true, error: null })
    try {
      await client.loadFileIndex()
      const [acct, tx, blanket, equity, snaps, loans] = await Promise.all([
        client.read<{ accounts: Account[] }>('accounts'),
        client.read<{ recurring: RecurringTransaction[]; oneTime: OneTimeTransaction[] }>('transactions'),
        client.read<{ blanketExpenses: BlanketExpense[] }>('blanketExpenses'),
        client.read<{ rsuGrants: RsuGrant[]; esppPlans: EsppPlan[] }>('equity'),
        client.read<{ snapshots: Snapshot[] }>('snapshots'),
        client.read<{ loans: Loan[] }>('loans'),
      ])
      set({
        accounts:       acct.accounts        ?? [],
        recurring:      tx.recurring         ?? [],
        oneTime:        tx.oneTime           ?? [],
        blanketExpenses:blanket.blanketExpenses ?? [],
        rsuGrants:      equity.rsuGrants     ?? [],
        esppPlans:      equity.esppPlans     ?? [],
        snapshots:      snaps.snapshots      ?? [],
        loans:          loans.loans          ?? [],
        loading: false,
      })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },

  saveAccounts:     async (c, accounts)            => { set({ accounts });     await c.write('accounts', { accounts }) },
  saveTransactions: async (c, recurring, oneTime)  => { set({ recurring, oneTime }); await c.write('transactions', { recurring, oneTime }) },
  saveBlanket:      async (c, blanketExpenses)      => { set({ blanketExpenses }); await c.write('blanketExpenses', { blanketExpenses }) },
  saveEquity:       async (c, rsuGrants, esppPlans) => { set({ rsuGrants, esppPlans }); await c.write('equity', { rsuGrants, esppPlans }) },
  saveSnapshots:    async (c, snapshots)            => { set({ snapshots });   await c.write('snapshots', { snapshots }) },
  saveLoans:        async (c, loans)                => { set({ loans });       await c.write('loans', { loans }) },

  setAccounts:  (accounts)       => set({ accounts }),
  setRecurring: (recurring)      => set({ recurring }),
  setOneTime:   (oneTime)        => set({ oneTime }),
  setBlanket:   (blanketExpenses)=> set({ blanketExpenses }),
  setRsuGrants: (rsuGrants)      => set({ rsuGrants }),
  setEsppPlans: (esppPlans)      => set({ esppPlans }),
  setSnapshots: (snapshots)      => set({ snapshots }),
  setLoans:     (loans)          => set({ loans }),
}))
