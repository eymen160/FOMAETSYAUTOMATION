# Lazer Grubu — Ay Sonu Raporu Otomasyonu

30+ Etsy mağazasının aylık form beyanlarını ShipStation gerçek verisiyle
eşleştirip denetleyen ve ekibin ay sonu Excel raporunu otomatik üreten
lokal web uygulaması. Tüm işlem bilgisayarınızda yapılır; veri hiçbir dış
servise gönderilmez (ShipStation API çağrıları hariç).

## Giriş (sign-in)

Uygulama açılışta giriş ekranı gösterir. Varsayılan demo bilgileri:
- **Kullanıcı adı:** `admin`
- **Şifre:** `lazer2026`

Bunları değiştirmek için `.env` dosyasına ekleyin:
```
LAZER_KULLANICI=istediginiz_kullanici
LAZER_SIFRE=guclu_bir_sifre
LAZER_SECRET=rastgele_uzun_bir_anahtar
```
Şifre düz metin saklanmaz; oturum çerezi `LAZER_SECRET`/`.flask_secret` ile
imzalanır. Sunumdan önce şifreyi değiştirmeniz önerilir.

## Demo (sunum)

Hızlı bir gösterim için açılış ekranındaki **"Demo verisini yükle"** butonuna
basın. Paketlenmiş örnek veri (`demo/` klasörü: 10 mağaza, Mayıs 2026) tek
tıkla yüklenir ve adımlı akış (Dönem → Veri → Eşleştirme → Denetim → Rapor)
otomatik ilerler. 9 mağaza otomatik eşleşir, FTM inceleme vakası olarak
işaretlenir. Her demo başlangıcında eşleştirme temiz baseline'a sıfırlanır
(prova tekrarlanabilir). Demo verisinde müşteri adı/adresi yoktur.

Testler:
```
pip install -r requirements-dev.txt
python -m pytest -q
```


## Formsuz mod (master form olmadan)

Master form yoksa rapor doğrudan ham veriden üretilir. Dönem adımında
**"Ham veriden üret (master form yok)"** kutusunu işaretleyin:
- **Ciro** = ShipStation Subtotal + müşteri kargosu (vergisiz)
- **Vergi** = satış vergisi (Tax Paid), **Kargo** = ShipStation kargo maliyeti
- **Parça adedi + ürün kolonları + sipariş içeriği** = kalem detayından otomatik
- **Reklam / İlave ödeme / Upgrade** = ekranda elle girilir (dönem bazında
  `elle_girdi.json`'a kaydedilir; Etsy Ads/hesap özeti eklenince reklam
  otomatikleşebilir)
- Mağazalar verinin kendisinden gelir; Amazon mağazaları "Rapor Dışı".

Gereken dosyalar (formsuz): ShipStation **sipariş özeti** (Amount-Order Total
kolonlu) + **kalem detayı** (Item Name/SKU'lu export).

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
   **Bağlantı Testi** önerilir). API yanıtları `cache/` klasörüne kaydedilir;
   aynı ay tekrar hesaplanırken API'ye gidilmez. Güncel veri için
   **Cache'i Yenile**. API çalışmazsa Cost kolonlu bir ShipStation raporu
   yükleyip **CSV'den Hesapla** kullanın.
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
