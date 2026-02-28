import { useState, useRef, useCallback } from 'react'
import Card from '../components/Card'
import { api } from '../api'

type Stage = 'idle' | 'preparing' | 'prepared' | 'uploading' | 'uploaded' | 'running' | 'succeeded' | 'failed'

const STAGE_LABELS: Record<Stage, string> = {
  idle: 'Select CSV files to begin',
  preparing: 'Archiving old data & resetting tables...',
  prepared: 'Old data archived — ready to upload new files',
  uploading: 'Uploading to S3...',
  uploaded: 'Files uploaded — ready to run pipeline',
  running: 'Pipeline running...',
  succeeded: 'Pipeline completed successfully!',
  failed: 'An error occurred',
}

const STAGE_COLORS: Record<Stage, string> = {
  idle: 'text-gray-500',
  preparing: 'text-amber-600',
  prepared: 'text-brand-600',
  uploading: 'text-blue-600',
  uploaded: 'text-brand-600',
  running: 'text-blue-600',
  succeeded: 'text-green-600',
  failed: 'text-red-600',
}

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([])
  const [stage, setStage] = useState<Stage>('idle')
  const [error, setError] = useState('')
  const [uploadedKeys, setUploadedKeys] = useState<string[]>([])
  const [executionArn, setExecutionArn] = useState('')
  const [pipelineStatus, setPipelineStatus] = useState('')
  const [archiveInfo, setArchiveInfo] = useState<{ archived: number; cleared: Record<string, number>; path: string } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const handleFiles = useCallback((selected: FileList | null) => {
    if (!selected) return
    const csvFiles = Array.from(selected).filter(f => f.name.toLowerCase().endsWith('.csv'))
    if (csvFiles.length === 0) {
      setError('Please select CSV files only')
      return
    }
    setFiles(csvFiles)
    setError('')
    setStage('idle')
    setUploadedKeys([])
    setExecutionArn('')
    setPipelineStatus('')
    setArchiveInfo(null)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  // Step 1: Archive old data + reset DynamoDB
  const prepareAndUpload = async () => {
    setError('')
    setStage('preparing')

    try {
      // Archive old S3 data and clear DynamoDB tables
      const prep = await api.prepareForUpload()
      setArchiveInfo({
        archived: prep.archived_files,
        cleared: prep.cleared_tables,
        path: prep.archive_path,
      })
      setStage('prepared')

      // Immediately proceed to upload
      setStage('uploading')
      const keys: string[] = []

      for (const file of files) {
        const presign = await api.presignUpload(file.name)
        await api.uploadFileToS3(presign.upload_url, file)
        keys.push(presign.s3_key)
        setUploadedKeys(prev => [...prev, presign.s3_key])
      }
      setUploadedKeys(keys)
      setStage('uploaded')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
      setStage('failed')
    }
  }

  // Step 2: Trigger pipeline
  const triggerPipeline = async () => {
    setError('')
    setStage('running')
    try {
      const resp = await api.triggerPipeline()
      setExecutionArn(resp.execution_arn)
      setPipelineStatus(resp.status)

      // Poll for completion
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.pipelineStatus(resp.execution_arn)
          setPipelineStatus(status.status)
          if (status.status === 'SUCCEEDED') {
            setStage('succeeded')
            if (pollRef.current) clearInterval(pollRef.current)
          } else if (status.status === 'FAILED' || status.status === 'TIMED_OUT' || status.status === 'ABORTED') {
            setStage('failed')
            if (pollRef.current) clearInterval(pollRef.current)
          }
        } catch {
          // Keep polling
        }
      }, 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Trigger failed')
      setStage('failed')
    }
  }

  const reset = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    setFiles([])
    setStage('idle')
    setError('')
    setUploadedKeys([])
    setExecutionArn('')
    setPipelineStatus('')
    setArchiveInfo(null)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Data Upload</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload new CSV files. Old data is archived automatically before ingestion.
        </p>
      </div>

      {/* Status bar */}
      <div className={`text-sm font-medium ${STAGE_COLORS[stage]} flex items-center gap-2`}>
        {(stage === 'preparing' || stage === 'uploading' || stage === 'running') && (
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        {stage === 'succeeded' && <span>✓</span>}
        {stage === 'failed' && <span>✗</span>}
        {STAGE_LABELS[stage]}
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
      )}

      {/* Drop zone */}
      <Card title="Upload Files">
        <div
          onDragOver={e => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center cursor-pointer hover:border-brand-400 hover:bg-brand-50/30 transition-colors"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            multiple
            className="hidden"
            onChange={e => handleFiles(e.target.files)}
          />
          <div className="text-4xl mb-3">📁</div>
          <p className="text-gray-600 font-medium">Drop CSV files here or click to browse</p>
          <p className="text-xs text-gray-400 mt-1">Accepts .csv files · Multiple files supported</p>
        </div>
      </Card>

      {/* File list */}
      {files.length > 0 && (
        <Card title={`Selected Files (${files.length})`}>
          <div className="space-y-2">
            {files.map((f, i) => (
              <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-2">
                <div className="flex items-center gap-3">
                  <span className="text-lg">📄</span>
                  <div>
                    <div className="text-sm font-medium text-gray-800">{f.name}</div>
                    <div className="text-xs text-gray-400">{(f.size / 1024).toFixed(1)} KB</div>
                  </div>
                </div>
                {uploadedKeys[i] && (
                  <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">✓ Uploaded</span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        {stage === 'idle' && files.length > 0 && (
          <button
            onClick={prepareAndUpload}
            className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg font-medium text-sm transition-colors"
          >
            🔄 Archive Old Data & Upload {files.length} file{files.length > 1 ? 's' : ''}
          </button>
        )}

        {stage === 'uploaded' && (
          <button
            onClick={triggerPipeline}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition-colors"
          >
            ▶ Run Analytics Pipeline
          </button>
        )}

        {(stage === 'succeeded' || stage === 'failed') && (
          <button
            onClick={reset}
            className="px-6 py-2.5 bg-gray-600 hover:bg-gray-700 text-white rounded-lg font-medium text-sm transition-colors"
          >
            Upload New Data
          </button>
        )}
      </div>

      {/* Archive info */}
      {archiveInfo && (
        <Card title="Archive Summary">
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Files archived:</span>
              <span className="font-medium text-gray-800">{archiveInfo.archived}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Archive location:</span>
              <span className="font-mono text-xs text-gray-600">{archiveInfo.path}</span>
            </div>
            <div>
              <span className="text-gray-500">DynamoDB tables cleared:</span>
              <div className="mt-1 space-y-1">
                {Object.entries(archiveInfo.cleared).map(([table, count]) => (
                  <div key={table} className="flex items-center gap-2 text-xs ml-4">
                    <span className="font-mono text-gray-600">{table}</span>
                    <span className="text-gray-400">—</span>
                    <span className="text-amber-600 font-medium">{count} items deleted</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Pipeline details */}
      {executionArn && (
        <Card title="Pipeline Execution">
          <div className="text-xs font-mono text-gray-500 break-all mb-2">{executionArn}</div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-gray-600">Status:</span>
            <span className={`text-xs font-bold ${
              pipelineStatus === 'SUCCEEDED' ? 'text-green-600' :
              pipelineStatus === 'RUNNING' ? 'text-blue-600' :
              'text-red-600'
            }`}>
              {pipelineStatus}
            </span>
          </div>
        </Card>
      )}

      {/* Pipeline flow diagram */}
      <Card title="Pipeline Flow">
        <div className="flex items-center gap-2 text-xs text-gray-500 flex-wrap">
          <span className="bg-amber-100 text-amber-700 px-3 py-1.5 rounded-lg font-medium">Archive Old Data</span>
          <span>→</span>
          <span className="bg-red-100 text-red-700 px-3 py-1.5 rounded-lg font-medium">Reset DynamoDB</span>
          <span>→</span>
          <span className="bg-brand-100 text-brand-700 px-3 py-1.5 rounded-lg font-medium">CSV Upload</span>
          <span>→</span>
          <span className="bg-blue-100 text-blue-700 px-3 py-1.5 rounded-lg font-medium">S3 Bucket</span>
          <span>→</span>
          <span className="bg-purple-100 text-purple-700 px-3 py-1.5 rounded-lg font-medium">ETL Lambda</span>
          <span>→</span>
          <div className="flex flex-col gap-1">
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded font-medium">Forecast</span>
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded font-medium">Combo</span>
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded font-medium">Expansion</span>
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded font-medium">Staffing</span>
            <span className="bg-green-100 text-green-700 px-3 py-1 rounded font-medium">Growth</span>
          </div>
          <span>→</span>
          <span className="bg-yellow-100 text-yellow-700 px-3 py-1.5 rounded-lg font-medium">DynamoDB</span>
          <span>→</span>
          <span className="bg-brand-100 text-brand-700 px-3 py-1.5 rounded-lg font-medium">Dashboard</span>
        </div>
      </Card>
    </div>
  )
}
