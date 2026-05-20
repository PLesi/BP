<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface Software { id: number; name: string }
interface Device { id: number; name: string }
interface TimeLimit { id: number; period: number; frequency: number }
interface InputLimit { id: number; min: number; max: number }
interface ConfigInput { id: number; type: string; name: string; workspace: string; input_limit: InputLimit | null }
interface ConfigOutput { id: number; type: string; name: string }
interface Config {
  id: number
  device_id: number
  port: string
  software: Software | null
  time_limit: TimeLimit | null
  output_path: string | null
  inputs: ConfigInput[]
  outputs: ConfigOutput[]
}

const configs = ref<Config[]>([])
const devices = ref<Device[]>([])
const softwareList = ref<Software[]>([])

const selected = ref<Config | null>(null)
const isNew = ref(false)
const isEditing = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Config form
const form = ref({
  device_id: '' as string | number,
  port: '',
  software_id: '' as string | number,
  output_path: '',
  has_time_limit: false,
  tl_period: '' as string | number,
  tl_frequency: '' as string | number,
})

// New input/output form
const newInput = ref({ type: '', name: '', workspace: 'inputs', has_limit: false, min: '', max: '' })
const newOutput = ref({ type: '', name: '' })
const inputError = ref<string | null>(null)
const outputError = ref<string | null>(null)

async function fetchAll() {
  const [cr, dr, sr] = await Promise.all([
    fetch('http://localhost:8000/configs'),
    fetch('http://localhost:8000/devices'),
    fetch('http://localhost:8000/software'),
  ])
  configs.value = await cr.json()
  devices.value = await dr.json()
  softwareList.value = await sr.json()
}

function deviceName(id: number) {
  return devices.value.find(d => d.id === id)?.name ?? `Device #${id}`
}

function selectConfig(cfg: Config) {
  selected.value = cfg
  isNew.value = false
  isEditing.value = false
  error.value = null
  success.value = null
  inputError.value = null
  outputError.value = null
  form.value = {
    device_id: cfg.device_id,
    port: cfg.port,
    software_id: cfg.software?.id ?? '',
    output_path: cfg.output_path ?? '',
    has_time_limit: !!cfg.time_limit,
    tl_period: cfg.time_limit?.period ?? '',
    tl_frequency: cfg.time_limit?.frequency ?? '',
  }
  newInput.value = { type: '', name: '', workspace: 'inputs', has_limit: false, min: '', max: '' }
  newOutput.value = { type: '', name: '' }
}

function clickNew() {
  selected.value = null
  isNew.value = true
  isEditing.value = true
  error.value = null
  success.value = null
  form.value = { device_id: '', port: '', software_id: '', output_path: '', has_time_limit: false, tl_period: '', tl_frequency: '' }
}

function cancel() {
  if (isNew.value) { isNew.value = false; isEditing.value = false }
  else if (selected.value) selectConfig(selected.value)
}

async function saveConfig() {
  if (!form.value.device_id) { error.value = 'Device is required.'; return }
  if (!form.value.port.trim()) { error.value = 'Port is required.'; return }
  if (form.value.has_time_limit && (!form.value.tl_period || !form.value.tl_frequency)) {
    error.value = 'Period and frequency are required when time limit is enabled.'; return
  }
  loading.value = true; error.value = null; success.value = null
  const payload: any = {
    device_id: Number(form.value.device_id),
    port: form.value.port.trim(),
    software_id: form.value.software_id !== '' ? Number(form.value.software_id) : null,
    output_path: form.value.output_path.trim() || null,
    time_limit: form.value.has_time_limit
      ? { period: Number(form.value.tl_period), frequency: Number(form.value.tl_frequency) }
      : null,
  }
  try {
    const url = isNew.value ? 'http://localhost:8000/configs' : `http://localhost:8000/configs/${selected.value!.id}`
    const res = await fetch(url, { method: isNew.value ? 'POST' : 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (!res.ok) { const d = await res.json(); throw new Error(d?.detail ?? `Error ${res.status}`) }
    const saved: Config = await res.json()
    await fetchAll()
    success.value = 'Config saved.'
    isNew.value = false; isEditing.value = false
    const fresh = configs.value.find(c => c.id === saved.id)
    if (fresh) selectConfig(fresh)
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

async function addInput() {
  if (!newInput.value.type.trim() || !newInput.value.name.trim()) { inputError.value = 'Type and name are required.'; return }
  inputError.value = null
  const payload: any = {
    config_id: selected.value!.id,
    type: newInput.value.type.trim(),
    name: newInput.value.name.trim(),    workspace: newInput.value.workspace,    input_limit: newInput.value.has_limit
      ? { min: Number(newInput.value.min), max: Number(newInput.value.max) }
      : null,
  }
  const res = await fetch('http://localhost:8000/inputs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  if (!res.ok) { const d = await res.json(); inputError.value = d?.detail ?? 'Error'; return }
  await fetchAll()
  const fresh = configs.value.find(c => c.id === selected.value!.id)
  if (fresh) selectConfig(fresh)
  newInput.value = { type: '', name: '', workspace: 'inputs', has_limit: false, min: '', max: '' }
}

async function deleteInput(id: number) {
  await fetch(`http://localhost:8000/inputs/${id}`, { method: 'DELETE' })
  await fetchAll()
  const fresh = configs.value.find(c => c.id === selected.value!.id)
  if (fresh) selectConfig(fresh)
}

async function addOutput() {
  if (!newOutput.value.type.trim() || !newOutput.value.name.trim()) { outputError.value = 'Type and name are required.'; return }
  outputError.value = null
  const payload = { config_id: selected.value!.id, type: newOutput.value.type.trim(), name: newOutput.value.name.trim() }
  const res = await fetch('http://localhost:8000/outputs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  if (!res.ok) { const d = await res.json(); outputError.value = d?.detail ?? 'Error'; return }
  await fetchAll()
  const fresh = configs.value.find(c => c.id === selected.value!.id)
  if (fresh) selectConfig(fresh)
  newOutput.value = { type: '', name: '' }
}

async function deleteOutput(id: number) {
  await fetch(`http://localhost:8000/outputs/${id}`, { method: 'DELETE' })
  await fetchAll()
  const fresh = configs.value.find(c => c.id === selected.value!.id)
  if (fresh) selectConfig(fresh)
}

onMounted(fetchAll)
</script>

<template>
  <div class="rounded-xl border border-zinc-700 bg-zinc-900 overflow-hidden flex h-[calc(100vh-130px)]">

    <!-- Left 25% -->
    <aside class="w-1/4 border-r border-zinc-700 flex flex-col">
      <div class="p-4 border-b border-zinc-700">
        <Button class="w-full bg-zinc-700 hover:bg-zinc-600 text-white" @click="clickNew">+ New Config</Button>
      </div>
      <nav class="flex-1 overflow-y-auto p-2">
        <ul class="space-y-0.5">
          <li v-if="configs.length === 0" class="text-zinc-500 text-sm p-3">No configs yet.</li>
          <li v-for="cfg in configs" :key="cfg.id">
            <button
              class="w-full text-left px-3 py-2 rounded-lg text-sm transition-colors"
              :class="selected?.id === cfg.id && !isNew ? 'bg-zinc-700 text-white' : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'"
              @click="selectConfig(cfg)"
            >
              <span class="font-medium">{{ deviceName(cfg.device_id) }}</span>
              <span class="block text-xs text-zinc-500 mt-0.5">{{ cfg.port }}</span>
            </button>
          </li>
        </ul>
      </nav>
    </aside>

    <!-- Right 75% -->
    <section class="flex-1 overflow-y-auto p-8">

      <div v-if="!selected && !isNew" class="flex items-center justify-center h-full text-zinc-500 text-sm">
        Select a config or click <span class="mx-1 text-zinc-300 font-medium">+ New Config</span>.
      </div>

      <div v-else class="max-w-2xl space-y-7">

        <!-- Header -->
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold text-white">
            {{ isNew ? 'New Config' : `Config — ${deviceName(selected!.device_id)}` }}
          </h2>
          <div class="flex gap-2">
            <template v-if="!isEditing">
              <Button variant="outline" class="border-zinc-600 text-zinc-300 hover:bg-zinc-800" @click="isEditing = true">Edit</Button>
            </template>
            <template v-else>
              <Button variant="outline" class="border-zinc-600 text-zinc-300 hover:bg-zinc-800" @click="cancel" :disabled="loading">Cancel</Button>
              <Button class="bg-white text-zinc-900 hover:bg-zinc-200" @click="saveConfig" :disabled="loading">{{ loading ? 'Saving...' : 'Save' }}</Button>
            </template>
          </div>
        </div>

        <!-- Config fields -->
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <Label class="text-zinc-400 text-sm">Device</Label>
            <select
              v-model="form.device_id"
              :disabled="!isEditing"
              class="w-full rounded-md bg-zinc-800 border border-zinc-700 text-white text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-default"
            >
              <option value="" disabled>Select device</option>
              <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-zinc-400 text-sm">Port</Label>
            <Input v-model="form.port" placeholder="/dev/ttyUSB0" :disabled="!isEditing" class="bg-zinc-800 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default" />
          </div>
          <div class="space-y-1.5">
            <Label class="text-zinc-400 text-sm">Software (optional)</Label>
            <select
              v-model="form.software_id"
              :disabled="!isEditing"
              class="w-full rounded-md bg-zinc-800 border border-zinc-700 text-white text-sm px-3 py-2 disabled:opacity-60 disabled:cursor-default"
            >
              <option value="">— None —</option>
              <option v-for="sw in softwareList" :key="sw.id" :value="sw.id">{{ sw.name }}</option>
            </select>
          </div>
          <div class="space-y-1.5">
            <Label class="text-zinc-400 text-sm">Output Path (optional)</Label>
            <Input v-model="form.output_path" placeholder="e.g. /data/out.txt" :disabled="!isEditing" class="bg-zinc-800 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default" />
          </div>
        </div>

        <!-- Time limit -->
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <input type="checkbox" id="has_tl" v-model="form.has_time_limit" :disabled="!isEditing" class="accent-white" />
            <label for="has_tl" class="text-zinc-400 text-sm">Enable Time Limit</label>
          </div>
          <div v-if="form.has_time_limit" class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Period (s)</Label>
              <Input type="number" v-model="form.tl_period" :disabled="!isEditing" class="bg-zinc-800 border-zinc-700 text-white disabled:opacity-60 disabled:cursor-default" />
            </div>
            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Frequency (Hz)</Label>
              <Input type="number" v-model="form.tl_frequency" :disabled="!isEditing" class="bg-zinc-800 border-zinc-700 text-white disabled:opacity-60 disabled:cursor-default" />
            </div>
          </div>
        </div>

        <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
        <p v-if="success" class="text-sm text-green-400">{{ success }}</p>

        <!-- Inputs — only when viewing existing config -->
        <div v-if="selected && !isNew" class="space-y-3">
          <h3 class="text-sm font-semibold text-zinc-300 uppercase tracking-wide border-t border-zinc-700 pt-4">Inputs</h3>
          <table v-if="selected.inputs.length" class="w-full text-sm text-zinc-300">
            <thead>
              <tr class="text-left text-zinc-500 text-xs uppercase">
                <th class="pb-2 pr-4">Name</th>
                <th class="pb-2 pr-4">Type</th>
                <th class="pb-2 pr-4">Workspace</th>
                <th class="pb-2 pr-4">Min</th>
                <th class="pb-2 pr-4">Max</th>
                <th class="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="inp in selected.inputs" :key="inp.id" class="border-t border-zinc-800">
                <td class="py-1.5 pr-4">{{ inp.name }}</td>
                <td class="py-1.5 pr-4 text-zinc-500">{{ inp.type }}</td>
                <td class="py-1.5 pr-4 text-zinc-500">{{ inp.workspace }}</td>
                <td class="py-1.5 pr-4 text-zinc-500">{{ inp.input_limit?.min ?? '—' }}</td>
                <td class="py-1.5 pr-4 text-zinc-500">{{ inp.input_limit?.max ?? '—' }}</td>
                <td class="py-1.5">
                  <button class="text-red-400 hover:text-red-300 text-xs" @click="deleteInput(inp.id)">Remove</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-zinc-500 text-sm">No inputs yet.</p>
          <!-- Add input -->
          <div class="bg-zinc-800 rounded-lg p-4 space-y-3">
            <p class="text-xs text-zinc-400 font-medium uppercase tracking-wide">Add Input</p>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Name</Label>
                <Input v-model="newInput.name" placeholder="e.g. temperature" class="bg-zinc-900 border-zinc-700 text-white text-sm placeholder:text-zinc-600 h-8" />
              </div>
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Type</Label>
                <select v-model="newInput.type" class="w-full rounded-md bg-zinc-900 border border-zinc-700 text-white text-sm px-3 h-8">
                  <option value="" disabled>Select type</option>
                  <option value="float">float</option>
                  <option value="int">int</option>
                  <option value="bool">bool</option>
                  <option value="string">string</option>
                </select>
              </div>
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Workspace</Label>
                <select v-model="newInput.workspace" class="w-full rounded-md bg-zinc-900 border border-zinc-700 text-white text-sm px-3 h-8">
                  <option value="inputs">inputs</option>
                  <option value="regparams">regparams</option>
                </select>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <input type="checkbox" id="has_il" v-model="newInput.has_limit" class="accent-white" />
              <label for="has_il" class="text-zinc-400 text-xs">Add limit (min/max)</label>
            </div>
            <div v-if="newInput.has_limit" class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Min</Label>
                <Input type="number" v-model="newInput.min" class="bg-zinc-900 border-zinc-700 text-white text-sm h-8" />
              </div>
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Max</Label>
                <Input type="number" v-model="newInput.max" class="bg-zinc-900 border-zinc-700 text-white text-sm h-8" />
              </div>
            </div>
            <p v-if="inputError" class="text-xs text-red-400">{{ inputError }}</p>
            <Button class="bg-zinc-600 hover:bg-zinc-500 text-white h-8 text-sm" @click="addInput">Add Input</Button>
          </div>
        </div>

        <!-- Outputs — only when viewing existing config -->
        <div v-if="selected && !isNew" class="space-y-3">
          <h3 class="text-sm font-semibold text-zinc-300 uppercase tracking-wide border-t border-zinc-700 pt-4">Outputs</h3>
          <table v-if="selected.outputs.length" class="w-full text-sm text-zinc-300">
            <thead>
              <tr class="text-left text-zinc-500 text-xs uppercase">
                <th class="pb-2 pr-4">Name</th>
                <th class="pb-2 pr-4">Type</th>
                <th class="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="out in selected.outputs" :key="out.id" class="border-t border-zinc-800">
                <td class="py-1.5 pr-4">{{ out.name }}</td>
                <td class="py-1.5 pr-4 text-zinc-500">{{ out.type }}</td>
                <td class="py-1.5">
                  <button class="text-red-400 hover:text-red-300 text-xs" @click="deleteOutput(out.id)">Remove</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-zinc-500 text-sm">No outputs yet.</p>
          <!-- Add output -->
          <div class="bg-zinc-800 rounded-lg p-4 space-y-3">
            <p class="text-xs text-zinc-400 font-medium uppercase tracking-wide">Add Output</p>
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Name</Label>
                <Input v-model="newOutput.name" placeholder="e.g. light_intensity" class="bg-zinc-900 border-zinc-700 text-white text-sm placeholder:text-zinc-600 h-8" />
              </div>
              <div class="space-y-1">
                <Label class="text-zinc-500 text-xs">Type</Label>
                <Input v-model="newOutput.type" placeholder="e.g. float" class="bg-zinc-900 border-zinc-700 text-white text-sm placeholder:text-zinc-600 h-8" />
              </div>
            </div>
            <p v-if="outputError" class="text-xs text-red-400">{{ outputError }}</p>
            <Button class="bg-zinc-600 hover:bg-zinc-500 text-white h-8 text-sm" @click="addOutput">Add Output</Button>
          </div>
        </div>

      </div>
    </section>

  </div>
</template>
