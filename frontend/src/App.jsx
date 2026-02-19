import { useState, useEffect, useCallback } from 'react'
import ObjectBrowser from './components/ObjectBrowser'
import TableDescriber from './components/TableDescriber'
import ColumnDescriber from './components/ColumnDescriber'
import ReviewExport from './components/ReviewExport'
import { fetchObjects, fetchColumns } from './api/client'

/*
  Workflow stages:
  - browse:   User browses/selects a Snowflake object
  - describe: Voice-guided table description
  - columns:  Column-by-column voice descriptions
  - review:   Review all documented tables and export to Alation
*/

export default function App() {
  const [objects, setObjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Current workflow state
  const [stage, setStage] = useState('browse') // browse | describe | columns | review
  const [selectedObj, setSelectedObj] = useState(null)
  const [columns, setColumns] = useState([])
  const [tableDescription, setTableDescription] = useState('')

  // All documented tables: Map<key, TableDocumentation>
  const [documented, setDocumented] = useState(new Map())

  const loadObjects = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchObjects()
      setObjects(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadObjects()
  }, [loadObjects])

  const handleSelectObject = async (obj) => {
    setSelectedObj(obj)
    setStage('describe')
    try {
      const cols = await fetchColumns(obj.database, obj.schema_name, obj.name)
      setColumns(cols)
    } catch (err) {
      setError(`Failed to load columns: ${err.message}`)
    }
  }

  const handleTableDescribed = (description) => {
    setTableDescription(description)
    if (columns.length > 0) {
      setStage('columns')
    } else {
      // No columns (e.g., some views), save directly
      saveDocumentation(description, [])
    }
  }

  const handleColumnsComplete = (colDocs) => {
    saveDocumentation(tableDescription, colDocs)
  }

  const saveDocumentation = (desc, colDocs) => {
    const key = `${selectedObj.database}.${selectedObj.schema_name}.${selectedObj.name}`
    const doc = {
      database: selectedObj.database,
      schema_name: selectedObj.schema_name,
      table_name: selectedObj.name,
      table_description: desc,
      columns: colDocs,
    }
    setDocumented((prev) => new Map(prev).set(key, doc))
    setStage('browse')
    setSelectedObj(null)
    setTableDescription('')
    setColumns([])
  }

  const documentedKeys = new Set(documented.keys())

  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex shrink-0 items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-snow-600 text-white">
            <SnowflakeIcon />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-900">
              Metadata Documenter
            </h1>
            <p className="text-xs text-gray-500">
              Voice-powered documentation for Alation
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {documented.size > 0 && (
            <button
              onClick={() => setStage('review')}
              className="inline-flex items-center gap-1.5 rounded-lg border border-snow-200 bg-snow-50 px-3 py-1.5 text-xs font-medium text-snow-700 transition hover:bg-snow-100"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-snow-600 text-[10px] text-white">
                {documented.size}
              </span>
              Review & Export
            </button>
          )}
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-3 font-medium underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex min-h-0 flex-1">
        {/* Sidebar - object browser (always visible except in review) */}
        {stage !== 'review' && (
          <aside className="flex w-80 shrink-0 flex-col border-r border-gray-200 bg-white">
            <ObjectBrowser
              objects={objects}
              loading={loading}
              onSelect={handleSelectObject}
              documented={documentedKeys}
            />
          </aside>
        )}

        {/* Main panel */}
        <main className="flex-1 overflow-y-auto p-8">
          <div className="mx-auto max-w-2xl">
            {stage === 'browse' && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="rounded-2xl bg-white p-12 shadow-sm ring-1 ring-gray-100">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-snow-100">
                    <MicLargeIcon />
                  </div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Select a table to document
                  </h2>
                  <p className="mt-2 max-w-sm text-sm text-gray-500">
                    Choose a table or view from the sidebar, then use your voice
                    to describe it. Your descriptions will be summarized and
                    formatted for Alation upload.
                  </p>
                </div>
              </div>
            )}

            {stage === 'describe' && selectedObj && (
              <TableDescriber
                table={selectedObj}
                onComplete={handleTableDescribed}
              />
            )}

            {stage === 'columns' && selectedObj && (
              <ColumnDescriber
                table={selectedObj}
                columns={columns}
                onComplete={handleColumnsComplete}
              />
            )}

            {stage === 'review' && (
              <ReviewExport
                documented={documented}
                onBack={() => setStage('browse')}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function SnowflakeIcon() {
  return (
    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 2L12 22M2 12L22 12M4.93 4.93L19.07 19.07M19.07 4.93L4.93 19.07" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    </svg>
  )
}

function MicLargeIcon() {
  return (
    <svg className="h-8 w-8 text-snow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
    </svg>
  )
}
