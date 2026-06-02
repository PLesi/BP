const API_KEY = import.meta.env.VITE_ADMIN_API_KEY ?? ''

export function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  headers.set('X-API-Key', API_KEY)
  return fetch(url, { ...init, headers })
}
