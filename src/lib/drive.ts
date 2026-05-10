// Google Drive REST API v3 adapter
// Stores all app JSON files in a single folder: "Personal Finance Suite"
// Uses drive.file scope — only sees files created by this app.

import type {
  Account,
  TransactionsFile,
  BlanketExpense,
  EquityFile,
  Snapshot,
  Loan,
  AppSettings,
} from '../types'

const DRIVE_API = 'https://www.googleapis.com/drive/v3'
const UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3'
const FOLDER_NAME = 'Personal Finance Suite'
const FOLDER_MIME = 'application/vnd.google-apps.folder'
const JSON_MIME = 'application/json'

// ── File name registry ───────────────────────────────────────────────────────

export const FILE_NAMES = {
  meta: 'meta.json',
  accounts: 'accounts.json',
  transactions: 'transactions.json',
  blanketExpenses: 'blanket-expenses.json',
  equity: 'equity.json',
  snapshots: 'snapshots.json',
  settings: 'settings.json',
  loans: 'loans.json',
} as const

export type FileKey = keyof typeof FILE_NAMES

// ── Default empty payloads ───────────────────────────────────────────────────

export const DEFAULTS: Record<FileKey, unknown> = {
  meta: { version: '1', files: {} },
  accounts: { accounts: [] },
  transactions: { recurring: [], oneTime: [] },
  blanketExpenses: { blanketExpenses: [] },
  equity: { rsuGrants: [], esppPlans: [] },
  snapshots: { snapshots: [] },
  settings: {
    currency: 'USD',
    locale: 'en-US',
    theme: 'light',
    accentColor: '#3b5fc0',
    sidebarStyle: 'icon-label',
    density: 'comfortable',
    fontSize: 'md',
    divergenceAlertPct: 500,
    startOfWeek: 0,
  },
  loans: { loans: [] },
}

// ── Drive client ─────────────────────────────────────────────────────────────

export class DriveClient {
  private folderId: string | null = null
  private fileIndex: Map<string, string> = new Map() // name → fileId

  constructor(private getAccessToken: () => string) {}

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const token = this.getAccessToken()
    const res = await fetch(`${DRIVE_API}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
    })
    if (!res.ok) {
      const err = await res.text()
      throw new Error(`Drive API error ${res.status}: ${err}`)
    }
    if (res.status === 204) return undefined as T
    return res.json() as Promise<T>
  }

  // ── Folder ─────────────────────────────────────────────────────────────────

  async ensureFolder(): Promise<string> {
    if (this.folderId) return this.folderId

    const { files } = await this.request<{ files: Array<{ id: string }> }>(
      `/files?q=${encodeURIComponent(`name='${FOLDER_NAME}' and mimeType='${FOLDER_MIME}' and trashed=false`)}&fields=files(id)`,
    )

    if (files.length > 0) {
      this.folderId = files[0].id
    } else {
      const folder = await this.request<{ id: string }>('/files', {
        method: 'POST',
        body: JSON.stringify({ name: FOLDER_NAME, mimeType: FOLDER_MIME }),
      })
      this.folderId = folder.id
    }
    return this.folderId!
  }

  // ── File index ─────────────────────────────────────────────────────────────

  async loadFileIndex(): Promise<void> {
    const folderId = await this.ensureFolder()
    const { files } = await this.request<{ files: Array<{ id: string; name: string }> }>(
      `/files?q=${encodeURIComponent(`'${folderId}' in parents and trashed=false`)}&fields=files(id,name)`,
    )
    this.fileIndex.clear()
    for (const f of files) this.fileIndex.set(f.name, f.id)
  }

  // ── Read ───────────────────────────────────────────────────────────────────

  async read<T>(key: FileKey): Promise<T> {
    const name = FILE_NAMES[key]
    let fileId = this.fileIndex.get(name)

    if (!fileId) {
      // File doesn't exist yet — create it with defaults
      fileId = await this.createFile(key)
    }

    const token = this.getAccessToken()
    const res = await fetch(`${DRIVE_API}/files/${fileId}?alt=media`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`Failed to read ${name}: ${res.status}`)
    return res.json() as Promise<T>
  }

  // ── Write ──────────────────────────────────────────────────────────────────

  async write<T>(key: FileKey, data: T): Promise<void> {
    const name = FILE_NAMES[key]
    const fileId = this.fileIndex.get(name)

    if (!fileId) {
      await this.createFile(key, data)
      return
    }

    const token = this.getAccessToken()
    const res = await fetch(`${UPLOAD_API}/files/${fileId}?uploadType=media`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': JSON_MIME,
      },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error(`Failed to write ${name}: ${res.status}`)
  }

  // ── Create ─────────────────────────────────────────────────────────────────

  private async createFile<T = unknown>(key: FileKey, data?: T): Promise<string> {
    const name = FILE_NAMES[key]
    const folderId = await this.ensureFolder()
    const payload = data ?? DEFAULTS[key]

    const token = this.getAccessToken()

    // Multipart upload: metadata + body
    const metadata = JSON.stringify({ name, parents: [folderId], mimeType: JSON_MIME })
    const body = JSON.stringify(payload)
    const boundary = '-------pfs_boundary'

    const multipart = [
      `--${boundary}`,
      'Content-Type: application/json; charset=UTF-8',
      '',
      metadata,
      `--${boundary}`,
      `Content-Type: ${JSON_MIME}`,
      '',
      body,
      `--${boundary}--`,
    ].join('\r\n')

    const res = await fetch(`${UPLOAD_API}/files?uploadType=multipart&fields=id`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': `multipart/related; boundary=${boundary}`,
      },
      body: multipart,
    })
    if (!res.ok) throw new Error(`Failed to create ${name}: ${res.status}`)
    const { id } = await res.json() as { id: string }
    this.fileIndex.set(name, id)
    return id
  }
}

// ── Typed convenience wrappers ────────────────────────────────────────────────

export interface AccountsFile { accounts: Account[] }
export interface BlanketExpensesFile { blanketExpenses: BlanketExpense[] }
export interface SnapshotsFile { snapshots: Snapshot[] }
export interface LoansFile { loans: Loan[] }
export interface SettingsFile { settings: AppSettings }
export type { TransactionsFile, EquityFile }
