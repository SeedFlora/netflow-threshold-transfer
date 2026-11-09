# NetFlow Threshold Transfer

Kode eksperimen untuk mengukur apakah threshold deteksi intrusi yang dikalibrasi pada trafik Januari tetap memenuhi anggaran false positive ketika diterapkan pada trafik Februari. Dataset yang digunakan adalah **NF-UNSW-NB15-v3**.

Panduan ini ditujukan untuk pembaca yang baru mulai memakai Git dan Python. Ikuti urutan langkah pada bagian instalasi dan reproduksi. Semua perintah PowerShell dijalankan dari folder utama repository, tempat `pyproject.toml` berada.

## Apa yang dipelajari

Model memberi setiap flow sebuah skor. Sebuah flow masuk antrean alert ketika `score > threshold`. Mengganti threshold dapat mengubah jumlah false positive meskipun model dan skor prediksinya sama.

| Istilah | Arti dalam proyek |
| --- | --- |
| Flow | Ringkasan komunikasi jaringan yang menjadi satu baris data |
| Benign | Label trafik normal pada benchmark |
| Attack | Label trafik serangan pada benchmark |
| False positive | Flow berlabel benign yang menghasilkan alert |
| Budget `alpha` | Proporsi benign yang diizinkan menghasilkan alert |
| FPR | Jumlah false positive dibagi jumlah flow benign |
| Budget ratio `rho` | `FPR / alpha`. Nilai di atas 1 berarti budget terlampaui |
| AP | Average precision untuk mengukur kualitas ranking skor |
| Recall | Proporsi flow attack yang berhasil ditandai |
| Seed | Angka pengendali variasi pengambilan sampel dan fitting |

Sebagai contoh, budget 0,1% pada 100.000 flow benign mengizinkan sekitar 100 alert benign. AP, FPR pada threshold tertentu, dan jumlah alert per jam dilaporkan secara terpisah.

## Hasil yang sudah tersimpan

Eksperimen utama mencakup 24 fit inti dan 6 fit kontrol. Dua fit smoke dipakai untuk memeriksa jalannya pipeline. Pengujian kode saat penyiapan repository menghasilkan **38 tests passed**.

| Hasil pada target Februari | Nilai |
| --- | --- |
| AP XGBoost/F1, rata-rata tiga seed | 0,999972 |
| Budget benign FPR untuk T1 | 0,1% |
| FPR XGBoost/F1 setelah transfer | sekitar 1,1682% |
| Budget ratio | sekitar 11,68 |
| Alert benign per jam | sekitar 1.070, dengan allowance sekitar 92 |
| Budget ratio setelah flow yang melibatkan attack hosts dikeluarkan | sekitar 1,18 |

Audit post hoc menemukan bahwa 88,6–90,8% false positive XGBoost/F1 melibatkan flow berlabel benign ke host penyerang testbed yang absen dari calibration. Temuan tersebut membatasi interpretasi besarnya kegagalan transfer. Eksperimen memakai satu benchmark laboratorium tahun 2015. Dekomposisi dan pembaruan threshold yang ditambahkan sesudah evaluasi diberi status post hoc.

Ringkasan angka tersedia pada `results/revision_numbers.json` dan `results/posthoc_attack_hosts.json`. Parameter dan prosedur lengkap berada pada `configs/` dan `src/nids_lab/`.

## Isi repository

```text
netflow-threshold-transfer/
  configs/                 Konfigurasi main, smoke, dan extended
  src/nids_lab/            Implementasi audit, split, model, threshold, evaluasi
  tests/                   Pengujian otomatis
  scripts/                 Pipeline dan analisis diagnostik
  results/                 Ringkasan CSV/JSON dari eksperimen yang direkam
  figures/                 Gambar hasil analisis
  reports/                 Laporan audit, protokol, dan interpretasi
  literature/              Metadata dan matriks referensi
  pyproject.toml           Metadata paket Python
  requirements.lock        Versi dependency eksperimen
  .gitattributes           Aturan line ending LF
  .gitignore               Aturan berkas lokal dan hasil build
```

Saat pipeline berjalan, folder `data/`, `manifests/`, dan `runs/` dibentuk secara lokal. Dataset, model terlatih, prediksi per flow, cache, keluaran Word/PDF, dan arsip paket berada dalam kelompok artefak lokal tersebut. Repository menyediakan kode, konfigurasi, dan ringkasan hasil untuk mereproduksinya.

## 1. Siapkan Git dan Python

Panduan Windows ini mengikuti lingkungan eksperimen yang direkam dengan Python 3.13.5. Metadata paket menerima Python 3.12 atau lebih baru. Versi dependency yang digunakan tercatat tepat pada `requirements.lock`.

Unduh Git for Windows dan Python melalui situs resminya. Saat memasang Python, aktifkan Python Launcher untuk memakai perintah `py` pada panduan ini. Setelah instalasi, buka ulang PowerShell. [Git for Windows](https://git-scm.com/install/windows), [Python 3.13.5](https://www.python.org/downloads/release/python-3135/)

Periksa instalasi melalui PowerShell.

```powershell
git --version
py -3.13 --version
```

Jika `py` tersedia dengan versi Python lain, gunakan `py -0p` untuk melihat interpreter yang terpasang. Perintah berikut memakai interpreter Python 3.13.

Jika instalasi hanya menyediakan `python`, pastikan `python --version` menunjukkan Python 3.12 atau lebih baru. Gunakan `python -m venv .venv` sebagai pengganti `py -3.13 -m venv .venv` pada langkah 3.

## 2. Clone repository

Clone membuat salinan repository di komputer. Pindah dahulu ke folder tempat proyek akan disimpan. Contoh berikut memakai folder `Projects` di direktori pengguna.

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\Projects" -Force
Set-Location -LiteralPath "$env:USERPROFILE\Projects"
git clone https://github.com/SeedFlora/netflow-threshold-transfer.git
Set-Location -LiteralPath '.\netflow-threshold-transfer'
```

Pastikan folder aktif benar.

```powershell
Get-Location
Test-Path -LiteralPath '.\pyproject.toml'
```

Perintah kedua seharusnya menghasilkan `True`. Seluruh langkah berikut dilakukan dari folder ini.

## 3. Buat lingkungan Python proyek

Virtual environment menyimpan dependency khusus proyek di dalam `.venv`.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
```

Opsi `-e .` memasang paket `nids_lab` dari sumber proyek yang sedang dibuka. Perintah dalam panduan menyebut Python di `.venv` secara langsung agar interpreter yang dipakai jelas.

Periksa dependency dan daftar perintah aplikasi.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m nids_lab --help
.\.venv\Scripts\python.exe -m pytest -q
```

Pengujian pada langkah ini memakai fixture kecil dari kode pengujian. Dataset penelitian dipakai mulai tahap audit di bawah.

## 4. Unduh dan tempatkan dataset

Pada halaman UQ, buka bagian **NetFlow V3 Datasets**, pilih **NF-UNSW-NB15-v3**, lalu ikuti tautan unduhnya. Dataset yang dirujuk memiliki DOI `10.48610/6e0eda1`. [Halaman dataset UQ](https://staff.itee.uq.edu.au/marius/NIDS_datasets/), [halaman unduh NF-UNSW-NB15-v3](https://rdm.uq.edu.au/files/abd2f5d8-e268-4ff0-84fb-f2f7b3ca3e8f)

Simpan ZIP di folder utama repository menggunakan nama yang dibaca konfigurasi bawaan.

```text
f7546561558c07c5_NFV3DATA-A11964_A11964.zip
```

Ukuran ZIP yang diaudit adalah 110.825.147 byte. SHA-256 yang diterima implementasi adalah sebagai berikut.

```text
6d51554df43e324ba8d68fc31a02a83d860ba0a3a93d63320a4a6fc314c9cdfd
```

Verifikasi salinan unduhan.

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '.\f7546561558c07c5_NFV3DATA-A11964_A11964.zip'
```

Audit memeriksa hash, mengekstrak CSV dan manifest secara otomatis ke `data/raw/`, kemudian membentuk cache Parquet. Data yang diaudit berisi 2.365.424 flow dan 55 kolom asli. CSV yang diekstrak berukuran sekitar 577 MB. Ruang disk tambahan dipakai untuk cache, model, dan prediksi.

Sebagai alternatif, resolver menerima CSV `NF-UNSW-NB15-v3.csv` dengan SHA-1 `2cba4879ead17c51e3268a01c06af41186cd90e4`. Jika memakai CSV langsung, sesuaikan `data_path` pada `configs/main.yaml` dan `configs/smoke.yaml`, lalu berikan path CSV pada perintah `audit`.

## 5. Audit data dan siapkan split

```powershell
.\.venv\Scripts\python.exe -m nids_lab doctor
.\.venv\Scripts\python.exe -m nids_lab audit --data f7546561558c07c5_NFV3DATA-A11964_A11964.zip
.\.venv\Scripts\python.exe -m nids_lab prepare --config configs/main.yaml
```

`doctor` merekam dependency, perangkat, dan status CUDA ke `reports/environment.json`. `audit` menghasilkan `reports/dataset_audit.json` serta `data/processed/dataset.parquet`. `prepare` menghasilkan `manifests/split_manifest.parquet` dan `reports/split_report.json`.

| Protokol | Pembagian data |
| --- | --- |
| `P_capture` | Januari sebagai source. Februari sebagai target. Cutoff source sekitar 70%, dengan embargo 60 detik dan purge group |
| `P_random` | Pembanding grouped random atas kedua capture |

Timestamp Januari yang dibaca sebagai UTC melewati tengah malam pada 22–23 Januari 2015. Target berasal dari 18 Februari 2015. Calibration berada sesudah serangan Januari berakhir, sehingga calibration berisi flow benign saja. Preprocessing, fitting, early stopping, dan threshold protokol beku memakai data source sesuai perannya.

Konfigurasi bawaan mencoba CUDA untuk XGBoost dan melakukan fallback ke CPU jika CUDA tidak dapat dipakai. Untuk menetapkan CPU sejak awal, ubah `device` menjadi `cpu` pada kedua konfigurasi sebelum membekukan eksperimen. Lingkungan asal memakai Windows 11, RAM 32 GB, dan GPU laptop 8 GB. Lama eksekusi bergantung pada perangkat dan data yang diproses.

## 6. Jalankan uji awal dan eksperimen utama

`freeze` merekam identitas data, split, konfigurasi, dan byte sumber training. Berkas plan dibentuk pada setiap workspace reproduksi. `.gitattributes` mempertahankan LF agar identitas sumber konsisten antar-checkout.

```powershell
.\.venv\Scripts\python.exe -m nids_lab freeze --config configs/main.yaml
.\.venv\Scripts\python.exe -m nids_lab smoke --config configs/smoke.yaml --resume
```

Smoke menjalankan LR dan XGBoost dengan satu seed dan 50.000 baris training. Setelah berhasil, jalankan konfigurasi utama.

```powershell
.\.venv\Scripts\python.exe -m nids_lab run --config configs/main.yaml --resume
.\.venv\Scripts\python.exe -m nids_lab evaluate --config configs/main.yaml
.\.venv\Scripts\python.exe -m nids_lab report --config configs/main.yaml
```

Main menggunakan 200.000 baris training, tiga seed `42`, `2026`, dan `3407`, LR serta XGBoost, dan fitur F0/F1. Dua protokol menghasilkan 24 fit inti. Dummy dan random forest menambah enam fit kontrol pada `P_capture/F1`.

T0 memakai threshold 0,5. T1 memakai kuantil calibration benign. T2 mengambil threshold maksimum dari blok calibration kronologis. Budget yang diuji adalah 0,1% dan 1%. Keputusan attack memakai strict exceedance `score > threshold`, sehingga skor yang sama dengan threshold ikut menentukan rate yang dapat dicapai.

Setiap run menyimpan status dan log di `runs/<run_id>/`. Opsi `--resume` melewati run lengkap yang identitasnya sesuai. Konfigurasi main membatasi satu fit sampai 2.400 detik dan satu invocation sampai 21.600 detik. Jika batas invocation tercapai, jalankan kembali perintah `run --resume` yang sama.

Untuk memakai rangkaian perintah otomatis pada penempatan ZIP bawaan, tersedia dua script berikut.

```powershell
.\scripts\run_all.ps1
```

```bash
bash scripts/run_all.sh
```

Script otomatis memakai nama ZIP bawaan pada tahap audit. Untuk lokasi dataset khusus, gunakan urutan CLI manual. Smoke dievaluasi terpisah jika diperlukan.

```powershell
.\.venv\Scripts\python.exe -m nids_lab evaluate --config configs/smoke.yaml
```

## 7. Baca hasil dan jalankan analisis tambahan

| Berkas | Isi |
| --- | --- |
| `results/main_metrics.csv` | Operating point setiap run dan aturan threshold |
| `results/main_seed_summary.csv` | Agregasi seed |
| `results/main_run_status.csv` | Status seluruh run main |
| `results/quality_gates.json` | Hasil pemeriksaan artefak |
| `reports/experiment_report.md` | Laporan hasil utama |
| `results/revision_numbers.json` | Ringkasan angka turunan |
| `results/posthoc_attack_hosts.json` | Audit keterlibatan attack hosts dan pengecualian flow |

Ringkasan CSV/JSON yang disertakan adalah hasil eksekusi yang direkam. Menjalankan ulang pipeline menulis ringkasan dari run di workspace aktif. Setiap perubahan data, konfigurasi, atau training code akan memiliki identitas eksperimen tersendiri. Untuk eksperimen dengan pilihan baru, gunakan nama profile dan workspace terpisah agar artefaknya mudah dibedakan.

Setelah main selesai dievaluasi dan dilaporkan, jalankan diagnostik dalam urutan berikut.

```powershell
.\.venv\Scripts\python.exe scripts/verify_artifacts.py
.\.venv\Scripts\python.exe scripts/missingness_diagnostic.py
.\.venv\Scripts\python.exe scripts/plot_diagnostics.py
.\.venv\Scripts\python.exe scripts/summarize_findings.py
.\.venv\Scripts\python.exe scripts/posthoc_operating_points.py
.\.venv\Scripts\python.exe scripts/posthoc_missingness.py
.\.venv\Scripts\python.exe scripts/posthoc_mitigation.py
.\.venv\Scripts\python.exe scripts/revision_numbers.py
.\.venv\Scripts\python.exe scripts/posthoc_attack_hosts.py
```

Script post hoc membaca prediksi beku. Pembaruan threshold dievaluasi pada skor tersimpan dengan kondisi penggunaan label yang dijelaskan dalam laporan. Interval pembaruan threshold menggunakan threshold hasil estimasi yang tetap selama bootstrap. Persentase dekomposisi bergantung pada populasi, partisi, dan referensi pembobotannya.

## 8. Simpan perubahan dengan Git

Git menyimpan versi kode dalam commit. GitHub menyimpan salinan remote yang dapat di-clone. Setelah clone, lihat branch dan perubahan lokal.

```powershell
git status
git remote -v
git switch -c eksperimen-saya
```

Setelah mengubah kode atau dokumentasi, periksa diff dan jalankan pengujian.

Pada instalasi Git baru, tetapkan identitas commit untuk repository ini. Ganti contoh dengan nama serta email GitHub atau alamat noreply akun sendiri.

```powershell
git config user.name "Nama Anda"
git config user.email "email-akun-anda@example.com"
```

```powershell
git diff
.\.venv\Scripts\python.exe -m pytest -q
git add README.md src configs scripts tests
git diff --cached --stat
git commit -m "Jelaskan perubahan eksperimen"
git push -u origin eksperimen-saya
```

Push ke repository memerlukan akun yang memiliki izin tulis. Pada GitHub, branch tersebut dapat dipakai untuk membuat pull request. Untuk mengambil perubahan saat working tree bersih, gunakan `git pull --ff-only` pada branch yang sesuai.

`.gitignore` memisahkan kode dari dataset, run, cache, temporary preview, naskah, sumber LaTeX, paket revisi, korespondensi reviewer, dan hasil build lokal. Pola nama berkas yang mengandung `codex` diabaikan tanpa membedakan huruf besar dan kecil. Periksa daftar staging sebelum membuat commit.

## Pemecahan masalah

| Pesan atau kondisi | Langkah pemeriksaan |
| --- | --- |
| `git` atau `py` tidak ditemukan | Periksa instalasi dan buka ulang PowerShell |
| `No module named nids_lab` | Jalankan instalasi editable dari folder yang memiliki `pyproject.toml` |
| Dataset tidak ditemukan | Cocokkan nama/lokasi ZIP dengan `data_path` dan folder aktif |
| `Dataset identity mismatch` | Bandingkan hash dengan nilai di atas dan unduh versi NF-UNSW-NB15-v3 yang sesuai |
| `Frozen plan differs` | Cocokkan data, konfigurasi, versi dependency, dan line ending dengan identitas yang dibekukan. Gunakan workspace/profile baru untuk rancangan baru |
| Run gagal atau invocation berakhir | Baca `runs/<run_id>/status.json`, `stderr.log`, dan `stdout.log`, lalu lanjutkan dengan konfigurasi yang sama dan `--resume` setelah penyebabnya diperbaiki |
| `run ... --resume` melaporkan `skipped_completed` | Run lengkap ditemukan dan dipakai kembali |
| Diagnostik meminta satu run tetapi menemukan beberapa | Pisahkan artefak rancangan eksperimen ke workspace/profile masing-masing |
| PowerShell memblokir `run_all.ps1` | Jalankan urutan CLI manual pada langkah 5–6 |
| Ruang disk habis | Periksa ruang untuk data hasil ekstraksi, cache, model, prediksi, dan preview |

## Menggunakan Linux

Periksa `python3 --version` dan gunakan Python 3.12 atau lebih baru. Untuk eksperimen inti, buat lingkungan memakai `python3 -m venv .venv`. Ganti `.\.venv\Scripts\python.exe` pada perintah Windows dengan `.venv/bin/python`. Script `scripts/run_all.sh` tersedia untuk alur otomatis. Lingkungan eksekusi yang diverifikasi proyek ini adalah Windows.

## Provenance dan ruang lingkup

Data source dan target berasal dari benchmark yang sama pada Januari dan Februari 2015. F0 memiliki 40 predictor. F1 memiliki 48 predictor dengan delapan tambahan statistik inter-arrival time. IP, label, timestamp absolut, query identifier, dan metadata hasil pemrosesan dikelola di luar predictor. Grouping memakai heuristic sesi bidirectional dengan idle gap 60 detik.

Audit deskriptif awal pernah mengamati label seluruh dataset. Protokol beku menetapkan pemakaian source untuk fitting dan calibration, sedangkan analisis pembaruan threshold memakai kondisi post hoc yang didokumentasikan. Seed mengukur variasi fitting. Pengulangan pada corpus dan capture independen diperlukan untuk menguji generalisasi.

Dataset memiliki sumber dan sitasinya sendiri pada UQ. Metadata referensi tersedia di `literature/`. Laporan eksperimen mempertahankan tanggal dan status saat dibuat. Ringkasan angka turunan tersedia pada `results/revision_numbers.json`.
