# Changelog

## DeviceManager.vue

### Delete Device
- Added `deleteDevice()` function — sends `DELETE /devices/{id}`, clears selection, refreshes list.
- Added **Delete** button next to **Edit** in view mode.
- `Delete` is now a solid red button with white text.
- Added a delete confirmation modal rendered via `Teleport`.
- Modal requires typing `DELETE` exactly before the destructive action is enabled.
- Modal includes both **Delete** and **Cancel** buttons and also closes on backdrop click.

### API Base URL
- Replaced all hardcoded `http://localhost:8000` URLs with `API_BASE` constant.
- `API_BASE` reads from `VITE_API_URL` env variable with fallback to `http://localhost:8000`.
- To configure for production, set `VITE_API_URL=http://your-server` in `my-vue-app/.env`.
- Fixed broken template literals left by `sed` substitution (mixed backtick/single-quote delimiters).

### Cancel Button
- Restyled Cancel to a dark button (`bg-zinc-800`) with readable light text.

### Header Actions
- `Edit` is now a solid blue button with white text.

### Responsive Sidebar
- Layout changed from `flex` to `flex-col md:flex-row` for mobile stacking.
- Added mobile topbar (`md:hidden`) with a **Show list / Hide** toggle button.
- Sidebar hidden by default on mobile, toggled via `sidebarOpen` ref, always visible on `md+`.

### Testing Shortcut
- Added `createTestDevice()` helper for quick test data creation.
- Added **Quick Test Device** sidebar button that instantly creates a test device and selects it.

### Empty State Interactivity
- `+ New Device` text in the empty right panel is now clickable — calls `clickNew()`.
- Added `cursor-pointer` and `hover:underline` for visual feedback.

---

## backend/app/models.py

### ExperimentReq (rewritten to match API spec)
- `command`: `str` → `Literal["start"]` — FastAPI returns 422 automatically for any other value.
- `setpoint_changes`: required → `ExperimentSetpointChanges | None = None` — optional per spec.
- `unit` in `ExperimentInputArgument`: `str | None = None` → `str` — required per spec.
- `type` in `ExperimentInputArgument`: `str` → `Literal["number", "string", "boolean"]`.
- `simulation_time` / `sample_rate`: `int | float` → `float`.

### Removed
- `ExperimentRun` (old DB-era model using `device_id`, `input_values`, `period`, `frequency`) — no longer used by new spec flow.

### New models added
| Model | Purpose |
|---|---|
| `ExperimentChangeReq` | WebSocket `change` command payload |
| `ExperimentStopReq` | WebSocket `stop` command payload |
| `ExperimentInputHistoryEntry` | Single entry in `run.input_history` |
| `ExperimentOutputHistoryEntry` | One `output_history` row with required `time` and dynamic output keys |
| `ExperimentRunLog` | The `run` object inside an experiment log |
| `ExperimentLogBase` | Reusable base response model matching the documented finished experiment shape |
| `ExperimentLog` | Full response for `GET /api/server/experiments/{job_id}` |

### Response model cleanup
- Removed unfinished `ExperimentFinished` stub that was breaking syntax.
- `output_history` is now typed as `list[ExperimentOutputHistoryEntry]` instead of `list[dict]`.
- `ExperimentLogBase` now matches the documented completed experiment response shape.

---

## backend/app/routers/experiments.py
- Updated import from `ExperimentRun` → `ExperimentReq` to match removed model.
- `/run` endpoint updated to use new `validate_experiment` signature (by `device_name`, `input_arguments`, `simulation_time`, `sample_rate`).
- Queue item now stores full new-spec fields: `device_name`, `software_name`, `input_arguments`, `output_arguments`, `simulation_time`, `sample_rate`, `setpoint_changes`.

---

## backend/app/services/services.py

### `validate_experiment` rewritten
- Lookup changed from `device_id: int` → `device_name: str`.
- Input parameter changed from `input_values: dict[str, int|float|bool]` → `input_arguments: dict[str, ExperimentInputArgument]` — reads `.value` from each argument object.
- `period` / `frequency` parameters replaced with `simulation_time: float` / `sample_rate: float`.
- Validation: `simulation_time` ≤ `time_limit.period`, `sample_rate` ≤ `time_limit.frequency`.
- Type matching now accepts both spec type names (`number`, `boolean`) and DB type names (`float`, `int`, `bool`).
- Eager-loads `software` relationship (required for software name check in queue endpoint).

---

## backend/app/routers/server.py

### `POST /api/server/experiments/queue` — fully implemented
- Replaced TODO stub with complete implementation.
- Calls updated `validate_experiment` by device name.
- Validates that `software_name` matches the device's configured software → 404 if not found.
- Checks Redis device lock → 409 Conflict if device is already busy.
- Builds queue item with all spec fields and pushes to `device_queue:{device_id}` via Redis.
- Fires Dramatiq `device_worker` to process the queue.
- Returns `{"job_id": uuid}` per spec.
- Added imports: `uuid`, `json`, `redis_client`, `device_worker`.

---

## backend/app/routers/devices.py

### Device deletion fix
- Fixed `DELETE /devices/{id}` returning 500 for devices with related records.
- Endpoint now eagerly loads the related config tree before deletion.
- Deletion order is explicit to satisfy FK constraints:
  - `InputLimit`
  - `Input`
  - `Output`
  - `TimeLimit`
  - `Config`
  - `Device`
- Added model imports required for cascading manual cleanup.

---

## backend/app/tasks.py

### `run_experiment` subprocess args updated
- Replaced old `--inputs` (flat `input_values` dict) with new spec args:
  - `--device-name`, `--software-name`
  - `--input-arguments` (full `InputArgument` objects as JSON)
  - `--output-arguments`, `--simulation-time`, `--sample-rate`, `--setpoint-changes`
