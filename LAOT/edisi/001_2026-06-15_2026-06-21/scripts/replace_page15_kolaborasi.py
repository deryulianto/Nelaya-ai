from pathlib import Path

p = Path("html/laot_edisi001_15-21juni2026_working.html")
s = p.read_text(encoding="utf-8")

idx = s.find("Halaman 15")
if idx == -1:
    raise SystemExit("ERROR: teks 'Halaman 15' tidak ditemukan di HTML.")

start = s.rfind('<div class="page">', 0, idx)
if start == -1:
    raise SystemExit("ERROR: awal blok <div class=\"page\"> untuk halaman 15 tidak ditemukan.")

end = s.find("<!-- HALAMAN 16", idx)
if end == -1:
    # fallback: cari halaman berikutnya
    end = s.find('<div class="page">', idx + 20)

if end == -1:
    raise SystemExit("ERROR: batas akhir halaman 15 tidak ditemukan.")

new_page15 = '''<!-- HALAMAN 15 — KOLABORASI LAUT -->
<div class="page">
  <div class="mini-head">
    <div class="mini-logo">L<span>A</span>OT</div>
    <div class="title">Halaman 15 — Kolaborasi Laut dan Dukungan Etis</div>
    <div class="issue">Integrity Layer</div>
  </div>

  <div class="grid-3">
    <div class="col">
      <div class="section-label">Prinsip Kolaborasi</div>
      <div class="hl-sub">Dukungan Boleh Hadir, Integritas Tetap Utama</div>
      <p class="drop-cap">LAOT membuka ruang kerja bersama bagi pihak yang peduli pada laut, nelayan, keselamatan, literasi pesisir, validasi lapangan, konservasi, dan penguatan data laut Aceh.</p>

      <div class="panel green">
        <div class="box-title">Bukan Sekadar Ruang Promosi</div>
        <p class="small">Dukungan tidak membeli kesimpulan. Pembacaan data, status risiko, dan catatan redaksi tetap berdiri di atas prinsip kehati-hatian, transparansi, dan kepentingan publik.</p>
      </div>

      <div class="panel red" style="margin-top:3mm">
        <div class="box-title">Etik Redaksi</div>
        <p class="small">LAOT tidak menerima dukungan yang mendorong praktik merusak laut, klaim berlebihan, janji hasil tangkap, atau promosi yang melemahkan keselamatan nelayan.</p>
      </div>
    </div>

    <div class="col">
      <div class="section-label amber">Arah Dukungan</div>
      <p class="small" style="margin-bottom:3mm">Kolaborasi diarahkan untuk memperkuat kerja pengetahuan laut, bukan mengubah pembacaan redaksi.</p>

      <div class="list-card"><b>Keselamatan Nelayan</b><span>Pelampung, radio, lampu, P3K kapal, komunikasi risiko, dan edukasi keselamatan melaut.</span></div>
      <div class="list-card"><b>Navigasi dan Presisi</b><span>GPS, peta laut, fish finder, kompas, jam presisi, dan perangkat bantu keputusan lapangan.</span></div>
      <div class="list-card"><b>Validasi Lapangan</b><span>Trip nelayan mitra, logbook, dokumentasi, observasi pesisir, dan umpan balik dari komunitas laut.</span></div>
      <div class="list-card"><b>Literasi dan Konservasi</b><span>Pulau kecil, mangrove, sampah laut, gizi biru, sekolah pesisir, dan edukasi publik.</span></div>
    </div>

    <div class="col">
      <div class="section-label">Kontak Kolaborasi</div>
      <div class="hl-sub">Pintu Dibuka, Etika Dijaga</div>
      <p class="drop-cap">Pihak yang ingin mendukung LAOT dapat menghubungi redaksi untuk membahas bentuk kerja sama yang selaras dengan misi laut Aceh.</p>

      <table class="table">
        <thead><tr><th>Jalur</th><th>Catatan</th></tr></thead>
        <tbody>
          <tr><td>Platform</td><td>nelaya-ai.com</td></tr>
          <tr><td>Lokasi</td><td>Banda Aceh, Aceh</td></tr>
          <tr><td>Fokus</td><td>Laut, nelayan, data, keselamatan</td></tr>
          <tr><td>Status</td><td>Kolaborasi dibuka selektif</td></tr>
        </tbody>
      </table>

      <div class="pull-quote" style="margin-top:5mm">“LAOT tidak menjual kesimpulan. LAOT mengajak pihak baik ikut bekerja untuk laut.”</div>

      <p class="small" style="margin-top:4mm">Setiap bentuk dukungan akan dicatat secara terbuka bila relevan, tanpa memengaruhi hasil pembacaan data dan keputusan redaksi.</p>
    </div>
  </div>

  <div class="footer">
    <div class="footer-left">Kolaborasi Laut</div>
    <div class="footer-center">DUKUNGAN BOLEH HADIR, INTEGRITAS TETAP UTAMA</div>
    <div class="footer-right">Halaman 15</div>
  </div>
</div>

'''

s = s[:start] + new_page15 + s[end:]
p.write_text(s, encoding="utf-8")

print("OK: halaman 15 berhasil diganti penuh menjadi halaman Kolaborasi Laut.")
