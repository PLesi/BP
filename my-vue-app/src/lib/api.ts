import { ref } from 'vue'

const STORAGE_KEY = 'admin_api_key'

export const adminApiKey = ref<string>(
  localStorage.getItem(STORAGE_KEY) ?? import.meta.env.VITE_ADMIN_API_KEY ?? ''
)

export function setAdminApiKey(key: string) {
  adminApiKey.value = key
  localStorage.setItem(STORAGE_KEY, key)
}

export function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  headers.set('X-API-Key', adminApiKey.value)
  return fetch(url, { ...init, headers })
}
