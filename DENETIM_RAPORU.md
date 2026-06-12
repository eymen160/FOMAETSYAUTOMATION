# DENETİM RAPORU — Lazer Grubu Ay Sonu Rapor Otomasyonu

**Denetim tarihi:** 12.06.2026 · **Denetlenen sürüm:** commit `ae61a41`
**Denetçi rolü:** Bağımsız denetim; geliştiricinin hiçbir varsayımına güvenilmedi, tüm değerler ham veriden yeniden hesaplandı.

> **GÜNCELLEME (12.06.2026):** Aşağıdaki 6 FAILED bulgunun tamamı giderildi;
> önce/sonra kanıtları ve testler için **DUZELTME_RAPORU.md**'ye bakın.
> Bölüm gövdeleri tarihsel kanıt olarak DEĞİŞTİRİLMEDİ; güncel durumlar özet
> tabloda ve her başlıkta "GİDERİLDİ" notuyla işaretlidir. UNVERIFIED
> maddeler (gerçek üretim verisi gerektirenler) hâlâ geçerlidir.

## 0. Denetimin kapsamı ve KRİTİK SINIRLAMA

Depo yalnızca **uygulama kodunu** içeriyor. Denetim talimatında adı geçen gerçek veri
dosyalarının **hiçbiri depoda yok**: `shipstation_orders.csv`, `shipstation_shipments.csv`,
`store_mapping.json`, `store_id_mapping.json`, master Excel, `cache/` içeriği, üretilmiş
nihai Excel ve `.env`. Bunlar `.gitignore` ile bilinçli olarak dışarıda tutuluyor
(güvenlik açısından doğru bir karar; bkz. Bölüm 6).

Bu nedenle denetim iki katmanda yapıldı:

1. **Mekanizma denetimi (yapıldı):** Mayıs 2026 için, talimattaki tüm uç durumları içeren
   sentetik veri seti üretildi (çok kalemli sipariş, iptal/negatif sipariş, boş Order #,
   boş Store, ay sınırı siparişleri, voided label, aynı shipment'a çoklu label, Amazon
   mağazası, boşluklu mağaza adı, adet=0 mağaza). Uygulamanın **gerçek Flask uç noktaları**
   üzerinden tam akış çalıştırıldı, üretilen Excel openpyxl ile hücre hücre doğrulandı.
   Sonuç: **81 kontrol PASSED, 6 bulgu FAILED, 3 WARNING.**
2. **Gerçek veri denetimi (yapılamadı):** Gerçek Mayıs ayı CSV'leri, gerçek
   `store_mapping.json` / `store_id_mapping.json` ve canlı ShipStation API erişimi bu
   ortamda bulunmadığından, gerçek tutarların doğrulanması gereken her madde **UNVERIFIED**
   olarak işaretlendi. Bu maddeler "muhtemelen doğrudur" diye GEÇİRİLMEDİ.

---

## 1. Veri bütünlüğü kontrolleri — **FAILED (1 hata) + UNVERIFIED (gerçek dosya yok)**

> **GİDERİLDİ:** 1.5'teki boş Order # bulgusu FIX 2 ile düzeltildi (DUZELTME_RAPORU.md).

### 1.1 Gerçek `shipstation_orders.csv` istatistikleri — UNVERIFIED
Dosya depoda yok; toplam satır / benzersiz Order # / benzersiz Store sayıları ve sipariş içi
alan tutarlılığı gerçek veride doğrulanamadı.

### 1.2 Dedupe doğrulaması (bağımsız yeniden hesap) — PASSED (mekanizma)
Sentetik orders CSV'si pandas `drop_duplicates("Order #")` ile bağımsız hesaplandı ve
uygulamanın (`lazer/shipstation_csv.py:129-153`) çıktısıyla mağaza bazında **kuruşuna kadar**
karşılaştırıldı. 6 mağazanın tamamında Ciro / Vergi / Kargo Müşteri birebir eşleşti.

### 1.3 Çift sayım testi (5+ kalemli sipariş) — PASSED
`VW-1001` siparişi 5 satır (5 kalem), her satırda Order Total=250 tekrarlanıyor.
Satır izleme: yalnızca **ilk satırda** `ciro_order_total += 250` çalışıyor
(`siparis_gorulen` sözlüğü, shipstation_csv.py:143-147); mağaza cirosu 430 = 250+100+80
çıktı, 5×250 değil. Sipariş tutarı nihai toplama **tam olarak BİR kez** giriyor. Quantity
ise her satırdan toplanıyor (doğru: adet 8).

### 1.4 Tarih kapsaması — PASSED (mekanizma) / kısmen eksik
- min/max tarih kontrolü ve "ay tam kapsanmıyor" uyarısı var ve sentetik testte doğru çalıştı
  (shipstation_csv.py:155-167).
- **WARNING:** Talimattaki "ilk/son 3 günde şüpheli düşük sipariş sayısı" kontrolü
  uygulamada YOK; export ayın 1'i ve son gününden birer satır içeriyorsa ortası kesik olsa
  bile uyarı çıkmaz. Gün bazında dağılım kontrolü önerilir.

### 1.5 Sorunlu satırlar — 1 FAILED, 1 WARNING
| Durum | Uygulamanın davranışı | Sonuç |
|---|---|---|
| Negatif tutar (`LW-2003`, −30) | Sipariş tamamen hariç + "İptal/negatif" listesinde gösteriliyor | PASSED |
| İptal statüsü (`LW-2002`) | Tamamen hariç + listede | PASSED |
| Quantity = 0 satırı | Adede 0 ekleniyor, sipariş tutarı normal sayılıyor | PASSED |
| Boş Store | `""` adlı mağazada toplanıyor; eşleşmeyenler listesinde `''` olarak görünüyor ama kolayca gözden kaçar | WARNING |
| **Boş Order #** | **FAILED — VERİ KAYBI RİSKİ:** Order # boş olan İKİ FARKLI sipariş (35$ ve 45$) aynı `""` anahtarında birleşiyor; dedupe mantığı ikinci siparişin Order Total/Tax/Shipping değerlerini **tamamen düşürüyor**. Testte 80$ yerine 35$ sayıldı. | **FAILED** |

**Düzeltme önerisi (1.5):** `shipstation_csv.py:135-147`'de `ono` boşsa dedupe'a sokmadan
her satırı ayrı sipariş gibi saymak (veya bu satırları "bozuk satır" listesine alıp kullanıcıya
göstermek). Boş Store satırları için açık bir uyarı eklenmeli.

---

## 2. ShipStation API / kargo maliyeti kontrolleri — PASSED (mekanizma) + UNVERIFIED (gerçek veri) + 1 FAILED

> **GİDERİLDİ:** 2.5'teki store_id tek-sipariş riski FIX 6 ile düzeltildi (≥3 kanıt + onay akışı).

### 2.1 API label sayısı vs shipments CSV — UNVERIFIED
Canlı API ve gerçek CSV yok; %2 fark analizi yapılamadı.

### 2.2 Voided label'ların hariç tutulması — PASSED (somut örnekle)
Sentetik testte `S1` shipment'ının voided kopyası (8.50$) maliyete **girmedi**; geçerli
label sayıldı, `voided=1` sayacı arayüze raporlandı (`shipstation_api.py:116-119,128-131`).

### 2.3 Çoklu label → hangisi sayıldı — PASSED
`S2` shipment'ında 7.00$ (10:00) ve 6.50$ (12:00) iki geçerli label: `created_at`'e göre
**en yenisi (6.50$)** sayıldı (shipstation_api.py:133-136). ISO-8601 string karşılaştırması
kronolojik sıralamayla tutarlı.

### 2.4 3 mağazanın label toplamı vs uygulamanın Kargo değeri — PASSED (sentetik) / UNVERIFIED (gerçek)
Sentetik API üzerinde Velvet (8.50+6.50=15.00), Crafty (10.00+5.25=15.25), Pine & Oak
(4.75+6.00=10.75) elle toplandı; uygulamanın `magaza_kargo` çıktısıyla birebir eşleşti.
Gerçek API ile aynı test UNVERIFIED.

### 2.5 `store_id_mapping.json` doğrulaması — UNVERIFIED + **FAILED (tasarım riski)**
Gerçek dosya yok. Ancak kod denetimi ciddi bir risk gösterdi
(`shipstation_api.py:211-215`): store_id → mağaza eşleşmesi **tek bir siparişten otomatik
öğreniliyor ve kalıcı dosyaya yazılıyor**; aynı store_id için son yazan kazanıyor, "düşük
güven" işareti yok. Tek bir hatalı Order#→Store kaydı eşlemeyi kalıcı olarak zehirleyebilir
ve sonraki TÜM ayların kargo dağılımını saptırır.
**Düzeltme:** store_id eşlemesini en az 5 bağımsız siparişle teyit etmeden kalıcılaştırmamak;
1 siparişe dayananları arayüzde "düşük güven — elle onaylayın" olarak göstermek.

---

## 2b. Tarih uyuşmazlığı ve Order # eşleştirme — **FAILED (denetimin en kritik bölümü)**

> **GİDERİLDİ:** 2b.1–2b.2 FIX 1, 2b.4–2b.6 FIX 4/5, 2b.8 FIX 3 ile düzeltildi (DUZELTME_RAPORU.md).

### 2b.1 Ay sonu (ileri) sınır testi — **FAILED**
Talimat gereği ay sonunda verilen siparişin kargo maliyeti, label sonraki ay kesilse bile
**sipariş ayına** yazılmalı. Uygulama bunu YAPMIYOR: label'lar `created_at` ile takvim ayı
penceresinde çekiliyor (`shipstation_api.py:90-95`).
**Kanıt:** 30.05.2026 tarihli `VW-1003` siparişinin label'ı 02.06.2026'da kesildi → Mayıs
penceresine girmedi, Velvet'in Mayıs Kargo'su 5.00$ **eksik** çıktı. Üstelik shipments CSV
de Ship Date ile filtrelendiği için bu siparişin Order#→Store eşleşmesi de düşüyor.

### 2b.2 Ters sınır testi — **FAILED**
30.04.2026 tarihli `PM-0420` siparişinin label'ı 02.05.2026'da kesildi → maliyeti (6.00$)
**Mayıs'a sızdı**: Pine & Oak Mayıs Kargo = 10.75$ (4.75 Mayıs + 6.00 Nisan siparişi).
Yani maliyetler "sipariş ayı" değil "label kesim ayı" bazında. İki yön birbirini kısmen
telafi etse de mağaza bazında para dağılımını bozar (yukarıdaki örnekte Velvet 5.00$
zarara, Pine & Oak 6.00$ fazla yüke uğruyor).
**Düzeltme (2b.1+2b.2):** Label'ları sipariş ayının ±1 ay penceresiyle çekip her label'ı
Order # üzerinden **siparişin tarihine** göre aya atamak; shipments CSV'yi de Ship Date değil
Order Date kapsamıyla almak ya da iki ayın shipments'ını birleştirmek.

### 2b.3 Order # normalizasyonu — PASSED
Üç kaynakta da Order # string olarak okunup `strip()` ediliyor (CSV: shipstation_csv.py:195,
API: shipstation_api.py:198 `str(...).strip()`); int/string tip farkı oluşmuyor. 10 sentetik
siparişin tamamı üç kaynak arasında birebir eşleşti. **WARNING:** CSV bir kez Excel'de açılıp
kaydedilirse sayısal Order #'lar `"12345.0"` biçimine dönüp eşleşme kaybedebilir; uygulamada
buna karşı normalizasyon yok (ham export kullanıldığı sürece sorun değil).

### 2b.4 Eşleşme oranı — **FAILED (özellik yok)**
Uygulama Order # eşleşme oranını HİÇ hesaplamıyor/raporlamıyor; yalnızca eşleşmeyen label
maliyet toplamını gösteriyor. Bağımsız hesap (sentetik): 10 benzersiz Mayıs siparişinden
7'si label'lı (%70). Karşılaştırılacak uygulama değeri yok.

### 2b.5 Eşleşmeyen siparişlerin sınıflandırması — **FAILED (özellik yok)**
(a) henüz kargolanmadı / (b) iptal-iade / (c) format hatası / (d) açıklanamayan ayrımı
uygulamada yok. Bağımsız sınıflandırma (sentetik): `PO-4001` → (a) kargolanmamış,
`VW-1003` → ay sınırı (2b.1 hatası), `XX-9001` → boş Store. Gerçek veride (d) kategorisinin
sıfır olduğu **kanıtlanamaz** durumda → talimat gereği FAILED.

### 2b.6 "Henüz kargolanmadı" uyarısı — **FAILED (özellik yok)**
Label'ı/gönderisi olmayan `PO-4001` için hiçbir uyarı üretilmedi. Böyle bir uyarı kodda yok.

### 2b.7 Tarih ayrıştırma (AA/GG karışması) — PASSED
`_tarih()` önce `%m/%d/%Y` deniyor (shipstation_csv.py:50-64). Test: `05/01/2026` → 1 Mayıs,
`05/12/2026` → 12 Mayıs, `05/14/2026 10:30 AM` → 14 Mayıs. Gün/ay karışması yok.
**WARNING:** API tarih penceresi UTC (`Z`); hesap saat dilimi farklıysa ay sınırındaki birkaç
label kayabilir.

### 2b.8 EK BULGU — ölü kod/yorum — **FAILED**
`app.py:356`'daki yorum "Orders CSV'deki Order# → Store da eşleşmeye katkı verir" diyor ama
**böyle bir kod yok**; `order_store` yalnızca shipments CSV'den dolduruluyor (app.py:354-355).
Shipments CSV yüklenmemişse veya eksikse label'lar yalnızca store_id sözlüğüne düşer →
eşleşme oranı gereksiz yere düşük kalır. **Düzeltme:** Orders CSV'den Order#→Store eşlemesini
de `order_store`'a eklemek (yorumun vaat ettiği davranış).

---

## 3. Mağaza eşleştirme kontrolleri — PASSED (mekanizma) + UNVERIFIED (gerçek dosya) + 1 WARNING

- Gerçek `store_mapping.json` depoda yok → mevcut eşleşmelerin listesi ve skor denetimi UNVERIFIED.
- **Fuzzy eşik — WARNING:** Otomatik öneri eşiği 90 değil **85** (`eslestirme.py:79`).
  85–89 skorlular ayrıca "elle teyit gerekli" diye işaretlenmiyor. Hafifletici: öneriler
  otomatik UYGULANMIYOR; rapora yalnızca kullanıcının kaydettiği eşleşmeler girer
  (`_ss_master_bazinda` sadece `eslestirme.yukle()` kullanır). Yine de eşiğin 90'a
  çekilmesi/ara bandın işaretlenmesi önerilir.
- İki yönlü eksik listeleri (ShipStation'da var↔formu yok) arayüzde üretiliyor; testte
  `Misc Shop` ve form-only mağazalar doğru listelendi. PASSED.
- **Amazon sızıntısı — PASSED (toplamla kanıtlı):** Amazon mağazası nihai Excel'in ana
  tablosuna girmedi; ana tablo Kargo toplamı 62.00$ = 6 mağazanın bağımsız toplamı; Amazon'un
  12.00$'ı yalnızca "RAPOR DIŞI (AMAZON)" bölümünde. Dikkat: koruma ada "amazon" geçmesine
  dayalı; kullanıcı bir Amazon mağazasını elle bir master mağazaya eşlerse sızar (eşleme
  sözlüğü amazon kontrolünden önce bakılıyor, app.py:277-279).
- **Boşluklu adlar — PASSED:** CSV'de `" Velvet Whiskey Design"` (baştaki boşlukla) doğru
  mağazada toplandı; `kaydet()` anahtarları da strip ediyor.

---

## 4. Formül ve Excel çıktısı — **PASSED (tam doğrulama)**

Üretilen `Lazer_Grubu_Rapor_2026_MAYIS.xlsx` openpyxl ile açıldı; tüm formüller bağımsız bir
değerlendiriciyle sayısal olarak hesaplandı (bu ortamdaki LibreOffice xlsx açamadığı için):

- **KALAN = CİRO − VERGİ − REKLAM − Kargo:** 6 satırın tamamında doğrulandı
  (örn. Velvet: 430−34−25−15=356 ✓). İLAVE ÖDEME formülde yok — şablonla tutarlı.
- **Türetilmiş kolonlar (tolerans 0.01):** Parça başı ciro 53.75, Kargo pb ödenen 2.375,
  Kargo pb kalan (19−15)/8=0.50, %REKLAM 5.81%, %VERGİ 7.91%, Parça başı kalan 44.50 —
  hücre değerleriyle birebir.
- **Gerçek formül mü:** Evet; tüm bölme/KALAN/yüzde hücreleri Excel formülü
  (`=IF(N(K3)=0,"",B3/K3)`, `=B3-D3-E3-I3` vb.), hardcode değil.
- **#DIV/0! taraması:** adet=0 olan "Zero Parts Co" satırında tüm bölme hücreleri boş ("")
  döndü; sayfada tek bir hata hücresi yok.
- **TOPLAM satırı:** `=SUM()` aralıkları doğru; bağımsız toplamlarla eşleşti (Ciro 1200,
  Vergi 94, Reklam 57, KM 56, Kargo 62, Adet 21, İlave 12, KALAN 987). Yüzde kolonları
  **ağırlıklı** (E_toplam/B_toplam = %4.75; naif toplam %28.3 olurdu).
- **Kolon sırası / biçim:** 17 kolon başlığı koddaki şablon listesiyle birebir; ay başlık
  satırı ("MAYIS 2026") ve turuncu (FF9900) başlık dolgusu mevcut; para `#,##0`, yüzde
  `0.0%`. *(Ekibin orijinal şablon dosyası depoda olmadığından "gerçek şablonla" birebir
  karşılaştırma UNVERIFIED; karşılaştırma README'deki şablon tanımına göre yapıldı.)*

---

## 5. Denetim modu (form vs ShipStation) — **PASSED**

- **Sapma yüzdeleri ve renkler:** Bağımsız hesapla birebir: Velvet |520−430|/520=%17.3 →
  kırmızı; Crafty %6.45 → sarı; Lazer Wood Art %4.0 → yeşil. Eşikler kodda tam talimattaki
  gibi: sarı >%5, kırmızı >%15 (`denetim.py:2-3`). Sapma tabanı `max(|form|,|ss|)`.
- **Reklam ve İlave Ödeme:** Her zaman formdan; kaynak seçiminden etkilenmiyor
  (`app.py:442-443`, testle doğrulandı).
- **Kaynak seçimi gerçekten uygulanıyor:** `ciro=form` seçilince Velvet CİRO hücresi 430
  (ShipStation) yerine 520 (form) yazıldı; varsayılanda 430. ShipStation verisi olmayan
  mağazalarda (Sunset Decor) otomatik form'a düşülüyor.

---

## 6. Güvenlik ve sağlamlık — **PASSED + 2 WARNING**

- **API anahtarı:** Kod tabanında hardcoded anahtar yok (regex taraması temiz); anahtar
  yalnızca `.env`/ortam değişkeninden okunur. 401 hata mesajında anahtar sızmıyor (testle
  doğrulandı); uygulama log dosyası yazmıyor.
- **.gitignore:** `.env`, `*.csv`, `*.xlsx` + `cache/`, `store_mapping.json`,
  `store_id_mapping.json` hepsi mevcut. PASSED.
- **Bozuk girdiler (hepsi Türkçe mesaj, çökme yok):** boş CSV ✓, yanlış kolonlu CSV
  (kolon listesiyle açıklayıcı hata) ✓, 0 satırlı ay ✓ ("Master'da Mart 2026 dönemi için
  form yanıtı bulunamadı."), API 401 ✓, API 429 (üstel bekleme ile 5 deneme sonrası Türkçe
  mesaj) ✓, dosya adı path traversal denemesi etkisiz ✓.
- **WARNING:** UTF-8 olmayan dosya latin-1 ile sessizce okunuyor — çökme yok ama Türkçe/özel
  karakterli mağaza adları bozulup eşleşmeyi düşürebilir; kullanıcıya "kodlama farklı"
  uyarısı gösterilmesi önerilir.
- **Determinizm:** Aynı ay iki kez hesaplandı; üretilen iki Excel hücre düzeyinde özdeş
  (SHA-256 parmak izi eşit). Cache deterministik; ancak **WARNING:** cache varken API'ye
  gidilmediği için ay içinde veri değiştiyse "Cache'i Yenile" basılmadan rapor eski kalır.

---

## 7. Uçtan uca kabul testi (Mayıs 2026) — mekanik PASSED / gerçek veri UNVERIFIED

Tam akış (master.xlsx + orders CSV + shipments CSV + API) gerçek Flask uç noktaları
üzerinden çalıştırıldı. Gerçek üretim verisi bulunmadığından sayılar sentetik settendir;
gerçek Mayıs raporunun kabulü **UNVERIFIED**.

| | Uygulama | Bağımsız hesap | Fark |
|---|---|---|---|
| Rapordaki mağaza | 6 | 6 | — |
| Formdaki mağaza | 6 | 6 | — |
| ShipStation mağazası | 7 (5 eşleşik + Misc Shop + Amazon) | 7 | — |
| CİRO | 1.200,00 | 1.200,00 | 0 |
| VERGİ | 94,00 | 94,00 | 0 |
| KARGO MÜŞTERİ | 56,00 | 56,00 | 0 |
| Kargo | 62,00 | 62,00* | 0* |
| KALAN | 987,00 | 987,00* | 0* |

\* Mutabakat "label kesim ayı" tanımına göredir. "Sipariş ayı" tanımına göre doğru Kargo
61,00$ olurdu (VW-1003'ün 5,00$'ı dahil, PM-0420'nin 6,00$'ı hariç) → bölüm 2b'deki FAILED.

**Tespit edilen TÜM uyumsuzluklar ve kök nedenleri:**
1. Velvet Mayıs Kargo 5,00$ eksik — kök neden: label'lar `created_at` takvim ayıyla çekiliyor (2b.1).
2. Pine & Oak Mayıs Kargo 6,00$ fazla — kök neden: Nisan siparişinin Mayıs label'ı sızıyor (2b.2).
3. Misc Shop cirosu 45,00$ eksik — kök neden: boş Order # dedupe çakışması (1.5).
4. Orders CSV'nin Order#→Store katkısı yok — kök neden: app.py:356 ölü yorum/eksik kod (2b.8).

**Önceden belirsiz kalemlerin güncel durumu:**
- **"P" kolonu (J):** Bilinçli olarak boş bırakılıyor (`rapor.py:94` — "kararla boş");
  testte tüm satırlarda boş doğrulandı. Şablon uyumu için bu kararın ekiple yazılı teyidi önerilir.
- **"Kargo parça başı ort kalan":** `=(KARGO MÜŞTERİ − Kargo) ÷ PARÇA ADEDİ` olarak
  uygulanmış (`rapor.py:101`); README'deki tanımla tutarlı, sayısal doğrulaması yapıldı.

---

## ÖZET TABLO

| Bölüm | İlk durum (ae61a41) | Güncel durum (düzeltme sonrası) |
|---|---|---|
| 1. Veri bütünlüğü | **FAILED** (boş Order # veri kaybı) + UNVERIFIED | **GİDERİLDİ** (FIX 2) + UNVERIFIED (gerçek CSV yok) |
| 2. API / kargo maliyeti | PASSED (mekanizma) + **FAILED** (store_id riski) + UNVERIFIED | **GİDERİLDİ** (FIX 6) + UNVERIFIED |
| 2b. Tarih / Order # eşleştirme | **FAILED** (ay sınırı ×2, oran/sınıflandırma/uyarı yok, app.py:356) | **GİDERİLDİ** (FIX 1, 3, 4, 5) |
| 3. Mağaza eşleştirme | PASSED + WARNING (eşik 85<90) + UNVERIFIED | değişmedi (WARNING sürüyor) |
| 4. Formüller / Excel | **PASSED** | PASSED (regresyon yok, yeniden doğrulandı) |
| 5. Denetim modu | **PASSED** | PASSED |
| 6. Güvenlik / sağlamlık | **PASSED** (+2 WARNING) | PASSED |
| 7. Uçtan uca (gerçek Mayıs 2026) | **UNVERIFIED** | UNVERIFIED (gerçek veri hâlâ bu ortamda yok) |

## KARAR

**İlk karar (ae61a41):** Bu rapor ekiple paylaşılmaya hazır DEĞİLDİR — şu 6 madde
düzeltilmeden paylaşmayın: (1) kargo maliyetinin sipariş ayına atanması [2b.1],
(2) önceki ay siparişlerinin maliyet sızıntısı [2b.2], (3) boş Order # veri kaybı [1.5],
(4) Orders CSV'nin Order#→Store eşleşmesine katılması [app.py:356], (5) eşleşme oranı +
eşleşmeyen sipariş sınıflandırması ve "henüz kargolanmadı" uyarısı [2b.4–2b.6],
(6) store_id eşlemesinin tek siparişten kalıcılaştırılmaması [2.5].

**Güncel karar:** 6 maddenin tamamı giderildi ve sentetik veri setiyle uçtan uca
yeniden doğrulandı (69 kontrol, 0 hata; ayrıntı: DUZELTME_RAPORU.md). Uygulama,
**gerçek Mayıs 2026 verisiyle bir kez uçtan uca koşulup eşleşme oranı ve
"açıklanamayan" listesi temiz çıktıktan sonra** ekiple paylaşılmaya hazırdır.
