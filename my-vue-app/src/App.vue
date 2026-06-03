<script setup lang="ts">
import { ref, onMounted } from 'vue'
import DeviceManager from './components/DeviceManager.vue'
import { adminApiKey, setAdminApiKey } from './lib/api'

const isDark = ref(true)

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

onMounted(() => {
  const saved = localStorage.getItem('theme')
  isDark.value = saved !== null ? saved === 'dark' : true
  document.documentElement.classList.toggle('dark', isDark.value)
})
</script>

<template>
  <div class="min-h-screen bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 flex flex-col">
    <header class="px-8 py-5 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">Experimental Server</h1>
        <p class="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">Device management</p>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <button
          @click="toggleTheme"
          class="rounded-md border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 px-2.5 py-1.5 text-sm transition-colors"
          :title="isDark ? 'Switch to light theme' : 'Switch to dark theme'"
        >
          {{ isDark ? '☀' : '🌙' }}
        </button>
        <label class="text-xs text-zinc-500 dark:text-zinc-400 whitespace-nowrap">Admin API Key</label>
        <input
          type="password"
          :value="adminApiKey"
          @change="setAdminApiKey(($event.target as HTMLInputElement).value)"
          placeholder="Enter key…"
          class="w-56 rounded-md bg-gray-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm px-3 py-1.5 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:focus:ring-zinc-500"
        />
      </div>
    </header>

    <main class="flex-1 p-6">
      <DeviceManager />
    </main>
  </div>
</template>
