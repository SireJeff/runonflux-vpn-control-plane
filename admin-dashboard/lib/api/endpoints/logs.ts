/**
 * Logs API Endpoints
 */
import { apiClient } from '../client'

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
export type LogSource = 'connection' | 'auth'

export interface LogEntry {
  id: number
  timestamp: string
  level: LogLevel
  source: LogSource
  message: string
  user_id?: number | null
  metadata?: Record<string, unknown>
}

export interface LogStats {
  total_today: number
  errors_today: number
  warnings_today: number
  most_common_source: string
}

export interface LogsListParams {
  level?: LogLevel
  source?: LogSource
  search?: string
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

function toCsv(logs: LogEntry[]): string {
  const header = ['id', 'timestamp', 'level', 'source', 'message', 'user_id']
  const rows = logs.map(log => [
    String(log.id),
    String(log.timestamp),
    String(log.level),
    String(log.source),
    JSON.stringify(log.message),
    log.user_id == null ? '' : String(log.user_id),
  ])
  return [header.join(','), ...rows.map(r => r.join(','))].join('\n')
}

export const logsApi = {
  listLogs: async (params?: LogsListParams): Promise<LogEntry[]> => {
    const response = await apiClient.get('/admin/logs', { params })
    return response.data
  },

  getLogStats: async (): Promise<LogStats> => {
    const response = await apiClient.get('/admin/logs/stats')
    return response.data
  },

  exportLogs: async (params?: LogsListParams): Promise<Blob> => {
    const logs = await logsApi.listLogs(params)
    const csv = toCsv(logs)
    return new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  },
}
