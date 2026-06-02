<script setup lang="ts">
import DeviceManager from './components/DeviceManager.vue'
import { adminApiKey, setAdminApiKey } from './lib/api'
</script>

<template>
  <div class="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
    <header class="px-8 py-5 border-b border-zinc-800 flex items-center justify-between gap-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-white">Experimental Server</h1>
        <p class="text-sm text-zinc-400 mt-0.5">Device management</p>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <label class="text-xs text-zinc-400 whitespace-nowrap">Admin API Key</label>
        <input
          type="password"
          :value="adminApiKey"
          @change="setAdminApiKey(($event.target as HTMLInputElement).value)"
          placeholder="Enter key…"
          class="w-56 rounded-md bg-zinc-800 border border-zinc-700 text-white text-sm px-3 py-1.5 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        />
      </div>
    </header>

    <main class="flex-1 p-6">
      <DeviceManager />
    </main>
  </div>
</template>
