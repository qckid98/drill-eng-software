# Drilling Proposal — Web Application

Aplikasi web Django untuk menggantikan workbook Excel
`DrillTime_ BDA-G3 - Cluster BDA-D1.xlsx` (form `DEP/Form/DE/01/DT` v2.4/2017)
yang dipakai oleh Drilling Engineer PT. Pertamina EP untuk menyusun
Drilling Proposal yang diajukan ke management.

## Fitur

- Custom user dengan role: **Engineer**, **Supervisor**, **Management**, **Admin**.
- Wizard pembuatan proposal meniru alur sheet `A.Proposal`:
  1. Data umum well (nama, lokasi, field, koordinat, target formation)
  2. Casing design (tabel section: 26", 17.5", 12.25", 8.5", dll.)
  3. Drilling activities per casing section (dipilih dari master library hasil
     import Tab 1.0)
  4. Tubing & completion spec
  5. Review & submit
- Kalkulasi drilling time otomatis (`proposals/services/calc.py`):
  - Drilling / non-drilling / completion hours → days per section
  - Drilling rate m/day per section
  - **Rig Days = MAX(total_days) + mob + demob** — meniru formula
    `=MAX(Chart!CA212:CA232)` di Excel untuk operasi paralel.
- Workflow approval: Draft → Submitted → Under Review → Approved / Rejected,
  dengan audit trail (`ApprovalLog`).
- Dashboard + Inbox per role.
- Visualisasi Chart.js — breakdown drilling vs non-drilling per hole section.
- Master data diimport sekali dari Excel sumber via management command.

## Struktur

```
drilltime_app/
├── drilltime_app/          # Django project (settings, urls, wsgi)
├── accounts/               # Custom User + Role
├── masterdata/             # HoleSection, MudType, RopRate, Activity*, RigSpec
│   └── management/commands/import_drilltime_master.py
├── wells/                  # Well model
├── proposals/              # Proposal, CasingSection, ProposalActivity, ApprovalLog
│   ├── services/
│   │   ├── calc.py         # kalkulasi drilling time (replace formula Excel)
│   │   └── approval.py     # state machine approval
│   └── signals.py          # auto-recalc totals via post_save
├── templates/base.html
├── static/css/app.css
└── requirements.txt
```

## Setup (dev)

Prasyarat: Python 3.12+.

```bash
cd drilltime_app
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
```

### Database PostgreSQL (opsional, production)

Set env var sebelum menjalankan perintah Django:

```
DATABASE_URL=postgres://user:pass@localhost:5432/drilltime
```

Kalau tidak diset, Django akan memakai SQLite (`db.sqlite3`) untuk kemudahan dev.

### Import master data dari Excel

```bash
python manage.py import_drilltime_master "C:/path/DrillTime_ BDA-G3 - Cluster BDA-D1.xlsx"
```

Perintah ini membaca:

- **Sheet `ROP`** → `HoleSection` + `RopRate`
- **Sheet `Tab 1.0`** → `ActivityCategoryL1` + `ActivityCategoryL2` + `DrillingActivity` (~180 baris pada workbook referensi)
- **Sheet `A.Proposal`** → contoh `RigSpec` (PDSI #04.3)

Script idempotent — aman dijalankan ulang, pakai `update_or_create`.

### Menjalankan server

```bash
python manage.py runserver
```

Buka http://127.0.0.1:8000/

## User testing cepat

Lewat Django shell:

```python
from accounts.models import User, Role
User.objects.create_user(username="engineer1",  password="pass", role=Role.ENGINEER,   full_name="Engineer 1")
User.objects.create_user(username="supervisor1", password="pass", role=Role.SUPERVISOR, full_name="Supervisor 1")
User.objects.create_user(username="manager1",    password="pass", role=Role.MANAGEMENT, full_name="Manager 1")
```

Lalu login sebagai `engineer1`, klik **+ Proposal Baru**, ikuti wizard,
dan submit. Login ulang sebagai `supervisor1` untuk forward ke management,
lalu `manager1` untuk approve.

## Validasi numerik vs Excel

Setiap perubahan activity memicu `recalculate_proposal()` yang menyimpan
nilai ter-cache di `CasingSection.total_days`, `Proposal.total_dryhole_days`,
`total_completion_days`, `total_rig_days`. Nilai tersebut seharusnya cocok
(toleransi ±0.1 hari) dengan cell `R36-R42` di sheet `A.Proposal` pada
workbook sumber bila input aktivitas identik.

## Modul AFE (Phase 2)

Setelah proposal berstatus **APPROVED**, engineer dapat membuat dokumen
**AFE (Authorization For Expenditure)** yang meniru sheet `F.CONT` pada
workbook `AFE_v.2017_Kontrak JTB_Update April 2026.xlsx`. Satu proposal dapat
memiliki banyak revisi AFE (`v1`, `v2`, ...), masing-masing independen.

### Struktur data
- **`AFETemplate`** — 58 baris F.CONT (Tangible + Intangible, dipecah ke
  section Preparation / Drilling / Formation / Completion / General).
- **`RateCardItem`** — harga satuan (USD) per line AFE, di-import dari sheet
  `D.MATE` + fallback rate set (~41 item) untuk memastikan kalkulasi non-zero.
- **`AFE`** — dokumen AFE, FK ke `proposals.Proposal`, cached total
  (`total_tangible_usd`, `total_intangible_usd`, `contingency_amount_usd`,
  `grand_total_usd`, `cost_per_meter_usd`, `cost_per_day_usd`).
- **`AFELine`** — satu baris F.CONT per AFE, menyimpan `calculated_usd`
  (hasil auto-generate) + `override_usd` (opsional edit manual).
- **`AFEApprovalLog`** — audit trail sama pola dengan `proposals.ApprovalLog`.

### Calculation methods (`afe/services/calc.py`)

| Method | Rumus |
|---|---|
| `RIG_DAYS_RATE`       | `proposal.total_rig_days × daily_rate` (line 19/20/22/24/45/50/52/53) |
| `DHB_CB_SPLIT`        | `dhb_days × dhb_rate + cb_days × cb_rate` (line 21, 28) |
| `PER_METER_DEPTH`     | `max(depth_m) × rate/m` (line 11, 32) |
| `PER_CASING_WEIGHT`   | `Σ(casing_weight_lb × interval_ft) × rate/lb` (line 2, 4) |
| `LUMP_SUM`            | flat lump sum dari rate card |
| `MANUAL`              | subtotal / header row — tidak di-auto |

Grand total = `tangible + intangible + (tangible+intangible) × contingency%`.

### Import master AFE

```bash
python manage.py import_afe_master "C:/path/AFE_v.2017_Kontrak JTB_Update April 2026.xlsx"
```

Flags: `--templates-only`, `--rates-only`, `--dry-run`.

Command melakukan:
1. Seed 58 `AFETemplate` (hard-coded — stabil).
2. Seed ~41 **fallback rate** untuk line utama (rig, mud, cement, logging,
   fuel, camp) sehingga kalkulasi selalu non-zero.
3. Import rate item dari sheet `D.MATE` (range `AV86:BY363`).

### Workflow
1. Engineer buka proposal APPROVED → klik **"+ Buat AFE (Revisi Baru)"**.
2. Sistem generate 58 baris otomatis dari rate card × data proposal.
3. Engineer edit override / contingency %, simpan.
4. Submit → Supervisor forward → Management approve/reject.
5. Semua aksi tercatat di `AFEApprovalLog`.

URL utama:
- `/afe/`             — dashboard AFE
- `/afe/inbox/`       — inbox approval (Supervisor / Management)
- `/afe/<pk>/`        — detail (chart donut per-section)
- `/afe/<pk>/edit/`   — edit header + 58 baris override
- `/afe/create/<proposal_pk>/` — buat revisi AFE baru dari proposal

## Roadmap (out of MVP scope)

- Export PDF dengan layout form `DEP/Form/DE/01/DT` (WeasyPrint).
- Export AFE ke Excel BS19 template.
- Mirror E.COMP / C2-XX detail sheets untuk granularitas per-item.
- Auto Profile / well trajectory diagram.
- SSO Pertamina.
- Notifikasi email saat ada perubahan status approval.
