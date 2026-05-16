<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface Software {
  id: number
  name: string
}

interface TimeLimit {
  id: number
  period: number
  frequency: number
}

interface InputLimit {
  id: number
  min: number
  max: number
}

interface ConfigInput {
  id: number
  type: string
  name: string
  input_limit: InputLimit | null
}

interface ConfigOutput {
  id: number
  type: string
  name: string
}

interface PendingInput {
  name: string
  type: string
  input_limit: { min: number; max: number } | null
}

interface PendingOutput {
  name: string
  type: string
}

interface DeviceConfig {
  id: number
  device_id: number
  port: string
  output_path: string | null
  software: Software | null
  time_limit: TimeLimit | null
  inputs: ConfigInput[]
  outputs: ConfigOutput[]
}

interface Device {
  id: number
  name: string
  slx_model: string | null
  device_type: string | null
  maintenance_start: string | null
  maintenance_end: string | null
  config: DeviceConfig | null
}

const devices = ref<Device[]>([])
const softwareList = ref<Software[]>([])
const selected = ref<Device | null>(null)
const isNew = ref(false)
const isEditing = ref(false)
const loading = ref(false)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)
const ioError = ref<string | null>(null)
const ioSuccess = ref<string | null>(null)
const pendingInputs = ref<PendingInput[]>([])
const pendingOutputs = ref<PendingOutput[]>([])
const showDeleteModal = ref(false)
const deleteConfirmText = ref('')

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const NONE_SOFTWARE_VALUE = '__none__'
const OTHER_SOFTWARE_VALUE = '__other__'

const form = ref({
  name: '',
  slx_model: '',
  device_type: '',
  maintenance_start: '',
  maintenance_end: '',
  port: '',
  output_path: '',
  time_limit_enabled: false,
  period: '',
  frequency: '',
  software_choice: NONE_SOFTWARE_VALUE,
  software_other_name: '',
})

const inputForm = ref({
  name: '',
  type: '',
  limit_enabled: false,
  min: '',
  max: '',
})

const outputForm = ref({
  name: '',
  type: '',
})

async function fetchDevices() {
  const res = await fetch(`${API_BASE}/devices`)
  if (!res.ok) {
    throw new Error(`Failed to fetch devices (${res.status})`)
  }
  devices.value = await res.json()
}

async function fetchSoftware() {
  const res = await fetch(`${API_BASE}/software`)
  if (!res.ok) {
    throw new Error(`Failed to fetch software (${res.status})`)
  }
  softwareList.value = await res.json()
}

async function fetchAll() {
  try {
    await Promise.all([fetchDevices(), fetchSoftware()])
  } catch (e) {
    console.error(e)
    saveError.value = 'Could not load devices/software list.'
  }
}

function selectDevice(device: Device) {
  selected.value = device
  isNew.value = false
  isEditing.value = false
  saveError.value = null
  saveSuccess.value = false
  ioError.value = null
  ioSuccess.value = null
  form.value = {
    name: device.name,
    slx_model: device.slx_model ?? '',
    device_type: device.device_type ?? '',
    maintenance_start: device.maintenance_start ? device.maintenance_start.slice(0, 5) : '',
    maintenance_end: device.maintenance_end ? device.maintenance_end.slice(0, 5) : '',
    port: device.config?.port ?? '',
    output_path: device.config?.output_path ?? '',
    time_limit_enabled: !!device.config?.time_limit,
    period: device.config?.time_limit ? String(device.config.time_limit.period) : '',
    frequency: device.config?.time_limit ? String(device.config.time_limit.frequency) : '',
    software_choice: device.config?.software?.id
      ? String(device.config.software.id)
      : NONE_SOFTWARE_VALUE,
    software_other_name: '',
  }
  inputForm.value = { name: '', type: '', limit_enabled: false, min: '', max: '' }
  outputForm.value = { name: '', type: '' }
  pendingInputs.value = []
  pendingOutputs.value = []
}

function clickNew() {
  selected.value = null
  isNew.value = true
  isEditing.value = true
  saveError.value = null
  saveSuccess.value = false
  ioError.value = null
  ioSuccess.value = null
  form.value = {
    name: '',
    slx_model: '',
    device_type: '',
    maintenance_start: '',
    maintenance_end: '',
    port: '',
    output_path: '',
    time_limit_enabled: false,
    period: '',
    frequency: '',
    software_choice: NONE_SOFTWARE_VALUE,
    software_other_name: '',
  }
  inputForm.value = { name: '', type: '', limit_enabled: false, min: '', max: '' }
  outputForm.value = { name: '', type: '' }
}

function cancelEdit() {
  if (isNew.value) {
    isNew.value = false
    isEditing.value = false
    pendingInputs.value = []
    pendingOutputs.value = []
  } else if (selected.value) {
    selectDevice(selected.value)
  }
}

async function ensureSoftwareId(): Promise<number | null> {
  if (form.value.software_choice === NONE_SOFTWARE_VALUE) {
    return null
  }

  if (form.value.software_choice !== OTHER_SOFTWARE_VALUE) {
    return Number(form.value.software_choice)
  }

  const newName = form.value.software_other_name.trim()
  if (!newName) {
    throw new Error('Enter software name when selecting Other.')
  }

  const existing = softwareList.value.find((s) => s.name.toLowerCase() === newName.toLowerCase())
  if (existing) {
    return existing.id
  }

  const createRes = await fetch(`${API_BASE}/software`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newName }),
  })
  if (!createRes.ok) {
    const data = await createRes.json()
    throw new Error(data?.detail ?? `Software create failed (${createRes.status})`)
  }
  const created = await createRes.json()
  await fetchSoftware()
  return created.id
}

async function upsertConfig(deviceId: number): Promise<number | null> {
  if (!form.value.port.trim()) {
    return null
  }

  if (form.value.time_limit_enabled && (!form.value.period || !form.value.frequency)) {
    throw new Error('Fill period and frequency when time limit is enabled.')
  }

  const softwareId = await ensureSoftwareId()
  const configPayload = {
    device_id: deviceId,
    port: form.value.port.trim(),
    software_id: softwareId,
    output_path: form.value.output_path.trim() || null,
    time_limit: form.value.time_limit_enabled
      ? {
          period: Number(form.value.period),
          frequency: Number(form.value.frequency),
        }
      : null,
  }

  const configId = selected.value?.config?.id
  const method = configId ? 'PATCH' : 'POST'
  const url = configId
    ? `${API_BASE}/configs/${configId}`
    : `${API_BASE}/configs`

  const configRes = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(configPayload),
  })

  if (!configRes.ok) {
    const data = await configRes.json()
    throw new Error(data?.detail ?? `Config save failed (${configRes.status})`)
  }

  const savedConfig = await configRes.json()
  return savedConfig.id ?? null
}

async function addInput() {
  ioError.value = null
  ioSuccess.value = null
  if (!inputForm.value.name.trim() || !inputForm.value.type.trim()) {
    ioError.value = 'Input name and type are required.'
    return
  }
  if (inputForm.value.limit_enabled && (!inputForm.value.min || !inputForm.value.max)) {
    ioError.value = 'Input min and max are required when limit is enabled.'
    return
  }

  pendingInputs.value.push({
    name: inputForm.value.name.trim(),
    type: inputForm.value.type.trim(),
    input_limit: inputForm.value.limit_enabled
      ? { min: Number(inputForm.value.min), max: Number(inputForm.value.max) }
      : null,
  })

  inputForm.value = { name: '', type: '', limit_enabled: false, min: '', max: '' }
  ioSuccess.value = 'Input queued. It will be saved with Save.'
}

function removePendingInput(index: number) {
  pendingInputs.value.splice(index, 1)
}

async function removeInput(inputId: number) {
  ioError.value = null
  ioSuccess.value = null
  const res = await fetch(`${API_BASE}/inputs/${inputId}`, { method: 'DELETE' })
  if (!res.ok) {
    ioError.value = `Input delete failed (${res.status})`
    return
  }
  if (selected.value) {
    await fetchDevices()
    const refreshed = devices.value.find((d) => d.id === selected.value!.id)
    if (refreshed) {
      selectDevice(refreshed)
      isEditing.value = true
    }
  }
  ioSuccess.value = 'Input removed.'
}

async function addOutput() {
  ioError.value = null
  ioSuccess.value = null
  if (!outputForm.value.name.trim() || !outputForm.value.type.trim()) {
    ioError.value = 'Output name and type are required.'
    return
  }

  pendingOutputs.value.push({
    name: outputForm.value.name.trim(),
    type: outputForm.value.type.trim(),
  })

  outputForm.value = { name: '', type: '' }
  ioSuccess.value = 'Output queued. It will be saved with Save.'
}

function removePendingOutput(index: number) {
  pendingOutputs.value.splice(index, 1)
}

async function flushPendingIo(configId: number) {
  for (const inp of pendingInputs.value) {
    const res = await fetch(`${API_BASE}/inputs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config_id: configId,
        name: inp.name,
        type: inp.type,
        input_limit: inp.input_limit,
      }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data?.detail ?? `Input create failed (${res.status})`)
    }
  }

  for (const out of pendingOutputs.value) {
    const res = await fetch(`${API_BASE}/outputs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config_id: configId,
        name: out.name,
        type: out.type,
      }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data?.detail ?? `Output create failed (${res.status})`)
    }
  }
}

async function removeOutput(outputId: number) {
  ioError.value = null
  ioSuccess.value = null
  const res = await fetch(`${API_BASE}/outputs/${outputId}`, { method: 'DELETE' })
  if (!res.ok) {
    ioError.value = `Output delete failed (${res.status})`
    return
  }
  if (selected.value) {
    await fetchDevices()
    const refreshed = devices.value.find((d) => d.id === selected.value!.id)
    if (refreshed) {
      selectDevice(refreshed)
      isEditing.value = true
    }
  }
  ioSuccess.value = 'Output removed.'
}

async function createTestDevice() {
  const n = devices.value.length + 1
  const testName = `udaq ${n}`
  saveError.value = null
  ioError.value = null
  ioSuccess.value = null

  try {
    const devRes = await fetch(`${API_BASE}/devices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: testName,
        slx_model: 'PI_RED.slx',
        device_type: 'controller',
        maintenance_start: null,
        maintenance_end: null,
      }),
    })
    if (!devRes.ok) {
      const data = await devRes.json().catch(() => ({}))
      throw new Error(data?.detail ?? `Device create failed (${devRes.status})`)
    }

    const createdDevice: Device = await devRes.json()

    const configRes = await fetch(`${API_BASE}/configs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: createdDevice.id,
        port: '/dev/ttyUSB0',
        output_path: 'out.txt',
        software_id: null,
        time_limit: {
          period: 60,
          frequency: 10,
        },
      }),
    })
    if (!configRes.ok) {
      const data = await configRes.json().catch(() => ({}))
      throw new Error(data?.detail ?? `Config create failed (${configRes.status})`)
    }

    const cfg = await configRes.json()
    const configId = cfg.id as number

    const inputs = [
      { name: 'bulb', type: 'number', input_limit: { min: 0, max: 100 } },
      { name: 'fan', type: 'number', input_limit: { min: 0, max: 100 } },
      { name: 'led', type: 'number', input_limit: { min: 0, max: 100 } },
      { name: 'reg_signal', type: 'string', input_limit: null },
      { name: 'reg_target', type: 'number', input_limit: null },
      { name: 'Kc', type: 'number', input_limit: null },
      { name: 'Ti', type: 'number', input_limit: null },
      { name: 'U_min', type: 'number', input_limit: null },
      { name: 'U_max', type: 'number', input_limit: null },
    ]

    for (const inputDef of inputs) {
      const inputRes = await fetch(`${API_BASE}/inputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_id: configId,
          name: inputDef.name,
          type: inputDef.type,
          input_limit: inputDef.input_limit,
        }),
      })
      if (!inputRes.ok) {
        const data = await inputRes.json().catch(() => ({}))
        throw new Error(data?.detail ?? `Input '${inputDef.name}' create failed (${inputRes.status})`)
      }
    }

    const outputs = [
      { name: 'reg_output', type: 'number' },
      { name: 'light_intensity', type: 'number' },
    ]

    for (const outputDef of outputs) {
      const outputRes = await fetch(`${API_BASE}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_id: configId,
          name: outputDef.name,
          type: outputDef.type,
        }),
      })
      if (!outputRes.ok) {
        const data = await outputRes.json().catch(() => ({}))
        throw new Error(data?.detail ?? `Output '${outputDef.name}' create failed (${outputRes.status})`)
      }
    }

    await fetchDevices()
    const created = devices.value.find((d) => d.id === createdDevice.id)
    if (created) selectDevice(created)
    ioSuccess.value = 'Quick test device created with config, inputs and outputs.'
  } catch (e: any) {
    saveError.value = e.message
  }
}

async function deleteDevice() {
  if (!selected.value) return
  loading.value = true
  saveError.value = null
  showDeleteModal.value = false
  deleteConfirmText.value = ''
  try {
    const res = await fetch(`${API_BASE}/devices/${selected.value.id}`, { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data?.detail ?? `Delete failed (${res.status})`)
    }
    selected.value = null
    isEditing.value = false
    isNew.value = false
    await fetchDevices()
  } catch (e: any) {
    saveError.value = e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name.trim()) {
    saveError.value = 'Name is required.'
    return
  }
  if (!form.value.slx_model.trim()) {
    saveError.value = 'SLX model is required.'
    return
  }

  loading.value = true
  saveError.value = null
  saveSuccess.value = false

  const payload = {
    name: form.value.name.trim(),
    slx_model: form.value.slx_model.trim(),
    device_type: form.value.device_type.trim() || null,
    maintenance_start: form.value.maintenance_start || null,
    maintenance_end: form.value.maintenance_end || null,
  }

  try {
    let res: Response
    if (isNew.value) {
      res = await fetch(`${API_BASE}/devices`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } else {
      res = await fetch(`${API_BASE}/devices/${selected.value!.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    }

    if (!res.ok) {
      const data = await res.json()
      throw new Error(data?.detail ?? `Device save failed (${res.status})`)
    }

    const saved: Device = await res.json()
    const configId = await upsertConfig(saved.id)
    if ((pendingInputs.value.length > 0 || pendingOutputs.value.length > 0) && !configId) {
      throw new Error('Port is required to save queued inputs/outputs.')
    }
    if (configId) {
      await flushPendingIo(configId)
    }

    await fetchDevices()

    const refreshed = devices.value.find((d) => d.id === saved.id)
    if (refreshed) {
      selectDevice(refreshed)
    }

    pendingInputs.value = []
    pendingOutputs.value = []

    saveSuccess.value = true
    isNew.value = false
    isEditing.value = false
  } catch (e: any) {
    saveError.value = e.message
  } finally {
    loading.value = false
  }
}

const sidebarOpen = ref(false)

onMounted(fetchAll)
</script>

<template>
  <div class="rounded-2xl border border-zinc-800 bg-zinc-900/80 shadow-[0_0_0_1px_rgba(59,130,246,0.08)] overflow-hidden flex flex-col md:flex-row h-[calc(100vh-140px)]">
    <!-- Mobile topbar -->
    <div class="md:hidden flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-950/70">
      <span class="text-zinc-300 text-sm font-medium">Devices</span>
      <button
        class="text-zinc-400 hover:text-white text-xs border border-zinc-700 rounded px-2 py-1"
        @click="sidebarOpen = !sidebarOpen"
      >
        {{ sidebarOpen ? 'Hide' : 'Show list' }}
      </button>
    </div>

    <aside
      class="border-r border-zinc-800 flex flex-col bg-zinc-950/70 md:w-1/4"
      :class="sidebarOpen ? 'flex' : 'hidden md:flex'"
    >
      <div class="p-4 border-b border-zinc-800 space-y-2">
        <Button class="w-full bg-blue-600 hover:bg-blue-500 text-white" @click="clickNew">
          + New Device
        </Button>
        <Button class="w-full bg-zinc-700 hover:bg-zinc-600 text-zinc-300 text-xs" @click="createTestDevice">
          ⚡ Quick Test Device
        </Button>
      </div>
      <nav class="flex-1 overflow-y-auto p-2">
        <ul class="space-y-1">
          <li v-if="devices.length === 0" class="text-zinc-500 text-sm p-3">
            No devices yet.
          </li>
          <li v-for="device in devices" :key="device.id">
            <button
              class="w-full text-left px-3 py-2 rounded-lg text-sm transition-colors border border-transparent"
              :class="selected?.id === device.id && !isNew
                ? 'bg-blue-600/20 border-blue-500/40 text-blue-100'
                : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'"
              @click="selectDevice(device)"
            >
              {{ device.name }}
              <span v-if="device.device_type" class="ml-1 text-zinc-500 text-xs">({{ device.device_type }})</span>
            </button>
          </li>
        </ul>
      </nav>
    </aside>

    <section class="flex-1 p-8 overflow-y-auto">
      <div v-if="!selected && !isNew" class="flex items-center justify-center h-full text-zinc-500 text-sm">
        Select a device or click <span class="mx-1 text-blue-300 font-medium cursor-pointer hover:underline" @click="clickNew">+ New Device</span>.
      </div>

      <div v-else class="max-w-2xl space-y-6">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-semibold text-white">
            {{ isNew ? 'New Device' : selected?.name }}
          </h2>
          <div class="flex gap-2">
            <template v-if="!isEditing">
              <Button
                class="bg-blue-600 text-white hover:bg-blue-500"
                @click="isEditing = true"
              >
                Edit
              </Button>
              <Button
                v-if="!isNew"
                class="bg-red-600 text-white hover:bg-red-500"
                @click="showDeleteModal = true; deleteConfirmText = ''"
                :disabled="loading"
              >
                Delete
              </Button>
            </template>
            <template v-else>
              <Button
                variant="outline"
                class="border-zinc-600 bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
                @click="cancelEdit"
                :disabled="loading"
              >
                Cancel
              </Button>
              <Button class="bg-blue-600 text-white hover:bg-blue-500" @click="save" :disabled="loading">
                {{ loading ? 'Saving...' : 'Save' }}
              </Button>
            </template>
          </div>
        </div>

        <div class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4">
          <h3 class="text-sm font-semibold text-blue-300 uppercase tracking-wide">Device Info</h3>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5 col-span-2">
              <Label class="text-zinc-400 text-sm">Name</Label>
              <Input
                v-model="form.name"
                placeholder="Device name"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="space-y-1.5 col-span-2">
              <Label class="text-zinc-400 text-sm">SLX Model</Label>
              <Input
                v-model="form.slx_model"
                placeholder="e.g. MyModel.slx"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="space-y-1.5 col-span-2">
              <Label class="text-zinc-400 text-sm">Device Type</Label>
              <Input
                v-model="form.device_type"
                placeholder="e.g. sensor, actuator"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Maintenance Start</Label>
              <Input
                type="time"
                v-model="form.maintenance_start"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white disabled:opacity-60 disabled:cursor-default"
              />
            </div>
            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Maintenance End</Label>
              <Input
                type="time"
                v-model="form.maintenance_end"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white disabled:opacity-60 disabled:cursor-default"
              />
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4">
          <h3 class="text-sm font-semibold text-blue-300 uppercase tracking-wide">Configuration</h3>

          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Port</Label>
              <Input
                v-model="form.port"
                placeholder="/dev/ttyUSB0"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="space-y-1.5">
              <Label class="text-zinc-400 text-sm">Output Path</Label>
              <Input
                v-model="form.output_path"
                placeholder="Optional"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="space-y-1.5 col-span-2">
              <Label class="text-zinc-400 text-sm">Software</Label>
              <Select v-model="form.software_choice" :disabled="!isEditing">
                <SelectTrigger class="bg-zinc-900 border-zinc-700 text-white">
                  <SelectValue placeholder="Select software" />
                </SelectTrigger>
                <SelectContent class="max-h-60 overflow-y-auto bg-zinc-900 border-zinc-700 text-white">
                  <SelectItem :value="NONE_SOFTWARE_VALUE">None</SelectItem>
                  <SelectItem v-for="sw in softwareList" :key="sw.id" :value="String(sw.id)">
                    {{ sw.name }}
                  </SelectItem>
                  <SelectItem :value="OTHER_SOFTWARE_VALUE">Other...</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div v-if="form.software_choice === OTHER_SOFTWARE_VALUE" class="space-y-1.5 col-span-2">
              <Label class="text-zinc-400 text-sm">New Software Name</Label>
              <Input
                v-model="form.software_other_name"
                placeholder="Type software name"
                :disabled="!isEditing"
                class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
              />
            </div>

            <div class="col-span-2 pt-2 border-t border-zinc-800">
              <div class="flex items-center gap-2 mb-3">
                <input
                  id="time-limit-enabled"
                  v-model="form.time_limit_enabled"
                  type="checkbox"
                  :disabled="!isEditing"
                  class="accent-blue-500"
                >
                <Label for="time-limit-enabled" class="text-zinc-300 text-sm">Enable Time Limit</Label>
              </div>
              <div v-if="form.time_limit_enabled" class="grid grid-cols-2 gap-4">
                <div class="space-y-1.5">
                  <Label class="text-zinc-400 text-sm">Period</Label>
                  <Input
                    v-model="form.period"
                    type="number"
                    min="0"
                    placeholder="e.g. 60"
                    :disabled="!isEditing"
                    class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
                  />
                </div>
                <div class="space-y-1.5">
                  <Label class="text-zinc-400 text-sm">Frequency</Label>
                  <Input
                    v-model="form.frequency"
                    type="number"
                    min="0"
                    placeholder="e.g. 5"
                    :disabled="!isEditing"
                    class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500 disabled:opacity-60 disabled:cursor-default"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4">
          <h3 class="text-sm font-semibold text-blue-300 uppercase tracking-wide">Inputs</h3>

          <div v-if="selected?.config?.inputs?.length" class="space-y-2">
            <div
              v-for="inp in selected.config.inputs"
              :key="inp.id"
              class="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2"
            >
              <div class="text-sm text-zinc-200">
                <span class="font-medium">{{ inp.name }}</span>
                <span class="text-zinc-500"> ({{ inp.type }})</span>
                <span v-if="inp.input_limit" class="text-zinc-500"> [{{ inp.input_limit.min }} - {{ inp.input_limit.max }}]</span>
              </div>
              <Button
                v-if="isEditing"
                variant="outline"
                class="h-8 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                @click="removeInput(inp.id)"
              >
                Remove
              </Button>
            </div>
          </div>
          <p v-else class="text-sm text-zinc-500">No inputs yet.</p>

          <div v-if="isEditing" class="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Input Name</Label>
                <Input
                  v-model="inputForm.name"
                  placeholder="e.g. fan"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Input Type</Label>
                <Input
                  v-model="inputForm.type"
                  placeholder="e.g. float"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
            </div>

            <div class="flex items-center gap-2">
              <input id="input-limit-enabled" v-model="inputForm.limit_enabled" type="checkbox" class="accent-blue-500">
              <Label for="input-limit-enabled" class="text-zinc-300 text-sm">Add input limit</Label>
            </div>

            <div v-if="inputForm.limit_enabled" class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Min</Label>
                <Input
                  v-model="inputForm.min"
                  type="number"
                  placeholder="e.g. 0"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Max</Label>
                <Input
                  v-model="inputForm.max"
                  type="number"
                  placeholder="e.g. 100"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
            </div>

            <Button class="bg-blue-600 text-white hover:bg-blue-500" @click="addInput">Add Input</Button>
            <p class="text-xs text-zinc-500">Input is queued and saved when you press Save.</p>
          </div>
        </div>

        <div v-if="pendingInputs.length" class="rounded-lg border border-dashed border-blue-500/40 bg-blue-500/5 p-4 space-y-2">
          <p class="text-xs uppercase tracking-wide text-blue-300 font-semibold">Queued Inputs</p>
          <div
            v-for="(inp, index) in pendingInputs"
            :key="`${inp.name}-${inp.type}-${index}`"
            class="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2"
          >
            <div class="text-sm text-zinc-200">
              <span class="font-medium">{{ inp.name }}</span>
              <span class="text-zinc-500"> ({{ inp.type }})</span>
              <span v-if="inp.input_limit" class="text-zinc-500"> [{{ inp.input_limit.min }} - {{ inp.input_limit.max }}]</span>
              <span class="ml-2 text-blue-300 text-xs">pending</span>
            </div>
            <Button variant="outline" class="h-8 border-zinc-700 text-zinc-300 hover:bg-zinc-800" @click="removePendingInput(index)">
              Remove
            </Button>
          </div>
        </div>

        <div class="rounded-xl border border-zinc-800 bg-zinc-950/50 p-5 space-y-4">
          <h3 class="text-sm font-semibold text-blue-300 uppercase tracking-wide">Outputs</h3>

          <div v-if="selected?.config?.outputs?.length" class="space-y-2">
            <div
              v-for="out in selected.config.outputs"
              :key="out.id"
              class="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2"
            >
              <div class="text-sm text-zinc-200">
                <span class="font-medium">{{ out.name }}</span>
                <span class="text-zinc-500"> ({{ out.type }})</span>
              </div>
              <Button
                v-if="isEditing"
                variant="outline"
                class="h-8 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                @click="removeOutput(out.id)"
              >
                Remove
              </Button>
            </div>
          </div>
          <p v-else class="text-sm text-zinc-500">No outputs yet.</p>

          <div v-if="isEditing" class="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Output Name</Label>
                <Input
                  v-model="outputForm.name"
                  placeholder="e.g. light_intensity"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
              <div class="space-y-1.5">
                <Label class="text-zinc-400 text-sm">Output Type</Label>
                <Input
                  v-model="outputForm.type"
                  placeholder="e.g. float"
                  class="bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-500"
                />
              </div>
            </div>

            <Button class="bg-blue-600 text-white hover:bg-blue-500" @click="addOutput">Add Output</Button>
            <p class="text-xs text-zinc-500">Output is queued and saved when you press Save.</p>
          </div>
        </div>

        <div v-if="pendingOutputs.length" class="rounded-lg border border-dashed border-blue-500/40 bg-blue-500/5 p-4 space-y-2">
          <p class="text-xs uppercase tracking-wide text-blue-300 font-semibold">Queued Outputs</p>
          <div
            v-for="(out, index) in pendingOutputs"
            :key="`${out.name}-${out.type}-${index}`"
            class="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2"
          >
            <div class="text-sm text-zinc-200">
              <span class="font-medium">{{ out.name }}</span>
              <span class="text-zinc-500"> ({{ out.type }})</span>
              <span class="ml-2 text-blue-300 text-xs">pending</span>
            </div>
            <Button variant="outline" class="h-8 border-zinc-700 text-zinc-300 hover:bg-zinc-800" @click="removePendingOutput(index)">
              Remove
            </Button>
          </div>
        </div>

        <p v-if="saveError" class="text-sm text-red-400">{{ saveError }}</p>
        <p v-if="saveSuccess" class="text-sm text-blue-300">Saved successfully.</p>
        <p v-if="ioError" class="text-sm text-red-400">{{ ioError }}</p>
        <p v-if="ioSuccess" class="text-sm text-blue-300">{{ ioSuccess }}</p>
      </div>
    </section>
  </div>

  <!-- Delete confirmation modal -->
  <Teleport to="body">
    <div
      v-if="showDeleteModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      @click.self="showDeleteModal = false"
    >
      <div class="w-full max-w-md rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl space-y-5">
        <h3 class="text-lg font-semibold text-white">Delete Device</h3>
        <p class="text-sm text-zinc-400">
          This will permanently delete
          <span class="font-semibold text-white">{{ selected?.name }}</span>
          and all its configuration, inputs, and outputs.
        </p>
        <p class="text-sm text-zinc-400">
          Type <span class="font-mono font-bold text-red-400">DELETE</span> to confirm.
        </p>
        <input
          v-model="deleteConfirmText"
          placeholder="Type DELETE"
          class="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-red-500"
        />
        <div class="flex justify-end gap-3">
          <Button
            variant="outline"
            class="border-zinc-600 bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
            @click="showDeleteModal = false; deleteConfirmText = ''"
          >
            Cancel
          </Button>
          <Button
            class="bg-red-600 text-white hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed"
            :disabled="deleteConfirmText !== 'DELETE' || loading"
            @click="deleteDevice"
          >
            {{ loading ? 'Deleting...' : 'Delete' }}
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
