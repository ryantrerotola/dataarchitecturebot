const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res
}

export async function fetchObjects() {
  const res = await request('/objects/')
  return res.json()
}

export async function fetchColumns(database, schema, table) {
  const res = await request(
    `/objects/${encodeURIComponent(database)}/${encodeURIComponent(schema)}/${encodeURIComponent(table)}/columns`
  )
  return res.json()
}

export async function summarizeTable(objectName, transcripts) {
  const res = await request('/summarize/table', {
    method: 'POST',
    body: JSON.stringify({ object_name: objectName, transcripts }),
  })
  const data = await res.json()
  return data.summary
}

export async function summarizeColumn(objectName, columnName, transcript) {
  const res = await request('/summarize/column', {
    method: 'POST',
    body: JSON.stringify({
      object_name: objectName,
      column_name: columnName,
      transcript,
    }),
  })
  const data = await res.json()
  return data.summary
}

export async function exportAlation(tables) {
  const res = await request('/export/alation', {
    method: 'POST',
    body: JSON.stringify({ tables }),
  })
  return res.json()
}

export async function exportAlationCombined(tables) {
  const res = await fetch(`${BASE}/export/alation/combined`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tables }),
  })
  return res.blob()
}
