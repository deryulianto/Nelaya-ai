from pathlib import Path

p = Path("html/laot_edisi001_15-21juni2026_working.html")
s = p.read_text(encoding="utf-8")

page17 = '''
<!-- HALAMAN 17 — SUARA UNTUK LAOT -->
<div class="page">
  <div class="mini-head">
    <div class="mini-logo">L<span>A</span>OT</div>
    <div class="title">Halaman 17 — Suara untuk LAOT</div>
    <div class="issue">Closing Voices</div>
  </div>

  <div class="grid-3">
    <div class="col">
      <div class="section-label">Pengantar</div>
      <div class="hl-sub">Apresiasi untuk Edisi Perdana</div>

      <p class="drop-cap">
        LAOT lahir bukan hanya sebagai tabloid data laut, tetapi sebagai ikhtiar membaca laut Aceh
        dengan lebih jernih, lebih berurutan, dan lebih bertanggung jawab. Edisi perdana ini kami
        sambut dengan syukur, sekaligus dengan ucapan, harapan, dan doa dari berbagai kalangan
        yang percaya bahwa laut layak dibaca dengan ilmu, rasa, dan kepedulian.
      </p>

      <div class="panel green" style="margin-top:4mm">
        <div class="box-title">Nada Halaman Ini</div>
        <p class="small">
          Halaman ini memuat suara apresiasi, harapan, dan dukungan moral dari berbagai kalangan
          atas terbitnya LAOT Edisi Perdana.
        </p>
      </div>

      <div class="pull-quote" style="margin-top:6mm">
        “Semoga LAOT menjadi ruang baca yang membantu laut dipahami dengan lebih utuh,
        lebih manusiawi, dan lebih bertanggung jawab.”
      </div>

      <div class="panel amber" style="margin-top:5mm">
        <div class="box-title">Catatan Redaksi</div>
        <p class="small">
          Nama, jabatan, afiliasi, dan kutipan pada halaman ini akan dilengkapi setelah seluruh
          ucapan/apresiasi diterima dan dikonfirmasi oleh redaksi.
        </p>
      </div>
    </div>

    <div class="col">
      <div class="section-label amber">Suara & Apresiasi</div>

      <div class="list-card">
        <b>[Nama Tokoh 1]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau apresiasi singkat. Ideal 2–4 kalimat. Tekankan harapan terhadap literasi laut, keselamatan nelayan, data, atau masa depan pesisir Aceh.]”</span>
      </div>

      <div class="list-card">
        <b>[Nama Tokoh 2]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau apresiasi singkat. Hindari kalimat terlalu panjang agar halaman tetap rapi dan mudah dibaca.]”</span>
      </div>

      <div class="list-card">
        <b>[Nama Tokoh 3]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau apresiasi singkat. Bisa berasal dari akademisi, tokoh laut, pemerintah, komunitas, atau mitra sosial.]”</span>
      </div>
    </div>

    <div class="col">
      <div class="section-label">Harapan & Doa</div>

      <div class="list-card">
        <b>[Nama Tokoh 4]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau harapan singkat. Sebaiknya bernada tulus, tidak terlalu promosi, dan tetap berpihak pada laut serta masyarakat pesisir.]”</span>
      </div>

      <div class="list-card">
        <b>[Nama Tokoh 5]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau doa singkat. Bisa menekankan agar LAOT terus menjaga kejujuran data, kehati-hatian, dan manfaat publik.]”</span>
      </div>

      <div class="list-card">
        <b>[Nama Tokoh 6]</b>
        <span><i>[Jabatan / Afiliasi]</i></span>
        <span>“[Isi ucapan atau apresiasi singkat. Bila testimoni yang masuk lebih dari enam, pilih yang paling mewakili ragam kalangan.]”</span>
      </div>

      <div class="panel soft" style="margin-top:5mm">
        <div class="box-title">Penutup</div>
        <p class="small">
          Kepada semua pihak yang memberi dukungan, perhatian, dan doa: terima kasih.
          Semoga LAOT tetap tumbuh sebagai ruang baca laut Aceh yang jujur, berguna,
          dan berpihak pada keselamatan, pengetahuan, dan martabat kehidupan pesisir.
        </p>
      </div>
    </div>
  </div>

  <div class="footer">
    <div class="footer-left">Suara untuk LAOT</div>
    <div class="footer-center">APRESIASI · HARAPAN · DOA</div>
    <div class="footer-right">Halaman 17</div>
  </div>
</div>
'''

if "Halaman 17 — Suara untuk LAOT" in s:
    print("Halaman 17 sudah ada. Tidak ditambahkan ulang.")
else:
    if "</body>" in s:
        s = s.replace("</body>", page17 + "\n</body>", 1)
    else:
        s = s + "\n" + page17

    p.write_text(s, encoding="utf-8")
    print("OK: Halaman 17 — Suara untuk LAOT berhasil ditambahkan.")
