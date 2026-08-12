# v1 arşivi

Buradaki dosyalar **kullanılmıyor**. v2 hiçbirine bağımlı değil; referans ve
geri dönüş için duruyorlar. İstediğin zaman bu klasörü tamamen silebilirsin —
kaynak dosyaların tamamı ayrıca `v1-legacy` git etiketinde duruyor:

```
git show v1-legacy:brightness_controller.py
```

| Dosya | Neydi | Neden gitti |
|---|---|---|
| `brightness_controller.py` | Tek dosyalık PyQt5 uygulaması (539 satır) | `src/lumina/` paketine bölündü, PySide6'ya taşındı |
| `ControlMyMonitor.exe` | NirSoft aracı, harici monitör DDC/CI kontrolü | `dxva2.dll` doğrudan çağrılıyor — okuma 7840 ms → 62 ms |
| `ControlMyMonitor.chm/.cfg`, `readme.txt` | NirSoft yardım ve ayar dosyaları | Araç kaldırıldı |
| `LUMINA.exe` | v1 PyInstaller onefile derlemesi (37 MB) | onedir + Inno Setup installer'a geçildi |
| `BASLAT.bat` | Çalışma anında pip install + NirSoft zip indirme | Installer her şeyi kuruyor |
| `lumina.log` | v1'in exe yanına yazdığı günlük | `%LOCALAPPDATA%\Lumina\logs\` altına döner günlüğe taşındı |

Ayrıca `assets/lumina_logo.png` (1024×1024 orijinal) korundu; uygulamanın
kullandığı 256 px sürüm ve `.ico` ondan üretiliyor.
