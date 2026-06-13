# Lazer Grubu — Ay Sonu Raporu Otomasyonu

30+ Etsy mağazasının aylık form beyanlarını ShipStation gerçek verisiyle
eşleştirip denetleyen ve ekibin ay sonu Excel raporunu otomatik üreten
lokal web uygulaması. Tüm işlem bilgisayarınızda yapılır; veri hiçbir dış
servise gönderilmez (ShipStation API çağrıları hariç).

## Kurulum

1. Python 3.11+ kurulu olmalı.
2. Bağımlılıkları kurun:
   ```
   pip install -r requirements.txt
   ```
3. Proje klasörüne `.env` dosyası oluşturun:
   ```
   SHIPSTATION_API_KEY=buraya_api_anahtariniz
   ```
   > `.env`, `*.csv` ve `*.xlsx` dosyaları `.gitignore`'dadır; müşteri
   > verisi ve API anahtarı asla git'e girmez.
4. Uygulamayı başlatın:
   ```
   python app.py
   ```
   Tarayıcıda `http://127.0.0.1:5000` açılır.

> **Lokal çalışma hiç değişmedi.** `DATA_DIR` ve `APP_PASSWORD` ortam
> değişkenleri tanımlı olmadığında uygulama tam olarak eskisi gibi davranır:
> dosyalar proje klasörüne yazılır ve giriş parolası sorulmaz (yalnızca
> `127.0.0.1`'e bağlanılır). Aşağıdaki Render ayarları yalnızca sunucuya
> kurulum içindir.

## Sunucuya kurulum (Render — kalıcı diskli)

Uygulama öğrendiği eşlemeleri (`store_mapping.json`, `store_id_mapping.json`)
ve API cache'ini (`cache/`) diske yazar; bu durum aylar boyunca birikir. Bu
yüzden **kalıcı diskli, kalıcı-sunucu** bir host gerekir — sunucusuz
(serverless) platformlar bu dosyaları her çağrıda siler. Render bu iş için
uygundur.

Repoda hazır bir **`render.yaml`** Blueprint'i vardır; Render'da
**New → Blueprint** ile repoyu bağladığınızda aşağıdaki ayarlar otomatik gelir.
Elle kurmak isterseniz panelden şu değerleri girin:

1. **Servis tipi:** Web Service · **Runtime:** Python · **Plan:** Starter ya
   da üzeri. *(Kalıcı disk Free planda yoktur; Starter ve üzeri gerekir.)*
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:**
   ```
   gunicorn app:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT
   ```
   > **Neden tek worker?** Uygulama adımlar arası durumu süreç-içi bellekte
   > tutar; birden çok worker bu durumu bölerdi. Tek worker + 4 thread tüm
   > istekleri aynı bellekte paylaştırır, uzun ShipStation çekimi sırasında
   > arayüzü kilitlemez. `--timeout 300` uzun sayfalı API çekimleri içindir.
4. **Kalıcı disk:** Ad `lazer-data`, **Mount Path `/data`**, boyut 1 GB.
5. **Ortam değişkenleri** (panelde *Environment* sekmesi):

   | Değişken | Değer | Not |
   |---|---|---|
   | `DATA_DIR` | `/data` | Disk mount yoluyla aynı olmalı; tüm yazılabilir durum buraya gider |
   | `SHIPSTATION_API_KEY` | *(API anahtarınız)* | Yalnızca panelde; repoya asla yazılmaz |
   | `APP_USERNAME` | *(giriş kullanıcı adı)* | Varsayılan `lazer` |
   | `APP_PASSWORD` | *(güçlü parola)* | **Zorunlu** — bu olmadan üretimde uygulama başlamaz |

   > `SHIPSTATION_API_KEY` üretimde panelden gelir; `.env` yalnızca lokal
   > içindir ve `.gitignore`'dadır.

### Erişim denetimi (kimlik doğrulama)

Uygulama müşteri adlarını/adreslerini ve para dağıtım rakamlarını gösterdiği
için **hiçbir sayfa, API ucu veya rapor indirme bağlantısı** kimlik doğrulaması
olmadan açılmaz. Korumalı HTTP Basic Auth devrededir:

- Üretimde `APP_USERNAME` / `APP_PASSWORD` ortam değişkenlerinden gelir.
  Tarayıcı ilk girişte kullanıcı adı + parola sorar.
- Render ortamında (otomatik `RENDER` değişkeniyle anlaşılır) `APP_PASSWORD`
  tanımlı değilse uygulama **güvenli tarafta kalmak için başlamaz**.
- Lokalde bu değişkenler tanımlı olmadığından parola sorulmaz (uygulama
  yalnızca `127.0.0.1`'e bağlıdır).

Parolayı değiştirmek için Render panelinden `APP_PASSWORD` değerini güncelleyip
servisi yeniden başlatın.

### Diskte ne saklanır?

`/data` altında: `store_mapping.json`, `store_id_mapping.json`, `cache/`
(aylık API yanıtları), `yuklenen/` (arayüzden yüklenen master/CSV'ler) ve
`cikti/` (üretilen raporlar). Servis yeniden başlasa da bu durum korunur;
öğrenilen eşlemeler ve cache kaybolmaz.

## ShipStation'dan export alma

### Orders export (gelir verisi)
1. ShipStation → **Orders** sekmesi.
2. Sağ üstteki tarih filtresinden ilgili ayın **1'i – son günü** aralığını
   seçin (örn. 1 Mayıs – 31 Mayıs). Aralığı eksik seçerseniz uygulama
   "tarih kapsama" uyarısı verir.
3. Tüm siparişleri seçip **Export** → CSV. Export şablonunda en az şu
   kolonlar bulunmalı: `Order #`, `Order Date`, `Item SKU`, `Item Name`,
   `Quantity`, `Tax Paid`, `Order Total`, `Shipping Paid`, `Amount Paid`,
   `Store`.
4. Not: Export **item bazlıdır**; çok ürünlü siparişlerde sipariş tutarları
   her satırda tekrarlanır. Uygulama bunları Order # bazında bir kez sayar.

### Shipments export (Order # ↔ Store eşleşmesi)
1. ShipStation → **Shipments** sekmesi.
2. Aynı ay aralığını **Ship Date** filtresiyle seçin.
3. Export → CSV (`Shipment #`, `Order #`, `Ship Date`, `Store` kolonlu
   standart export yeterlidir; bu dosyada maliyet yoktur).

## Aylık kullanım akışı

1. `python app.py` ile uygulamayı açın.
2. **1) Veri Dosyaları**: Master Excel klasörde otomatik bulunur; Orders ve
   Shipments CSV'lerini sürükleyip bırakın (klasördeki CSV'ler de içeriğine
   göre otomatik tanınır).
3. **2) Dönem**: Ay + yılı seçip **Analiz Et**'e basın.
4. **3) Mağaza Eşleştirme**: Fuzzy önerileri kontrol edin, gerekirse
   düzeltin, **Kaydet**. Eşleştirmeler `store_mapping.json`'a yazılır ve
   sonraki aylarda otomatik kullanılır; yalnızca yeni mağazalar sorulur.
   Adında "Amazon" geçen mağazalar otomatik "Rapor Dışı (Amazon)" olur.
5. **4) Kargo Maliyeti**: **API'den Kargo Maliyetini Çek** (ilk seferde
   **Bağlantı Testi** önerilir). Maliyet **sipariş ayına** yazılır: label'lar
   geniş pencereyle (ay başı −7 gün, ay sonu +45 gün) çekilip Order #
   üzerinden ayın siparişlerine bağlanır; ay sonunda verilip sonraki ay
   kargolanan siparişin maliyeti doğru aya girer. Eşleşme oranı, eşleşmeyen
   siparişlerin sınıflandırması ve "henüz kargolanmamış" mağaza listesi
   ekranda gösterilir. store_id → mağaza eşlemesi en az 3 sipariş kanıtıyla
   kalıcılaşır; daha azı onayınıza sunulur. API yanıtları `cache/` klasörüne
   kaydedilir; güncel veri için **Cache'i Yenile**. API çalışmazsa Cost
   kolonlu bir ShipStation raporu yükleyip **CSV'den Hesapla** kullanın.
6. **5) Denetim**: Form beyanı ile ShipStation gerçeği yan yana; %5+ sapma
   sarı, %15+ sapma kırmızı. Kolon bazında hangi kaynağın rapora gireceğini
   seçin (varsayılan ShipStation; Reklam ve İlave Ödeme her zaman formdan).
   "Ciro tanımı" (Order Total / Amount Paid) kalibrasyon önerisiyle gelir.
7. **6) Validasyon**: Eksik form dolduranlar, eşleşmeyen mağazalar,
   iptal/negatif siparişler, tarih kapsaması ve bozuk master satırları.
8. **7) Excel İndir** → `Lazer_Grubu_Rapor_{YIL}_{AY}.xlsx`. Hesap
   kolonları (KALAN, parça başı değerler, yüzdeler) Excel formülü olarak
   yazılır; ekip hücreye tıklayıp kontrol edebilir.

## Önemli dosyalar

| Dosya | Açıklama |
|---|---|
| `store_mapping.json` | ShipStation mağaza adı → master mağaza adı sözlüğü |
| `store_id_mapping.json` | ShipStation V2 `store_id` → mağaza adı sözlüğü |
| `cache/` | Aylık API yanıtları (labels/shipments) |
| `cikti/` | Üretilen raporlar |
| `yuklenen/` | Arayüzden yüklenen dosyalar |

## Rapor formülleri

- `KALAN = CİRO − VERGİ − REKLAM − Kargo`
- `Parça başı ciro = CİRO ÷ PARÇA ADEDİ`
- `Kargo parça başı ort ödenen = KARGO MÜŞTERİ ÷ PARÇA ADEDİ`
- `Kargo parça başı ort kalan = (KARGO MÜŞTERİ − Kargo) ÷ PARÇA ADEDİ`
- `%REKLAM = REKLAM ÷ CİRO`, `%VERGİ = VERGİ ÷ CİRO`
- `Parça başı kalan = KALAN ÷ PARÇA ADEDİ`
- PARÇA ADEDİ 0/boş ise bölme hücreleri boş bırakılır (#DIV/0! üretilmez).
- TOPLAM satırında yüzde kolonları toplam ciro üzerinden ağırlıklıdır.
