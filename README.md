# Local CV Analyzer

Yerel LLM kullanan CV ve iş ilanı karşılaştırma uygulaması. CV metni (veya dosya/link) ile iş ilanı linkini (veya metnini) karşılaştırır; uygunluk skoru, eksikler ve CV geliştirme önerileri üretir.

## Özellikler

- **Uyum Analizi**: CV ile iş ilanı arasında embedding + kural tabanlı skorlama, eksik beceri tespiti.
- **LLM Analizi**: Yerel model veya Cursor API ile detaylı Türkçe rapor.
- **CV Güncelleme**: İlana göre CV iyileştirme önerileri; LaTeX (`.tex`) girdilerinde template korunarak PDF üretimi.
- **İş Unvanı Önerileri**: CV'ye uygun pozisyon başlıkları.
- **İlan Arama**: Opsiyonel Apify entegrasyonu ile LinkedIn / Kariyer.net üzerinden ilan arama ve skorlama.
- **Çift LLM sağlayıcı**: Yerel Ollama (varsayılan) veya Cursor API (OpenAI-compatible).
- **TR → EN normalizasyon**: LLM girdileri otomatik İngilizceye çevrilir (cache'li).

## İçindekiler

- [Donanım Hedefi ve Model](#donanım-hedefi-ve-model)
- [Hızlı Başlangıç](#hızlı-başlangıç)
- [Proje Yapısı](#proje-yapısı)
- [API Uç Noktaları](#api-uç-noktaları)
- [Test](#test)
- [LLM Girdi Normalizasyonu](#llm-girdi-normalizasyonu)
- [LLM Sağlayıcı Seçimi](#llm-sağlayıcı-seçimi)
- [Opsiyonel Apify Entegrasyonu](#opsiyonel-apify-entegrasyonu-linkedin--kariyernet)
- [Local LLM Kalite Ayarları](#local-llm-kalite-ayarları)
- [LaTeX CV ve PDF Çıktısı](#latex-cv-ve-pdf-çıktısı)
- [Mimari](#mimari)

## Donanım Hedefi ve Model

- 16 GB RAM
- RTX 3060 Ti 8 GB VRAM
- 4-bit quantized 7B-8B sınıfı yerel model

Varsayılan yapı Ollama üzerinden çalışır. Model adı ortam değişkeniyle değiştirilebilir, bu yüzden Ollama'da mevcut olan Qwen 3 / Qwen 3.5 / Llama gibi uyumlu modeller kullanılabilir.

Önerilen başlangıç:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Qwen 3.5 varyantını daha kaliteli ama daha yavaş cevaplar için kullanmak isterseniz Ollama'da model mevcutsa:

```powershell
$env:OLLAMA_MODEL="qwen3.5:9b-q4_K_M"
```

Model adları Ollama registry'deki gerçek etikete göre değişebilir.

## Hızlı Başlangıç

### Her İkisini Birlikte Başlatma (önerilen)

Proje kökünden backend ve frontend'i aynı anda başlatmak için:

```powershell
.\start-dev.ps1
```

Alternatif olarak çift tıklama:

```text
start-dev.bat
```

Script backend'i `http://localhost:8000`, frontend'i `http://localhost:5173` adresinde ayrı PowerShell pencerelerinde açar. `backend\.venv` varsa otomatik olarak onu kullanır.

### Backend (manuel)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (manuel)

```powershell
cd frontend
npm install
npm run dev
```

Uygulama varsayılan olarak `http://localhost:5173` adresinden backend'e `http://localhost:8000` üzerinden bağlanır.

## Proje Yapısı

```text
cvanalyzeproject/
├── backend/                # FastAPI uygulaması
│   ├── app/
│   │   ├── api/            # analysis ve jobs router'ları
│   │   ├── services/       # skorlama, LLM, ingestion, latex, pdf, apify, vb.
│   │   ├── config.py       # ortam değişkeni tabanlı ayarlar
│   │   ├── db.py           # SQLite cache ve analiz kayıtları
│   │   ├── models.py       # Pydantic modelleri
│   │   └── main.py         # FastAPI giriş noktası
│   ├── tests/              # pytest testleri (LLM indirmesi gerektirmez)
│   ├── .env.example        # ortam değişkeni şablonu
│   └── requirements.txt
├── frontend/               # React + Vite (TypeScript) arayüzü
│   └── src/components/      # sekmeler, paneller, formlar
├── start-dev.ps1           # backend + frontend birlikte başlatma
└── start-dev.bat
```

## API Uç Noktaları

| Metot | Yol | Açıklama |
| --- | --- | --- |
| GET | `/health` | Servis sağlık kontrolü |
| POST | `/api/analysis` | Uyum (skorlama) analizi başlatır |
| POST | `/api/llm-analysis` | LLM destekli detaylı analiz başlatır |
| GET | `/api/analysis/{analysis_id}` | Analiz durumu/sonucu |
| POST | `/api/analysis/{analysis_id}/rewrite-cv` | CV güncelleme önerisi üretir |
| GET | `/api/analysis/{analysis_id}/rewrite-cv/{rewrite_id}/pdf` | Güncellenmiş CV'nin PDF çıktısı |
| GET | `/api/llm/health` | LLM sağlayıcı erişim kontrolü |
| POST | `/api/job-title-suggestions` | CV'ye uygun iş unvanı önerileri |
| POST | `/api/job-search/preview` | İlan arama önizlemesi |
| POST | `/api/job-search` | İlan arama + skorlama |
| GET | `/api/apify/health` | Apify token/erişim kontrolü |

İnteraktif API dokümanı backend çalışırken `http://localhost:8000/docs` adresindedir.

## Test

```powershell
cd backend
pytest
```

Testler LLM indirmeyi gerektirmez; LLM adapter mock/fallback davranışla doğrulanır.

## LLM Girdi Normalizasyonu

Varsayılan olarak LLM ve embedding çağrılarına giden metinler İngilizce değilse yerel Ollama ile İngilizceye çevrilir. Skorlama, profil çıkarımı ve CV doğrulama orijinal metinle çalışmaya devam eder. Çeviriler SQLite cache'te saklanır.

Kapatmak için:

```powershell
$env:AUTO_TRANSLATE_LLM_INPUT_TO_ENGLISH="false"
```

## LLM Sağlayıcı Seçimi

Uygulama iki LLM sağlayıcısı destekler:

- **Local LLM** (varsayılan): Ollama üzerinden yerel model
- **Cursor API**: OpenAI-compatible `/v1/chat/completions` endpoint'i (Cursor proxy/bridge)

UI'dan sağlayıcı seçilebilir; varsayılan davranış değişmez (`local`).

Cursor API için backend ortam değişkenleri. **API key'i `config.py` içine yazmayın**; `backend/.env` kullanın:

```powershell
cd backend
copy .env.example .env
# .env dosyasında CURSOR_API_KEY değerini doldurun
```

`.env` örneği:

```env
CURSOR_API_BASE_URL=http://127.0.0.1:8765/v1
CURSOR_API_KEY=your-api-key-or-token
CURSOR_MODEL=auto
```

Alternatif olarak PowerShell ortam değişkenleri:

```powershell
$env:DEFAULT_LLM_PROVIDER="local"
$env:CURSOR_API_BASE_URL="http://127.0.0.1:8765/v1"
$env:CURSOR_API_KEY="your-api-key-or-token"
$env:CURSOR_MODEL="auto"
```

Cursor API bir OpenAI-compatible proxy gerektirir (ör. `http://127.0.0.1:8765/v1`). Proxy çalışmıyorsa Sistem Durumu "bağlı değil" gösterir ve LLM analizi hemen hata verir.

Cursor seçildiğinde metin çeviri/normalizasyonu Ollama'ya bağımlı kalmadan doğrudan modele gönderilir. Domain skoru için embedding hâlâ yerel Ollama kullanır; embedding yoksa keyword fallback devreye girer.

## Opsiyonel Apify Entegrasyonu (LinkedIn + Kariyer.net)

Apify, LinkedIn ve Kariyer.net üzerinden **ilan arama** ve **tek ilan linkinden metin çekme** için opsiyonel bir veri kaynağıdır. Apify kapalıyken veya token yokken mevcut httpx/BeautifulSoup yolu aynen çalışır; analiz pipeline'ı etkilenmez.

### Token alma

1. [Apify Console](https://console.apify.com/) hesabı oluşturun.
2. **Settings → Integrations → API tokens** bölümünden token alın.
3. `backend/.env` dosyasına ekleyin:

```env
APIFY_API_TOKEN=apify_api_...
APIFY_ENABLED=true
APIFY_LINKEDIN_SEARCH_ACTOR_ID=
APIFY_LINKEDIN_JOB_ACTOR_ID=
APIFY_KARIYER_SEARCH_ACTOR_ID=
APIFY_KARIYER_JOB_ACTOR_ID=
APIFY_MAX_RESULTS_PER_SOURCE=10
APIFY_TIMEOUT_SECONDS=120
```

Actor ID'ler kodda sabitlenmez; [Apify Store](https://apify.com/store) üzerinden LinkedIn iş arama / iş detayı ve Kariyer.net actor'larını seçip `.env`'e yazın. Store'daki actor adları ve input şemaları zamanla değişebilir — README'deki örnekler yalnızca başlangıç noktasıdır.



### UI kullanımı

- **İlan Arama** sekmesi: CV + "Apify ile ara" + kaynak seçimi (LinkedIn / Kariyer.net). Sonuçlar mevcut skorlama motoruyla sıralanır.
- **Uyum Analizi / LLM Analizi**: İş ilanı modu "Link" iken **Apify ile çek (LinkedIn/Kariyer)** checkbox'ı LinkedIn/Kariyer URL'lerinde actor ile detay metni çeker; başarısız olursa httpx fallback devreye girer.

### Maliyet uyarısı

Apify kullanımı **ücretlidir** (ücretsiz kredi sonrası actor run başına ücret). `APIFY_MAX_RESULTS_PER_SOURCE` ile kaynak başına ilan sayısını sınırlayın.

### Sağlık kontrolü

`GET /api/apify/health` token ve Apify API erişimini döner. İlan Arama sekmesinde Sistem Durumu panelinde özet gösterilir.

Apify token tanımlı değilse uygulama normal şekilde çalışmaya devam eder; yalnızca Apify'ye bağlı özellikler devre dışı kalır. Sunucu tarafında `APIFY_ENABLED=false` ise UI toggle açık olsa bile Apify çağrılmaz.

## Local LLM Kalite Ayarları

Profile summary, analiz raporu ve CV güncelleme çıktılarının kalitesini artırmak için context ve çıktı bütçeleri `.env` veya PowerShell ortam değişkenleriyle ayarlanabilir.

```powershell
$env:OLLAMA_NUM_CTX="8192"
$env:LLM_SUMMARY_NUM_PREDICT="700"
$env:CV_REWRITE_NUM_PREDICT="1800"
$env:CV_REWRITE_CV_CHARS="9000"
$env:CV_REWRITE_JOB_CHARS="4500"
```

RTX 3060 Ti 8 GB VRAM için 7B-8B 4-bit modellerde bu değerler dengeli başlangıç noktasıdır. Daha uzun ve bütünlüklü CV rewrite çıktısı gerekiyorsa `CV_REWRITE_NUM_PREDICT=2200` veya `2500` denenebilir; süre çok uzarsa tekrar `1800` civarına çekmek daha uygundur.

## LaTeX CV ve PDF Çıktısı

CV güncelleme modülü, CV metni LaTeX kaynak formatındaysa (`.tex`) aynı template/preamble yapısını korumaya çalışır ve güncellenmiş LaTeX kaynak metnini gösterir. Sistemde `xelatex`, `pdflatex` veya `tectonic` varsa PDF üretmeyi dener; yoksa LaTeX kaynağı verilir ve uyarı gösterilir.

## Mimari

- FastAPI backend
- React + Vite frontend
- SQLite cache ve analiz kayıtları
- Ollama LLM adapter
- Cursor API (OpenAI-compatible) LLM adapter
- LLM girdi normalizasyonu (TR → EN, cache'li; local sağlayıcıda)
- Embedding + kural tabanlı scoring
- LLM destekli Türkçe raporlama
