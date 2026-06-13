# DÜZELTME RAPORU — DENETIM_RAPORU.md'deki 6 FAILED Bulgu

**Tarih:** 12.06.2026 · **Önceki durum:** commit `ae61a41` · **Doğrulama:**
`tests/test_duzeltmeler.py` (16 test) + denetimin sentetik Mayıs 2026 veri
setiyle uçtan uca yeniden çalıştırma (69 kontrol, 0 hata).

Her test eski kod üzerinde de çalıştırıldı (git worktree ile `ae61a41`):
eski kodda 16 testin 16'sı başarısız (1 assertion hatası + 15 özellik-yok
hatası); yeni kodda 16/16 geçiyor.

---

## FIX 1 — Ay sınırı maliyet ataması (DENETİM 2b.1 + 2b.2)

**Önce:** Label'lar `created_at` takvim ayı penceresiyle çekiliyordu; maliyet
label kesim ayına yazılıyordu. Kanıt: 30 Mayıs siparişi VW-1003'ün Haziran
label'ı (5,00$) Mayıs'tan düşmüş, 30 Nisan siparişi PM-0420'nin Mayıs label'ı
(6,00$) Mayıs'a sızmıştı.

**Sonra (`lazer/shipstation_api.py`):**
1. Ayın Order # kümesi Orders CSV'den Order Date'e göre kurulur
   (`orders_isle` artık `siparisler` sözlüğü döndürür).
2. Label'lar geniş pencereyle çekilir: ay başı −7 gün → ay sonu +45 gün
   (`_genis_pencere`; cache adları `labels_genis_*` oldu, bayat dar-pencere
   cache'i kullanılmaz).
3. Label'lar normalize Order # ile ay kümesine bağlanır; **yalnızca eşleşen
   label'lar** aya sayılır, küme dışı label'lar `ay_disi_label` sayacıyla
   raporlanır.

**Önce/sonra (sentetik Mayıs 2026):**
| Mağaza | Önce | Sonra | Doğru değer |
|---|---|---|---|
| Velvet Whiskey Design (VW-1003 dahil) | 15,00$ | **20,00$** | 20,00$ |
| Pine & Oak Studio (PM-0420 hariç) | 10,75$ | **4,75$** | 4,75$ |

Testler: `test_ileri_sinir_*`, `test_ters_sinir_*`, `test_genis_pencere_tarihleri`.

## FIX 2 — Boş Order # ciro kaybı (DENETİM 1.5)

**Önce:** Order # boş iki farklı sipariş `""` anahtarında çakışıyor, ikincinin
cirosu düşüyordu (35+45 → 35 sayılmıştı). Ayrıca negatif tutarlı tek bir boş
satır, `""`'i iptal kümesine sokup TÜM boş satırları düşürebiliyordu.

**Sonra (`lazer/shipstation_csv.py`):** Boş Order # satırları dedupe'a hiç
girmez; her satır ayrı sipariş olarak gelire sayılır, iptal işaretlemesi boş
satırlar için satır bazında yapılır. Mağaza başına `bos_order_no`
({satır sayısı, ciro}) döner ve analiz uyarısı olarak gösterilir:
*"Order # eksik: Misc Shop — 2 satır, 80.00$ ciro. Her satır ayrı sipariş
olarak sayıldı; export'u kontrol edin."* Boş satırlar ay sipariş kümesine
(`siparisler`) ve eşleşme oranına dahil edilmez.

**Önce/sonra:** Misc Shop cirosu 35,00$ → **80,00$** (iki sipariş de sayılıyor).
Testler: `TestFix2BosOrderNo` (3 test).

## FIX 3 — app.py:356 ölü yorum / Orders CSV katkısı (DENETİM 2b.8)

**Önce:** Yorum "Orders CSV'deki Order# → Store da eşleşmeye katkı verir"
diyordu ama kod yoktu; `order_store` yalnızca Shipments CSV'den doluyordu.

**Sonra (`app.py:_kargo_girdileri`):** Order#→Store eşlemesi Orders CSV (veya
sipariş özeti raporu) **∪** Shipments CSV birleşimidir. Aynı Order # için iki
kaynak farklı mağaza söylüyorsa sessizce seçilmez: Orders CSV değeri
kullanılır ve ekranda uyarı çıkar ("… çelişiyor; Orders CSV değeri kullanıldı,
veriyi kontrol edin."). Shipments CSV hiç yokken artık yalnız Orders CSV ile
eşleşme tam çalışır.

Testler: `TestFix3OrdersCsvKatkisi` (2 test).

## FIX 4 — Eşleşme oranı + eşleşmeyen sınıflandırması (DENETİM 2b.4 + 2b.5)

**Önce:** Oran ve sınıflandırma yoktu.

**Sonra:** Maliyet join'i sonrası `istatistik` döner ve 4. bölümde gösterilir:
- `eslesen/toplam_siparis` ve yüzde; **%97 altı kırmızı** bantta uyarı.
- Eşleşmeyenlerin sınıflandırması: (a) `kargolanmamis` (gönderi kaydı da yok),
  (b) `iptal_iade`, (c) `format_anomalisi` (gevşek normalizasyonla — boşluk,
  tire, büyük/küçük, Excel'in `.0` bozması — label'a oturanlar),
  (d) `aciklanamayan` (gönderi kaydı var, label yok). Kategori (d) örnek
  Order #'larıyla kırmızı kutuda listelenir ve "bu liste boşalmadan rapor
  paylaşılmamalı" notu taşır.

**Sentetik doğrulama:** 8/10 (%80, kırmızı); a={PO-4001, XX-9001},
b={LW-2002, LW-2003}, c=∅, d=∅. Testler: `TestFix4Fix5...` (3 test).

## FIX 5 — "Henüz kargolanmadı" uyarısı (DENETİM 2b.6)

**Önce:** Yoktu; kargolanmamış siparişin maliyeti sessizce eksik kalıyordu.

**Sonra:** Kategori (a) siparişleri mağaza bazında sipariş sayısı + ciro
tutarıyla listelenir ve şu banner gösterilir: *"Henüz kargolanmamış
siparişler — Kargo maliyeti eksik kalmış olabilir; birkaç gün sonra 'Cache'i
Yenile' ile tekrar çalıştırın."* Sentetik testte Pine & Oak Studio
(1 sipariş, 150$) ve mağazasız XX-9001 (40$) listelendi.

## FIX 6 — store_id eşleme zehirlenmesi (DENETİM 2.5)

**Önce:** store_id → mağaza eşlemesi tek siparişten öğrenilip kalıcı dosyaya
yazılıyordu; son yazan kazanıyordu.

**Sonra (`shipstation_api.py`):**
- Kalıcılaştırma için **≥3 bağımsız sipariş kanıtı** gerekir
  (`STORE_ID_MIN_KANIT = 3`).
- 3'ten az kanıt → `store_id_dusuk_guven`: ekranda "düşük güven" olarak
  listelenir, **Onayla** butonu (`/api/storeid/onayla`) kullanıcı onayıyla
  kalıcılaştırır.
- Aynı store_id için birden fazla mağaza kanıtı → otomatik eşleme yapılmaz,
  çelişki uyarısı çıkar.
- Mevcut kayıtla çelişen kanıt → **asla sessizce ezilmez**; "üzerine
  YAZILMADI; doğruysa eşlemeyi elle onaylayın" uyarısı çıkar.
- **"store_id Eşlemelerini Sıfırla ve Yeniden Öğren"** butonu
  (`/api/storeid/yenile`) sözlüğü silip bu ayın verisinden ≥3 kuralıyla
  yeniden kurar.

Testler: `TestFix6StoreIdOgrenme` (4 test) + uçtan uca onay/yenile endpoint testleri.

---

## Uçtan uca yeniden doğrulama (sentetik Mayıs 2026)

Tam akış (master + orders + shipments + stub API → Excel) yeniden çalıştırıldı;
**69 kontrol, 0 hata**. Regresyon yok:

- Dedupe kuruşuna kadar: 6 mağazanın Ciro/Vergi/Kargo Müşteri'si bağımsız
  pandas hesabıyla birebir (boş Order # yeni semantiğiyle).
- Excel: kolon sırası, ay başlığı, turuncu format, gerçek formüller, DIV/0
  korumalı bölmeler, ağırlıklı TOPLAM yüzdeleri, `#,##0` / `0.0%` biçimleri.
- Amazon ayrımı: 12,00$ Amazon kargosu ana tabloda değil, "RAPOR DIŞI" bölümünde.
- Kaynak seçimi (form/ShipStation) ve determinizm (iki çalıştırma hücre
  düzeyinde özdeş) korunuyor.

**Yeni toplamlar (sentetik):** CİRO 1.200 · VERGİ 94 · KARGO MÜŞTERİ 56 ·
Kargo **61,00** (önce 62,00; artık sipariş ayı bazında doğru) · KALAN **988,00**
— tamamı bağımsız hesapla birebir.

> Not: Denetimdeki UNVERIFIED maddeler (gerçek üretim CSV'leri,
> gerçek mapping dosyaları, canlı API toplamları) bu ortamda hâlâ
> doğrulanamaz; gerçek Mayıs verisiyle bir kez uçtan uca koşulmalıdır.
