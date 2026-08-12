# LUMINA

Windows parlaklık kontrolü. Laptop paneli ve harici DDC/CI monitörler tek
arayüzden, bildirim alanından tek tıkla.

- **Hızlı panel** — tepsi ikonuna tıkla, slider gelsin
- **Eşitleme** — tüm monitörler tek slider'la
- **Zamanlayıcı** — saat aralığına göre otomatik, gece aşırı aralıklar dahil
- **Yumuşak geçiş** — zamanlayıcı tetiklendiğinde kademeli
- **Windows ile başlat** — bildirim alanına sessiz açılış

Harici program gerekmez. `ControlMyMonitor.exe` yok, `powershell.exe` yok.

## Kurulum

`LuminaSetup-2.0.0.exe` çalıştır. Yönetici hakkı istemez, `%LOCALAPPDATA%\Programs\Lumina`
altına kurar. Python kurulu olması gerekmez.

> İmzasız installer olduğu için Windows SmartScreen ilk çalıştırmada uyarır:
> **Daha fazla bilgi → Yine de çalıştır**.

## Nasıl çalışıyor

| Katman | Yöntem |
|---|---|
| Harici monitörler | `dxva2.dll` — `GetMonitorBrightness` / `SetMonitorBrightness` (DDC/CI) |
| Laptop paneli | WMI `WmiMonitorBrightnessMethods` COM üzerinden |
| Monitör kimliği | `EnumDisplayMonitors` + `EnumDisplayDevices`, isimler registry EDID'inden |
| Tak/çıkar | Qt `screenAdded` / `screenRemoved` |

Ölçülen gecikmeler (v1 aynı donanımda, alt satır v2):

| İşlem | v1 | v2 |
|---|---|---|
| Tam monitör taraması | ~8000 ms | 135 ms |
| Laptop paneli oku / yaz | 1183 / ~1200 ms | 4 / 7 ms |
| Harici monitör oku | 7840 ms | 62 ms |
| Harici monitör yaz | ~170 ms | 60 ms |

Harici yazmanın 60 ms'i DDC/CI I²C veri yolunun fiziksel tabanı. Asıl kazanç
**yazma birleştirmesinde**: slider sürüklenirken bekleyen değer monitör başına
tek yuvada tutulur, yeni değer eskisinin üstüne yazılır. v1 her tik'i sırayla
uyguladığı için bırakıldıktan sonra monitör bir saniye daha "yetişirdi".

## Geliştirme

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe run_lumina.py --debug
```

```powershell
.venv\Scripts\python.exe -m pytest tests -q     # 38 test, donanım gerekmez
.venv\Scripts\python.exe tools\smoke_core.py    # gerçek monitörlerde gecikme ölçümü
.venv\Scripts\python.exe tools\preview.py       # tüm sayfaları PNG'ye bas
.venv\Scripts\python.exe tools\measure_startup.py
```

### Derleme

```powershell
.\build.ps1                 # test + exe + installer
.\build.ps1 -ExeOnly        # sadece exe
.\build.ps1 -SkipTests
```

Çıktı: `build\output\LuminaSetup-<sürüm>.exe`. Inno Setup kurulu değilse
`build.ps1` winget ile kurar.

## Yerleşim

```
src/lumina/
  core/      ddcci.py  panel.py  discovery.py  backend.py  service.py
  features/  automation.py (zamanlayıcı + fade)  autostart.py
  ui/        main_window.py  quick_panel.py  widgets.py  icons.py
  resources/ theme.qss  lumina.png  lumina.ico
  app.py     tüm bağlantılar burada
build/       lumina.spec  installer.iss  version_info.txt
legacy/      v1 arşivi, silinebilir
```

Kullanıcı verisi:

- Ayarlar: `%APPDATA%\Lumina\config.json`
- Günlükler: `%LOCALAPPDATA%\Lumina\logs\lumina.log` (döner, 512 KB × 3)

Kaldırma ayarları silmez; `config.json`'ı elle silebilirsin.
