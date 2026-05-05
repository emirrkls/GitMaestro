\# ARCHITECTURE\_DECISIONS



Bu doküman, \*\*GitHub Issue Orchestra (Maestro)\*\* projesindeki kritik mimari kararları ve gerekçelerini kayıt altına alır.



\---



\## ADR-001 — Framework Seçimi: Custom Lightweight Orchestrator



\- \*\*Status:\*\* Accepted

\- \*\*Date:\*\* 2026-05-05



\### Context

Projede dinamik orkestrasyon, retry loop, güvenlik kapıları ve gözlemlenebilir mesajlaşma gerekiyor. Framework seçenekleri (LangGraph vb.) değerlendirildi.



\### Decision

Projeyi \*\*custom lightweight orchestrator\*\* ile implemente ediyoruz.  

LangGraph/CrewAI gibi katmanlar MVP kapsamına dahil edilmeyecek.



\### Rationale

\- Ders gereksinimi: “tasarım kararlarını ve kodu satır satır açıklayabilme”

\- Daha düşük öğrenme ve entegrasyon maliyeti

\- Tam kontrol: state machine, policy, log formatı, guardrail’ler



\### Consequences

\- \*\*Pozitif:\*\* Daha şeffaf mimari, daha kolay savunma, daha az bağımlılık

\- \*\*Negatif:\*\* Bazı altyapı yeteneklerini (routing/state/logging) kendimiz yazacağız



\---



\## ADR-002 — Tester Güvenlik Modeli: Komut Whitelist + Timeout + `shell=False`



\- \*\*Status:\*\* Accepted

\- \*\*Date:\*\* 2026-05-05



\### Context

Tester ajanı komut çalıştırdığı için komut enjeksiyonu, kontrolsüz süreç ve kaynak tüketimi riski bulunuyor.



\### Decision

Tester yalnızca izinli komutları çalıştırır:

\- \*\*Whitelist tabanlı komut kontrolü\*\*

\- Her çalıştırmada \*\*timeout\*\*

\- Süreç başlatmada \*\*`shell=False`\*\*

\- Çalışma dizini ve argümanlar doğrulanır

\- Çıktı boyutu sınırlandırılır



\### Rationale

\- Güvenli ve deterministik test yürütümü

\- Demo sırasında beklenmeyen davranışların önlenmesi

\- Otomasyon sisteminde minimum saldırı yüzeyi



\### Consequences

\- \*\*Pozitif:\*\* Güvenlik ve stabilite artar

\- \*\*Negatif:\*\* Esneklik azalır (izinli olmayan test komutları ek konfigürasyon ister)



\---



\## ADR-003 — Critic Model Dayanıklılığı: Fallback Politikası



\- \*\*Status:\*\* Accepted

\- \*\*Date:\*\* 2026-05-05



\### Context

Critic için farklı model kullanımı planlandı. Ücretsiz/limitli sağlayıcılarda rate-limit veya geçici erişim sorunları oluşabilir.



\### Decision

Critic için birincil model başarısız olursa otomatik fallback uygulanır:

1\. `critic\_primary\_model` (örn. `llama-4-scout`)

2\. `critic\_fallback\_model` (config ile tanımlı)



Fallback yalnızca belirli hata sınıflarında tetiklenir (rate limit, timeout, provider unavailable).



\### Rationale

\- Orkestranın tek bir model/sağlayıcıya bağımlı kalmaması

\- Çalışmanın kesintisiz devam etmesi

\- Değerlendirme deneylerinin tamamlanabilmesi



\### Consequences

\- \*\*Pozitif:\*\* Runtime güvenilirliği artar

\- \*\*Negatif:\*\* Çıktı dağılımı model bazında farklılaşabilir (raporda belirtilmeli)



\---



\## ADR-004 — `confidence` Alanı: Seçici Zorunluluk



\- \*\*Status:\*\* Accepted

\- \*\*Date:\*\* 2026-05-05



\### Context

Tüm ajanlar için `confidence` zorunlu olduğunda bazı ajanlar anlamsız veya yapay güven skorları üretme eğilimi gösterir.



\### Decision

`confidence` alanı:

\- \*\*Zorunlu:\*\* `Maestro`, `Critic`

\- \*\*Opsiyonel:\*\* diğer ajanlar (`Analyst`, `Scout`, `Surgeon`, `Tester`, `Scribe`, ad-hoc)



\### Rationale

\- Güven skorunu gerçekten karar verici noktalarda kullanmak

\- Şema sadeliği ve sinyal kalitesini artırmak

\- “Sahte kesinlik” üretimini azaltmak



\### Consequences

\- \*\*Pozitif:\*\* Daha anlamlı telemetry ve daha temiz mesaj şeması

\- \*\*Negatif:\*\* Bazı analizlerde tüm ajanlar arası confidence karşılaştırması yapılamaz



\---



\## Uygulama Notları



\- Bu ADR’lerin hepsi `config.yaml` ve policy katmanında karşılık bulmalıdır.

\- Her karar için run log’larında uygulanma izi bulunmalıdır (özellikle fallback ve safety guardrail).

\- Gelecekte değişiklik olursa yeni ADR eklenmeli, mevcut ADR metni geriye dönük olarak sessizce değiştirilmemelidir.

