<script setup lang="ts">
import DeviceManager from './components/DeviceManager.vue'
</script>

<template>
  <div class="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
    <header class="px-8 py-5 border-b border-zinc-800">
      <h1 class="text-2xl font-semibold tracking-tight text-white">Experimental Server</h1>
      <p class="text-sm text-zinc-400 mt-0.5">Device management</p>
    </header>

    <main class="flex-1 p-6">
      <DeviceManager />
    </main>
  </div>
</template>
