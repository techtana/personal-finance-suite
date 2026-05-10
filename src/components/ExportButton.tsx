import { useState } from 'react'
import { useAuthStore } from '../store/authStore'

export function ExportButton() {
  const { firestoreClient } = useAuthStore()
  const [exporting, setExporting] = useState(false)

  async function handleExport() {
    if (!firestoreClient) return
    setExporting(true)
    try {
      const data = await firestoreClient.exportAll()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `personal-finance-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="p-5 bg-white border border-[#d1d5db] rounded-xl">
      <div className="text-sm font-bold mb-1" style={{ color: '#0f172a' }}>Export Data</div>
      <div className="text-xs mb-3" style={{ color: '#5c6473' }}>
        Download all your data as a JSON file. You can use this as a backup or to migrate to another tool.
      </div>
      <button
        onClick={handleExport}
        disabled={exporting}
        className="px-4 py-2 rounded-lg text-sm font-semibold border border-[#d1d5db] bg-white hover:bg-[#f4f6f9] transition-colors disabled:opacity-50"
        style={{ color: '#0f172a' }}
      >
        {exporting ? 'Exporting…' : 'Download JSON'}
      </button>
    </div>
  )
}
