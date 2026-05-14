<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface Software {
  id: number
  name: string
}

const list = ref<Software[]>([])
const selected = ref<Software | null>(null)
const isNew = ref(false)
const isEditing = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const success = ref(false)
const name = ref('')

async function fetchAll() {
  const res = await fetch('http://localhost:8000/software')
  list.value = await res.json()
}

function select_(sw: Software) {
  selected.value = sw
  isNew.value = false
  isEditing.value = false
  error.value = null
  success.value = false
  name.value = sw.name
}

function clickNew() {
  selected.value = null
  isNew.value = true
  isEditing.value = true
  error.value = null
  success.value = false
  name.value = ''
}

function cancel() {
  if (isNew.value) { isNew.value = false; isEditing.value = false }
  else if (selected.value) select_(selected.value)
}

async function save() {
  if (!name.value.trim()) { error.value = 'Name is required.'; return }
  loading.value = true; error.value = null; success.value = false
  try {
    const url = isNew.value
      ? 'http://localhost:8000/software'
      : `http://localhost:8000/software/${selected.value!.id}`
    const res = await fetch(url, {
      method: isNew.value ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.value.trim() }),
    })
    if (!res.ok) { const d = await res.json(); throw new Error(d?.detail ?? `Error ${res.status}`) }
    const saved: Software = await res.json()
    await fetchAll()
    success.value = true; isNew.value = false; isEditing.value = false
    select_(saved)
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

onMounted(fetchAll)
</script>

<template>
  <div class="rounded-xl border border-zinc-700 bg-zinc-900 overflow-hidden flex h-[calc(100vh-130px)]">
    <!-- Left -->
    <aside class="w-1/4 border-r border-zinc-700 flex flex-col">
      <div class="p-4 border-b border-zinc-700">
        <Button class="w-full bg-zinc-700 hover:bg-zinc-600 text-white" @click="clickNew">+ New Software</Button>
      </div>
      <nav class="flex-1 overflow-y-auto p-2">
        <ul class="space-y-0.5">
          <li v-if="list.length === 0" class="text-zinc-500 text-sm p-3">No software yet.</li>
          <li v-for="sw in list" :key="sw.id">
            <button
              class="w-full text-left px-3 py-2 rounded-lg text-sm transition-colors"
              :class="selected?.id === sw.id && !isNew ? 'bg-zinc-700 text-white' : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'"
              @click="select_(sw)"
            >{{ sw.name }}</button>
          </li>
        </ul>
      </nav>
    </aside>

    <!-- Right -->
    <section class="flex-1 p-8 overflow-y-auto">
      <div v-if="!selected && !isNew" class="flex items-center justify-center h-full text-zinc-500 text-sm">
        Select software or click <span class="mx-1 text-zinc-300 font-medium">+ New Software</span>.
      </div>
      <div v-else class="max-w-sm space-y-5">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold text-white">{{ isNew ? 'New Software' : selected?.name }}</h2>
          <div class="flex gap-2">
            <template v-if="!isEditing">
              <Button variant="outline" class="border-zinc-600 text-zinc-300 hover:bg-zinc-800" @click="isEditing = true">Edit</Button>
            </template>
            <template v-else>
              <Button variant="outline" class="border-zinc-600 text-zinc-300 hover:bg-zinc-800" @click="cancel" :disabled="loading">Cancel</Button>
              <Button class="bg-white text-zinc-900 hover:bg-zinc-200" @click="save" :disabled="loading">{{ loading ? 'Saving...' : 'Save' }}</Button>
            </template>
          </div>
        </div>
        <div class="space-y-1.5">
          <Label class="text-zinc-400 text-sm">Name</Label>
          <Input v-model="name" placeholder="Software name" :disabled="!isEditing" class="bg-zinc-800 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default" />
        </div>
        <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
        <p v-if="success" class="text-sm text-green-400">Saved successfully.</p>
      </div>
    </section>
  </div>
</template>
