# Uzaktan kuyruk (bulut API + ev worker)

Amaç: Okul veya başka bir ağdan tarayıcı ile iş kuyruğuna `repo` + `issue` eklemek; **evdeki** bilgisayarda çalışan worker `python -m maestro run ...` ile işi alıp çalıştırmak; sonuç ve `events.jsonl` içeriği yine bu API üzerinden okunur. Ollama yalnızca worker makinede localhost’ta kalır.

## Repo içi yerleşim

| Yol | Rol |
|-----|-----|
| `remote/queue_server/` | Bulutta (veya denemede yerelde) çalışan FastAPI + SQLite |
| `remote/worker/` | Ev PC’de sürekli veya oturum boyunca çalışan poller |

Çekirdek `src/maestro/` ile bilinçli olarak ayrı tutuldu; bağımlılıklar `pyproject.toml` içinde `[remote]` extra ile gelir.

## Kurulum

```powershell
cd C:\Users\Emir\Desktop\GitMaestro
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[remote]"
```

## Bulut sunucusu (queue API)

Ortam değişkenleri:

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `REMOTE_UI_USERNAME` | evet | Tarayıcı Basic Auth kullanıcı adı |
| `REMOTE_UI_PASSWORD` | evet | Tarayıcı Basic Auth şifresi |
| `WORKER_TOKEN` | evet | Worker’ın `Authorization: Bearer ...` ile kullandığı uzun gizli anahtar |
| `QUEUE_DB_PATH` | hayır | SQLite dosyası (yoksa `remote/queue_server/queue.db`) |
| `PORT` | hayır | Dinlenecek port (varsayılan 8000) |

Örnek (yerel deneme):

```powershell
cd remote\queue_server
$env:REMOTE_UI_USERNAME="demo"
$env:REMOTE_UI_PASSWORD="demo-secret"
$env:WORKER_TOKEN="worker-secret-change-me"
python app.py
```

Üretimde aşağıdaki **Render** adımları veya elle aynı env’lerle `uvicorn app:app --host 0.0.0.0 --port $PORT` ile çalıştır.

## Render ile deploy

Bulutta sadece **kuyruk API** çalışır (SQLite + FastAPI). Lab bilgisayarında kurulum yok; tarayıcı yeterli.

### Önkoşul

Repoyu GitHub’a push et (Render repoyu oradan çeker).

### Yöntem A — Blueprint (`render.yaml`)

1. [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
2. GitHub’da bu repoyu bağla, `render.yaml` dosyasını algılat.
3. Sihirbaz **REMOTE_UI_USERNAME**, **REMOTE_UI_PASSWORD**, **WORKER_TOKEN** için değer isteyecek (`sync: false`); güçlü şifre ve uzun rastgele token gir.
4. **Apply** ile deploy bekle.
5. Servisin **`https://....onrender.com`** adresini kopyala → bu, ev worker’da `QUEUE_BASE_URL` olacak.

### Yöntem B — Tek Web Service (elle)

1. **New** → **Web Service** → repoyu seç.
2. **Runtime:** Python 3 (repoda `runtime.txt` → 3.12.8).
3. **Build command:**  
   `pip install -r remote/queue_server/requirements.txt`
4. **Start command:**  
   `cd remote/queue_server && uvicorn app:app --host 0.0.0.0 --port $PORT`
5. **Environment** sekmesinde şu üçlüyü ekle: `REMOTE_UI_USERNAME`, `REMOTE_UI_PASSWORD`, `WORKER_TOKEN`.
6. **Create Web Service** → canlı URL’yi al.

### Ücretsiz plan notu (önemli)

- İstek gelmeyince servis **uykuya** geçebilir; ilk açılış **onlarca saniye** sürebilir. Sunumdan **birkaç dakika önce** tarayıcıdan ana sayfayı bir kez aç.
- Disk **kalıcı değil**; redeploy veya uzun süre sonra SQLite’daki eski işler silinebilir. Demo kuyruğu için normal.

### Deploy sonrası

Ev PC’de worker’ı `QUEUE_BASE_URL=https://<senin-servis>.onrender.com` ile çalıştır (`WORKER_TOKEN` Render’daki ile aynı).

## Ev worker

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `QUEUE_BASE_URL` | evet | Bulut API kök URL’si, örn. `https://xxx.onrender.com` |
| `WORKER_TOKEN` | evet | Sunucudaki `WORKER_TOKEN` ile **aynı** |
| `MAESTRO_REPO_ROOT` | evet | `config.yaml` ve `runs/` olan repo kökü (GitMaestro kökü) |
| `MAESTRO_PYTHON` | hayır | Varsayılan: worker’ı çalıştırdığın `python` |
| `MAESTRO_CONFIG` | hayır | Varsayılan `config.yaml` |
| `MAESTRO_GIT_REF` | hayır | İş öncesi `git checkout` (ör. `part2-demo` — Part 2 sunumu) |
| `WORKER_POLL_SECONDS` | hayır | İş yokken bekleme (varsayılan 4) |
| `MAESTRO_RUN_TIMEOUT_SECONDS` | hayır | Tek iş için üst süre (varsayılan 7200) |

### Part 2 sunumu vs Part 3 geliştirme

| Bileşen | Part 2 (Perşembe) | Part 3 (`main`) |
|---------|-------------------|-----------------|
| Render (`render.yaml`) | `branch: part2-demo` | Dashboard’da branch’i `main` yapabilirsiniz |
| Ev worker | `MAESTRO_GIT_REF=part2-demo` veya repoda `git checkout part2-demo` | `MAESTRO_GIT_REF` boş, `main` üzerinde çalışın |

`main` ile `part2-demo` ayrıldıktan sonra worker yanlışlıkla `main`’de kalırsa farklı orchestrator kodu çalışır; sunum haftası worker’da `part2-demo` kullanın.

```powershell
cd C:\Users\Emir\Desktop\GitMaestro
$env:QUEUE_BASE_URL="https://your-app.onrender.com"
$env:WORKER_TOKEN="worker-secret-change-me"
$env:MAESTRO_REPO_ROOT="C:\Users\Emir\Desktop\GitMaestro"
python remote\worker\main.py
```

## Akış

1. Tarayıcıdan `https://.../` adresine git; kullanıcı adı / şifre ile giriş (Basic Auth).
2. Formdan `owner/name` ve issue numarası veya URL gönder → kayıt `pending` olur.
3. Evdeki worker `POST /worker/claim` ile bir işi `running` yapar, `maestro run` çalıştırır.
4. Bittiğinde `POST /worker/finish` ile stdout, `events.jsonl`, `task_id` yüklenir.
5. Aynı tarayıcıda `/jobs/<id>` sayfası birkaç saniyede bir yenilenir; API: `GET /api/jobs/<id>`.

## Güvenlik notları

- `WORKER_TOKEN` ve UI şifresini güçlü ve rastgele tut; repoya commit etme.
- Ücretsiz PaaS veritabanı diski silinebilir; sadece demo kuyruğu için uygundur.
- Issue metni ve loglar SQLite’da durur; hassas repolarda dikkat.
