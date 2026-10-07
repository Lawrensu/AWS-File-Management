---
filename: 07-sop-insiden-keselamatan-siber.md
doc_type: sop
department: Jabatan Teknologi Maklumat
lang: ms
year: 2023
supersedes: []
scanned: false
---

# SOP/TM/2023/05: Prosedur Pengendalian Insiden Keselamatan Siber

**No. Dokumen:** SOP/TM/2023/05
**Versi:** 1.1
**Tarikh Berkuat Kuasa:** 1 September 2023
**Pemilik:** Jabatan Teknologi Maklumat, Jabatan Pembangunan Digital Sarawak

## 1. Tujuan

1.1 Prosedur Operasi Standard (SOP) ini menetapkan langkah-langkah pelaporan, pengawalan dan pemulihan insiden keselamatan siber di Jabatan Pembangunan Digital Sarawak.

## 2. Skop

2.1 SOP ini terpakai kepada semua pegawai dan kakitangan, kontraktor serta pembekal yang menggunakan sistem maklumat, rangkaian atau data Jabatan.

## 3. Klasifikasi Insiden

3.1 Tahap 1 (Rendah): percubaan e-mel pancingan data (phishing) yang tidak diklik, imbasan port daripada luar.

3.2 Tahap 2 (Sederhana): akaun pengguna dikompromi, jangkitan perisian hasad (malware) pada satu komputer.

3.3 Tahap 3 (Tinggi): kebocoran data peribadi, serangan ransomware, atau gangguan sistem kritikal melebihi dua (2) jam.

## 4. Prosedur

Langkah 1. Pelaporan. Pengguna yang mengesyaki insiden hendaklah melapor kepada Meja Bantuan ICT melalui sambungan 4000 atau e-mel siber@jpds.example.my dalam tempoh satu (1) jam. Borang Laporan Insiden (Borang TM-09) hendaklah dilengkapkan dalam tempoh 24 jam.

Langkah 2. Penilaian awal. Pegawai Meja Bantuan menetapkan tahap insiden dalam tempoh 30 minit dan memaklumkan Pegawai Keselamatan ICT (ICTSO).

Langkah 3. Pengasingan. Pasukan Tindak Balas Insiden Komputer (CERT Jabatan) mengasingkan sistem atau akaun terjejas daripada rangkaian dalam tempoh dua (2) jam bagi insiden Tahap 2 dan Tahap 3.

Langkah 4. Eskalasi. Insiden Tahap 3 dimaklumkan kepada Pengarah Jabatan dalam tempoh empat (4) jam dan kepada Pusat Keselamatan Siber Negeri dalam tempoh 24 jam.

Langkah 5. Pemulihan. Pasukan CERT memulihkan sistem daripada sandaran (backup) terkini yang bersih. Sandaran harian disimpan selama 30 hari dan sandaran mingguan selama 12 bulan.

Langkah 6. Semakan selepas insiden. ICTSO menyediakan Laporan Selepas Insiden dalam tempoh tujuh (7) hari bekerja, mengandungi punca, kesan dan tindakan pencegahan.

## 5. Tempoh Tindak Balas

5.1 Tahap 1: dikendalikan dalam tempoh satu hari bekerja.

5.2 Tahap 2: tindak balas dalam tempoh empat (4) jam, pemulihan dalam tempoh dua (2) hari bekerja.

5.3 Tahap 3: tindak balas serta-merta, pemulihan sasaran dalam tempoh 24 jam.

## 6. Jadual Tanggungjawab

| Peranan | Tanggungjawab |
|---|---|
| Pengguna | Lapor insiden dalam 1 jam |
| Pegawai Meja Bantuan | Nilai dan klasifikasi insiden |
| Pegawai Keselamatan ICT (ICTSO) | Selaras dan sediakan laporan |
| CERT Jabatan | Asing, siasat dan pulih sistem |
| Pengarah Teknologi Maklumat | Luluskan komunikasi kepada pihak luar |
| Pengarah Jabatan | Dimaklumkan bagi Tahap 3 |

## 7. Rekod

7.1 Semua borang dan laporan insiden disimpan dalam Daftar Insiden Keselamatan selama lima (5) tahun.

7.2 Statistik insiden dilaporkan kepada Jawatankuasa Pemandu ICT setiap suku tahun.

## 8. Sejarah Semakan

- Versi 1.0: 3 Mac 2022
- Versi 1.1: 1 September 2023, menambah klasifikasi Tahap 3 bagi ransomware
