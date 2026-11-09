# Dua puluh paper terkait — penelusuran awal

Tanggal penelusuran: **5 September 2026**. Ini bukan klaim semua teks lengkap telah dibaca. Tingkat akses disebutkan per entri. Artikel jurnal dan precursor preprint tidak dihitung ganda.

Prioritas pemeriksaan novelty: **P01–P05, P11, dan P16**. Keberadaan penelitian serupa tidak boleh disembunyikan. Paper lama tetap berguna sebagai landasan evaluasi; paper terbaru tidak otomatis lebih kuat kualitasnya.

## P01 — Time Matters: Temporal NetFlow Features for ML-Based Network Intrusion Detection

**Luay et al. (2026)** — IEEE Access

Identifier: `10.1109/ACCESS.2026.3688204`. [Sumber primer](https://ieeexplore.ieee.org/document/11498288/).

**Relevansi:** Landasan dataset v3 dan fitur temporal.

**Catatan kritis:** Penambahan IAT atau evaluasi fitur temporal saja bukan novelty baru. Precursor arXiv 2503.04404 dan artikel jurnal dihitung satu research line; verifikasi judul/penulis versi final saat membuat BibTeX.

**Status pemeriksaan:** Metadata publikasi primer; bagian naskah precursor arXiv diperiksa. Teks lengkap versi jurnal belum berhasil dibaca.

## P02 — Self-Supervised Learning of Graph Representations for Network Intrusion Detection

**Guerra et al. (2025)** — NeurIPS 2025; arXiv v6 diperbarui 16 Agustus 2026

Identifier: `arXiv:2509.16625`. [Sumber primer](https://arxiv.org/abs/2509.16625).

**Relevansi:** GraphIDS; studi langsung memakai NF-UNSW-NB15-v3.

**Catatan kritis:** Training representasi benign-only tetapi pemilihan checkpoint/threshold menggunakan validation berlabel. Jangan menyebut seluruh pipeline label-free. Eksperimen kita tetap supervised pada training historis, bukan replikasi GraphIDS.

**Status pemeriksaan:** Bagian metode, preprocessing, threshold, dan keterbatasan pada HTML v6 diperiksa.

## P03 — TE-G-SAGE: Explainable Edge-Aware Graph Neural Networks for Network Intrusion Detection

**Luša, Pintar, and Vranić (2025)** — Modelling 6(4), 165

Identifier: `10.3390/modelling6040165`. [Sumber primer](https://www.mdpi.com/2673-3951/6/4/165).

**Relevansi:** Evaluasi kronologis langsung pada NF-UNSW-NB15-v3.

**Catatan kritis:** Jangan mengklaim penggunaan chronological split pada v3 sebagai yang pertama. Detail split dan threshold perlu dibaca penuh sebelum klaim perbedaan.

**Status pemeriksaan:** Metadata dan cuplikan terindeks dari penerbit; akses teks lengkap penerbit terbatas.

## P04 — Budget-aware two-stage NetFlow intrusion detection for high-traffic critical information infrastructure under domain shift

**Ha Thanh Dung (2026)** — International Journal of Critical Infrastructure Protection 54, 100876

Identifier: `10.1016/j.ijcip.2026.100876`. [Sumber primer](https://www.sciencedirect.com/science/article/abs/pii/S187454822600048X).

**Relevansi:** RiskGate-IDS: gating, anggaran komputasi, domain shift, dan kalibrasi target berlabel.

**Catatan kritis:** Pembanding novelty wajib. Fokus source-only kita harus dibedakan dari adaptasi target. Jangan mengisi detail eksperimen yang tidak tersedia dari abstrak.

**Status pemeriksaan:** Abstrak dan metadata terindeks penerbit; teks lengkap belum diakses.

## P05 — A transfer-aware, deployment-oriented evaluation framework for NetFlow-based intrusion detection systems (TAN-IDS)

**Dung Ha Thanh (2026)** — PLOS One 21(4), e0346801

Identifier: `10.1371/journal.pone.0346801`. [Sumber primer](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0346801).

**Relevansi:** Framework evaluasi transfer, source-only, mixed-domain, dan fine-tuning dengan data target.

**Catatan kritis:** Framework evaluasi tanpa classifier baru sudah ada. Harus ada pertanyaan dan bukti empiris spesifik, bukan sekadar mengganti dataset atau model.

**Status pemeriksaan:** Abstrak dan bagian metode pada HTML penerbit diperiksa.

## P06 — Are We There Yet? Unraveling the State-of-the-Art Graph Network Intrusion Detection Systems

**Wang et al. (2025)** — Preprint; status venue belum diverifikasi

Identifier: `arXiv:2503.20281`. [Sumber primer](https://arxiv.org/abs/2503.20281).

**Relevansi:** Audit replikasi GNN-NIDS dan kesenjangan performa benchmark dengan evaluasi lebih realistis.

**Catatan kritis:** Tidak menganggap skor di tabel paper lain langsung sebanding dengan split, fitur, dan hardware kita.

**Status pemeriksaan:** Abstrak dan bagian evaluasi/keterbatasan PDF diperiksa.

## P07 — NetFlow Datasets for Machine Learning-Based Network Intrusion Detection Systems

**Sarhan, Layeghy, Moustafa, and Portmann (2021)** — Big Data Technologies and Applications; Springer

Identifier: `10.1007/978-3-030-72802-1_9`. [Sumber primer](https://arxiv.org/abs/2011.09144).

**Relevansi:** Asal representasi dataset NetFlow yang distandardisasi.

**Catatan kritis:** Tahun preprint 2020 berbeda dari publikasi 2021; jangan dihitung dua paper.

**Status pemeriksaan:** Abstrak serta metadata publikasi/dataset primer diperiksa.

## P08 — Towards a Standard Feature Set for Network Intrusion Detection System Datasets

**Sarhan, Layeghy, and Portmann (2022)** — Mobile Networks and Applications 27, 357–370; online 2021

Identifier: `10.1007/s11036-021-01843-0`. [Sumber primer](https://link.springer.com/article/10.1007/s11036-021-01843-0).

**Relevansi:** Landasan fitur NetFlow v2 dan komparabilitas fitur.

**Catatan kritis:** Ablasi kita harus memakai baris v3 yang sama, bukan membandingkan dua versi CSV dengan jumlah flow berbeda.

**Status pemeriksaan:** Metadata penerbit dan abstrak preprint diperiksa.

## P09 — UNSW-NB15: A Comprehensive Data Set for Network Intrusion Detection Systems (UNSW-NB15 Network Data Set)

**Moustafa and Slay (2015)** — MilCIS 2015

Identifier: `10.1109/MilCIS.2015.7348942`. [Sumber primer](https://ieeexplore.ieee.org/document/7348942/).

**Relevansi:** Sumber trafik, konteks, dan taksonomi serangan dataset asal.

**Catatan kritis:** Trafik tahun 2015; v3 tidak otomatis berarti ancaman yang dikumpulkan tahun 2025/2026.

**Status pemeriksaan:** Metadata IEEE dan laman resmi dataset diperiksa.

## P10 — The Cross-Evaluation of Machine Learning-Based Network Intrusion Detection Systems

**Apruzzese, Pajola, and Conti (2022)** — IEEE Transactions on Network and Service Management 19(4), 5152–5169

Identifier: `10.1109/TNSM.2022.3157344`. [Sumber primer](https://arxiv.org/abs/2203.04686).

**Relevansi:** XeNIDS dan masalah cross-evaluation.

**Catatan kritis:** Generalization gap bukan klaim baru; kontribusi harus lebih spesifik.

**Status pemeriksaan:** Abstrak dan metadata institusional primer diperiksa.

## P11 — Explainable Cross-domain Evaluation of ML-based Network Intrusion Detection Systems

**Layeghy and Portmann (2023)** — Computers & Electrical Engineering 108, 108692

Identifier: `10.1016/j.compeleceng.2023.108692`. [Sumber primer](https://www.sciencedirect.com/science/article/abs/pii/S0045790623001167).

**Relevansi:** Penjelasan performa lintas domain dan ketergantungan pada fitur.

**Catatan kritis:** Precursor berjudul On Generalisability of Machine Learning-based Network Intrusion Detection Systems; jangan dihitung dua paper.

**Status pemeriksaan:** Metadata jurnal dan abstrak precursor diperiksa.

## P12 — On the Cross-Dataset Generalization of Machine Learning for Network Intrusion Detection

**Cantone, Marrocco, and Bria (2024)** — Preprint; status venue belum diverifikasi

Identifier: `arXiv:2402.10974`. [Sumber primer](https://arxiv.org/abs/2402.10974).

**Relevansi:** Generalisasi antar-dataset dan batas performa model.

**Catatan kritis:** Pemisahan capture dalam satu dataset tidak setara dengan generalisasi antarjaringan independen.

**Status pemeriksaan:** Abstrak primer diperiksa.

## P13 — Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study

**Engelen, Rimmer, and Joosen (2021)** — IEEE Security and Privacy Workshops

Identifier: `10.1109/SPW53761.2021.00009`. [Sumber primer](https://intrusion-detection.distrinet-research.be/WTMC2021/Resources/wtmc2021_Engelen_Troubleshooting.pdf).

**Relevansi:** Audit konstruksi dataset, ekstraksi fitur, dan label.

**Catatan kritis:** Dataset sudah berlabel bukan bukti seluruh data bersih.

**Status pemeriksaan:** Metadata IEEE dan materi situs lab penulis diperiksa.

## P14 — Dos and Don’ts of Machine Learning in Computer Security

**Arp et al. (2022)** — USENIX Security 2022

Identifier: `arXiv:2010.09470`. [Sumber primer](https://www.usenix.org/conference/usenixsecurity22/presentation/arp).

**Relevansi:** Panduan menghindari leakage, evaluasi salah, dan kesimpulan berlebihan.

**Catatan kritis:** Audit kualitas eksperimen merupakan kewajiban dasar, bukan otomatis novelty.

**Status pemeriksaan:** Laman primer USENIX dan abstrak diperiksa.

## P15 — SoK: Pragmatic Assessment of Machine Learning for Network Intrusion Detection

**Apruzzese, Laskov, and Schneider (2023)** — IEEE European Symposium on Security and Privacy

Identifier: `10.1109/EuroSP57164.2023.00042`. [Sumber primer](https://arxiv.org/abs/2305.00550).

**Relevansi:** Penilaian operasional, biaya, dan keterbatasan deployment.

**Catatan kritis:** Mengukur training time atau memakai laptop saja tidak cukup menjadi kontribusi.

**Status pemeriksaan:** Abstrak dan metadata primer diperiksa.

## P16 — TITANIUM-4: A Low-Latency Four-Layer Intrusion Detection Pipeline and the Limits of Benchmark-Trained Thresholds under Domain Shift

**Younas et al. (2026)** — International Journal of Innovations in Science & Technology 8(4), 1559–1582

Identifier: `10.33411/IJIST/1956`. [Sumber primer](https://journal.50sea.com/index.php/IJIST/article/view/1956).

**Relevansi:** Paper dekat tentang kegagalan transfer threshold dari benchmark.

**Catatan kritis:** Jangan mengklaim pertama menunjukkan threshold gagal lintas domain. Tinjau kualitas protokol yang dilaporkan dan bedakan analisis penyebab kuantitatif kita dari temuan kegagalan semata.

**Status pemeriksaan:** Abstrak dan metadata penerbit diperiksa; tanggal terbit 11 Juli 2026.

## P17 — Outside the Closed World: On Using Machine Learning for Network Intrusion Detection

**Sommer and Paxson (2010)** — IEEE Symposium on Security and Privacy

Identifier: `10.1109/SP.2010.25`. [Sumber primer](https://ieeexplore.ieee.org/document/5504793/).

**Relevansi:** Landasan perbedaan benchmark tertutup dengan lingkungan nyata.

**Catatan kritis:** Tidak membuat klaim deployment, zero-day, atau ancaman masa kini dari satu benchmark historis.

**Status pemeriksaan:** Metadata primer diperiksa.

## P18 — The Base-Rate Fallacy and the Difficulty of Intrusion Detection

**Axelsson (2000)** — ACM Transactions on Information and System Security 3(3), 186–205

Identifier: `10.1145/357830.357849`. [Sumber primer](https://dl.acm.org/doi/10.1145/357830.357849).

**Relevansi:** Pentingnya false alarm dan prevalensi serangan.

**Catatan kritis:** Gunakan artikel asli tahun 2000; jangan mencampurnya dengan publikasi ulang/chapter yang memiliki DOI atau tahun berbeda.

**Status pemeriksaan:** Metadata artikel asli pada sumber primer terindeks diperiksa; teks lengkap belum dibaca.

## P19 — Conformal Risk Control

**Angelopoulos, Bates, Fisch, Lei, and Schuster (2024)** — ICLR 2024

Identifier: `arXiv:2208.02814`. [Sumber primer](https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html).

**Relevansi:** Rujukan metodologis untuk membedakan kendali risiko dengan jaminan statistik bersyarat asumsi.

**Catatan kritis:** Quantile threshold dan max-block threshold kita bukan otomatis conformal risk control; tidak ada jaminan FPR masa depan di bawah arbitrary distribution shift.

**Status pemeriksaan:** Abstrak serta metadata proceedings primer diperiksa.

## P20 — The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets

**Saito and Rehmsmeier (2015)** — PLOS One 10(3), e0118432

Identifier: `10.1371/journal.pone.0118432`. [Sumber primer](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432).

**Relevansi:** Pemilihan metrik untuk ketimpangan kelas.

**Catatan kritis:** Average precision dan trapezoidal PR-AUC tidak identik. Laporkan nama estimator dan prevalensi setiap split; AP saja tidak menjamin FPR kecil.

**Status pemeriksaan:** Laman/abstrak penerbit dan metadata diperiksa.

## Matriks yang harus dilengkapi agen

Untuk setiap paper, isi: dataset dan versi; target biner/multikelas; model; fitur/identifier yang dipakai; unit dan urutan split; data yang boleh diakses saat fit preprocessing; label yang dipakai saat memilih model dan threshold; target FPR; kalibrasi source versus target; analisis komposisi trafik; ablation; biaya komputasi; kode/data tersedia; keterbatasan; halaman/section pendukung. Gunakan `not reported` atau `not verified` untuk informasi yang tidak dapat diperiksa. Jangan menebak dari judul.

Jangan menyalin skor sebagai benchmark langsung apabila protokol, data, fitur atau hardware berbeda. Jangan mengunduh atau mendistribusikan PDF berbayar secara tidak sah.

## Watchlist di luar 20 referensi inti

Dua item tambahan ada di JSON sebagai pengingat verifikasi, bukan bagian dari hitungan 20. Item yang baru muncul dari daftar pustaka belum dianggap terverifikasi.
