import { useState, useMemo } from 'react'

export default function ObjectBrowser({ objects, loading, onSelect, documented }) {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('ALL')

  const types = useMemo(() => {
    const set = new Set(objects.map((o) => o.type))
    return ['ALL', ...Array.from(set).sort()]
  }, [objects])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return objects.filter((o) => {
      if (typeFilter !== 'ALL' && o.type !== typeFilter) return false
      const full = `${o.database}.${o.schema_name}.${o.name}`.toLowerCase()
      return full.includes(q)
    })
  }, [objects, search, typeFilter])

  const objectKey = (o) => `${o.database}.${o.schema_name}.${o.name}`

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-snow-600 border-t-transparent"></div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Search and filter */}
      <div className="space-y-3 border-b border-gray-200 p-4">
        <input
          type="text"
          placeholder="Search tables, views..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm placeholder-gray-400 shadow-sm focus:border-snow-500 focus:outline-none focus:ring-1 focus:ring-snow-500"
        />
        <div className="flex flex-wrap gap-1.5">
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                typeFilter === t
                  ? 'bg-snow-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {t === 'ALL' ? 'All' : formatType(t)}
            </button>
          ))}
        </div>
      </div>

      {/* Object list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="p-4 text-center text-sm text-gray-400">No objects found</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {filtered.map((obj) => {
              const key = objectKey(obj)
              const isDone = documented.has(key)
              return (
                <li key={key}>
                  <button
                    onClick={() => onSelect(obj)}
                    className="flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-gray-50"
                  >
                    <TypeBadge type={obj.type} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900">
                        {obj.name}
                      </p>
                      <p className="truncate text-xs text-gray-500">
                        {obj.database}.{obj.schema_name}
                      </p>
                    </div>
                    {isDone && (
                      <span className="mt-0.5 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        Done
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* Count */}
      <div className="border-t border-gray-200 px-4 py-2 text-xs text-gray-500">
        {filtered.length} of {objects.length} objects
        {documented.size > 0 && ` · ${documented.size} documented`}
      </div>
    </div>
  )
}

function TypeBadge({ type }) {
  const colors = {
    'BASE TABLE': 'bg-blue-100 text-blue-700',
    VIEW: 'bg-purple-100 text-purple-700',
    'MATERIALIZED VIEW': 'bg-indigo-100 text-indigo-700',
    'EXTERNAL TABLE': 'bg-amber-100 text-amber-700',
  }
  return (
    <span
      className={`mt-0.5 inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        colors[type] || 'bg-gray-100 text-gray-600'
      }`}
    >
      {formatType(type)}
    </span>
  )
}

function formatType(type) {
  return type
    .replace('BASE TABLE', 'TABLE')
    .replace('MATERIALIZED VIEW', 'MAT VIEW')
    .replace('EXTERNAL TABLE', 'EXT TABLE')
}
