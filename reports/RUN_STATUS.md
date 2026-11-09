# Status eksekusi akhir

Workspace: **G:\network**. Tanggal: **5 September 2026**.

| Tahap | Hasil |
|---|---|
| Lingkungan lokal | Python 3.13.5 dalam `.venv`, dependency terkunci; tidak mengubah driver/global Python |
| Doctor dan CUDA smoke | Berhasil; XGBoost melaporkan `cuda:0` |
| Audit ZIP/CSV penuh | Identitas dan 2.365.424 flow cocok; raw data tetap tersimpan |
| Prepare dan freeze | Berhasil; tidak ada overlap group/event antarsplit |
| Unit/integration tests | **38 passed**, hasil akhir tanpa warning; `unit_test_results.txt` |
| Smoke real data | **2/2 selesai**, 50.000 train rows; hanya debugging |
| Main inti | **24/24 selesai**, 200.000 train rows, 3 seed |
| Main pendukung | **6/6 selesai**, dummy/RF pada P_capture/F1 |
| Fit gagal / run belum dijalankan dalam main | **0 / 0** |
| Evaluasi frozen predictions | **30 main + 2 smoke**; smoke tidak masuk tabel main |
| Quality gate artefak | **30/30 terverifikasi**, tanpa training/convergence warnings |
| Resume nyata | **30 completed runs dilewati, 0 fit baru** |
| Laporan | 150 operating points, 420 paired-IAT interval rows, seed aggregates, decomposition, bootstrap, per-attack, per-window, tails dan measured Pareto |
| Extended | Tidak dijalankan; opsional |

`results/main_run_status.json` mencatat invocation **resume terakhir**, sehingga `completed: 0, skipped_completed: 30` berarti tidak melatih ulang, bukan tidak ada hasil. Keadaan seluruh artefak ada di `results/main_run_status.csv` dan `results/quality_gates.json`.

## Command yang benar-benar telah dijalankan

Semua command Python menggunakan `.venv\Scripts\python.exe` dari workspace. Paket dipasang editable menggunakan `pip install -e . --no-deps --no-build-isolation`; versi tersimpan di `requirements.lock`.

```powershell
.\.venv\Scripts\python.exe -m nids_lab doctor
.\.venv\Scripts\python.exe -m nids_lab audit --data f7546561558c07c5_NFV3DATA-A11964_A11964.zip
.\.venv\Scripts\python.exe -m nids_lab prepare --config configs/main.yaml
.\.venv\Scripts\python.exe -m nids_lab freeze --config configs/main.yaml
.\.venv\Scripts\python.exe -m nids_lab smoke --config configs/smoke.yaml --resume
.\.venv\Scripts\python.exe -m nids_lab run --config configs/main.yaml --resume
.\.venv\Scripts\python.exe -m nids_lab evaluate --config configs/main.yaml
.\.venv\Scripts\python.exe -m nids_lab evaluate --config configs/smoke.yaml
.\.venv\Scripts\python.exe -m nids_lab report --config configs/main.yaml
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verify_artifacts.py
.\.venv\Scripts\python.exe scripts/missingness_diagnostic.py
.\.venv\Scripts\python.exe scripts/plot_diagnostics.py
.\.venv\Scripts\python.exe scripts/summarize_findings.py
```

Audit dan prepare awal dijalankan melalui Python API `audit_dataset(...)` dan `prepare_splits(load_config('configs/main.yaml'))`, kemudian CLI keduanya diverifikasi kembali dengan cache yang sama. Main freeze terjadi pada **2026-09-05 05:19:16 UTC**, sebelum smoke dan evaluasi test pertama. Smoke tidak dipakai untuk mengubah hyperparameter main.

## Keterbatasan implementasi yang perlu diketahui

Data cache menggunakan satu Parquet terkompresi dengan row groups 100.000, bukan banyak berkas per partisi; membership disimpan terpisah di manifest. Peak RSS/GPU adalah puncak sampel monitor, bukan hard allocator maximum. Pengukuran GPU device-wide mencakup proses lain. Preprocessing fit/development dan benchmark batch tercatat, tetapi total waktu semua transform test tidak dipisahkan. Script shell Linux disediakan tetapi lingkungan yang diuji adalah Windows.

Perbaikan engineering selama smoke/audit: fixed-length pandas hash key dan penanganan column order sklearn diperbaiki sebelum freeze. Setelah freeze, perubahan hanya pada validasi/evaluasi/reporting, status exit CLI, dan gambar; model, fitur, data, split, threshold serta config main tidak diubah. Validasi hash training kembali lulus pada resume.

Ringkasan hasil dan kontrol eksperimen tersedia pada [CONTRIBUTION_EVIDENCE.md](CONTRIBUTION_EVIDENCE.md).
