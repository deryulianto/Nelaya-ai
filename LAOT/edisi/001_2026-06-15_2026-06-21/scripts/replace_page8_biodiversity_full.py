from pathlib import Path

p = Path("html/laot_edisi001_15-21juni2026_working.html")
s = p.read_text(encoding="utf-8")

idx = s.find("Halaman 8")
if idx == -1:
    raise SystemExit("ERROR: teks 'Halaman 8' tidak ditemukan.")

start = s.rfind('<div class="page">', 0, idx)
end = s.find("<!-- HALAMAN 9", idx)

if start == -1 or end == -1:
    raise SystemExit("ERROR: batas halaman 8 tidak ditemukan.")

new_page8 = '''<!-- HALAMAN 8 — BIODIVERSITY WATCH -->
<div class="page">
  <div class="mini-head">
    <div class="mini-logo">L<span>A</span>OT</div>
    <div class="title">Halaman 8 — Biodiversity Watch dan Tuna Depth Layer</div>
    <div class="issue">Ecology Layer</div>
  </div>

  <div class="grid-3">
    <div class="col">
      <div class="section-label">Biodiversity Watch</div>
      <div class="hl-sub">Ekologi Laut Tidak Dibaca dari Ikan Saja</div>

      <p class="drop-cap">
        Biodiversity Watch dalam LAOT mengingatkan bahwa laut bukan hanya ruang produksi,
        tetapi juga ruang hidup. Ikan, plankton, suhu, arus, kedalaman, oksigen, dan stabilitas
        fisik laut saling terhubung. Karena itu, tanda peluang pelagis tidak boleh dibaca terpisah
        dari kondisi ekologi yang menopangnya.
      </p>

      <p>
        Dalam pembacaan mingguan, klorofil memberi petunjuk tentang produktivitas permukaan,
        tetapi klorofil bukan satu-satunya bahasa laut. Air yang tampak produktif belum tentu
        langsung berarti ikan berkumpul di sana. Arus dapat memindahkan massa air, gelombang
        dapat mengubah kelayakan operasi, dan lapisan kedalaman dapat menentukan apakah
        ikan pelagis berada dekat permukaan atau lebih turun mengikuti suhu dan mangsa.
      </p>

      <div class="panel green" style="margin-top:4mm">
        <div class="box-title">Bahasa Rubrik</div>
        <p class="small">
          “Sinyal ekologis cukup stabil” berarti kondisi pendukung terbaca ada, tetapi tetap
          perlu dipadukan dengan keselamatan, pengalaman nelayan, dan validasi lapangan.
        </p>
      </div>
    </div>

    <div class="col">
      <div class="section-label amber">Tuna Depth Layer</div>
      <div class="hl-sub">Membaca Kedalaman, Bukan Hanya Permukaan</div>

      <p>
        Tuna Depth Layer membantu LAOT membaca bahwa peluang ikan pelagis besar tidak selalu
        muncul di permukaan. Pada beberapa kondisi, tanda ekologis justru lebih bermakna ketika
        dibaca bersama kedalaman 30–100 meter, terutama saat suhu permukaan hangat dan arus
        membentuk koridor pergerakan massa air.
      </p>

      <p>
        Bagi nelayan, informasi ini tidak dimaksudkan sebagai perintah menuju satu titik. Ia lebih
        tepat dibaca sebagai pengetahuan tambahan: di mana ruang laut sedang memberi tanda,
        pada kedalaman berapa tanda itu mungkin lebih relevan, dan kapan keputusan melaut
        harus tetap dikalahkan oleh keselamatan.
      </p>

      <table class="table" style="margin-top:3mm">
        <thead>
          <tr><th>Kedalaman</th><th>Makna Baca</th></tr>
        </thead>
        <tbody>
          <tr><td>0–30 m</td><td>Sinyal permukaan, sangat dipengaruhi cuaca dan pemanasan harian.</td></tr>
          <tr><td>30–60 m</td><td>Koridor aktif pelagis tertentu; perlu dibaca bersama arus dan suhu.</td></tr>
          <tr><td>60–100 m</td><td>Lapisan bawah yang penting untuk pelagis besar dan nelayan pancing.</td></tr>
        </tbody>
      </table>

      <div class="panel amber" style="margin-top:4mm">
        <div class="box-title">Catatan Kehati-hatian</div>
        <p class="small">
          Kedalaman tidak menjamin kehadiran ikan. Ia hanya membantu mempersempit cara baca,
          agar peluang tidak disederhanakan menjadi satu angka permukaan.
        </p>
      </div>
    </div>

    <div class="col">
      <div class="section-label">Spesies Indikator</div>

      <div class="panel dark">
        <div class="box-title">Potensi Kehadiran Indikatif</div>
        <div style="font-size:8pt;line-height:1.7">
          <b>Cakalang</b> <span style="float:right;color:var(--green)">●●●○○</span><br>
          <b>Tuna sirip kuning</b> <span style="float:right;color:var(--amber)">●●●○○</span><br>
          <b>Tongkol</b> <span style="float:right;color:var(--green)">●●●●○</span><br>
          <b>Layang</b> <span style="float:right;color:var(--green)">●●●○○</span>
        </div>
        <p class="small" style="margin-top:3mm;color:white">
          Indikatif, bukan jaminan hasil. Pembacaan spesies harus digabungkan dengan musim,
          alat tangkap, pengalaman nelayan, dan catatan lapangan.
        </p>
      </div>

      <div class="panel soft" style="margin-top:4mm">
        <div class="box-title">Untuk Pembaca Umum</div>
        <p class="small">
          Halaman ini membantu pembaca melihat bahwa ikan tidak “muncul begitu saja”.
          Ia hadir karena rangkaian kondisi: makanan, suhu, arus, kedalaman, dan kestabilan
          ruang laut.
        </p>
      </div>

      <div class="ad-box" style="margin-top:4mm">
        <div>
          <div class="slot">Kolaborasi Edukasi Ekologi</div>
          <div class="name">Mitra Konservasi</div>
          <div class="desc">Literasi laut · konservasi · sekolah pesisir · validasi lapangan</div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    <div class="footer-left">Biodiversity & Tuna</div>
    <div class="footer-center">EKOLOGI · PELAGIS · KEDALAMAN</div>
    <div class="footer-right">Halaman 8</div>
  </div>
</div>

'''

s = s[:start] + new_page8 + s[end:]
p.write_text(s, encoding="utf-8")

print("OK: Halaman 8 diganti dengan narasi penuh dan bernilai.")
