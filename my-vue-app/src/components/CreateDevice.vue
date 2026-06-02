<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { ref } from 'vue'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { apiFetch } from '@/lib/api'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const DEVICE_TYPES = ['sensor', 'actuator', 'controller', 'gateway']

const formSchema = toTypedSchema(
  z.object({
    name: z.string().min(1, 'Name is required'),
    slx_model: z.string().trim().min(1, 'SLX model is required'),
    device_type: z.string().optional(),
    maintenance_start: z.string().optional(),
    maintenance_end: z.string().optional(),
  })
)

const form = useForm({ validationSchema: formSchema })

const success = ref(false)
const error = ref<string | null>(null)
const loading = ref(false)

const onSubmit = form.handleSubmit(async (values) => {
  loading.value = true
  success.value = false
  error.value = null
  try {
    const res = await apiFetch(`${API_BASE}/devices`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: values.name,
        slx_model: values.slx_model,
        device_type: values.device_type ?? null,
        maintenance_start: values.maintenance_start || null,
        maintenance_end: values.maintenance_end || null,
      }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data?.detail ?? `Error ${res.status}`)
    }
    success.value = true
    form.resetForm()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-background p-4">
    <Card class="w-full max-w-md">
      <CardHeader>
        <CardTitle>Create Device</CardTitle>
        <CardDescription>Add a new device to the system.</CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit="onSubmit" class="space-y-4">

          <FormField v-slot="{ componentField }" name="name">
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input placeholder="e.g. Sensor A1" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="slx_model">
            <FormItem>
              <FormLabel>SLX Model</FormLabel>
              <FormControl>
                <Input placeholder="e.g. MyModel.slx" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="device_type">
            <FormItem>
              <FormLabel>Device Type</FormLabel>
              <Select v-bind="componentField">
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a type (optional)" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem v-for="t in DEVICE_TYPES" :key="t" :value="t">
                    {{ t }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="maintenance_start">
            <FormItem>
              <FormLabel>Maintenance Start</FormLabel>
              <FormControl>
                <Input type="time" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="maintenance_end">
            <FormItem>
              <FormLabel>Maintenance End</FormLabel>
              <FormControl>
                <Input type="time" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <div v-if="success" class="text-sm text-green-600 font-medium">
            Device created successfully!
          </div>
          <div v-if="error" class="text-sm text-red-600 font-medium">
            {{ error }}
          </div>

          <Button type="submit" class="w-full" :disabled="loading">
            {{ loading ? 'Creating...' : 'Create Device' }}
          </Button>

        </form>
      </CardContent>
    </Card>
  </div>
</template>
