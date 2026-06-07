# run_obod.py — ХИТРЫЙ КИТ: «По-китайски? Нет — по-одесски!»
# Запускаем без ошибок, даже если ошибки хотят запуститься первыми
import sys, os, traceback

def кит_говорит(текст):
    print(f"🐋 {текст}")

def кит_матюкается(текст):
    print(f"💢 {текст}")

print("""
╔══════════════════════════════════════════╗
║   🛸 ОБОД — Образная Обработка Данных   ║
║   v4.2 — финальная сборка               ║
║   Кит в рубке.                           ║
║   «Посмотрим, что тут у нас...»         ║
╚══════════════════════════════════════════╝
""")

# === ШАГ 1: ЕСТЬ ЛИ ФАЙЛЫ? ===
кит_говорит("Считаю файлы...")
нужны = ['obod.html', 'core_data.py', 'text_generator.py', 'ui_obod_qt.py']
потеряшки = []
for ф in нужны:
    if os.path.exists(ф):
        print(f"  ✅ {ф}")
    else:
        print(f"  ❌ {ф} — потерялся!")
        потеряшки.append(ф)

if потеряшки:
    кит_матюкается(f"Не могу найти: {', '.join(потеряшки)}")
    кит_говорит("Положи ВСЕ 4 файла в одну папку. Я подожду.")
    input("Нажми Enter, когда всё будет готово...")
    sys.exit(1)

# === ШАГ 2: ЕСТЬ ЛИ БИБЛИОТЕКИ? ===
кит_говорит("Проверяю библиотеки...")
try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel
    print(f"  ✅ PySide6 (версия {PySide6.__version__})")
except ImportError:
    кит_матюкается("PySide6 не установлен!")
    print("  pip install PySide6 PySide6-WebEngine")
    sys.exit(1)

# === ШАГ 3: РАБОТАЕТ ЛИ ЛОГИКА? ===
кит_говорит("Тестирую мозги (core_data + text_generator)...")
try:
    from core_data import get_all_numbers, analyze_mandala, check_compatibility, reduce_to_single
    from text_generator import OBDGenerator
    print("  ✅ Импорт — ок")
    
    # Тест на реальной дате
    r = get_all_numbers(15, 5, 1990)
    assert r['fate'] is not None, "fate = None!"
    assert r['soul'] is not None, "soul = None!"
    print(f"  ✅ Тест-драйв: fate={r['fate']}, soul={r['soul']}")
    
    m = analyze_mandala(15, 5, 1990)
    assert 'rich' in m, "Мандала без rich!"
    print(f"  ✅ Мандала: rich={m['rich']}, empty={m['empty']}")
    
    c = check_compatibility(1, 3)
    assert 'level' in c, "Совместимость без level!"
    print(f"  ✅ Совместимость (1+3): {c['level']}")
    
    g = OBDGenerator(r, m)
    txt = g.ecu_blob()
    assert len(txt) > 10, "Генератор выдал пустоту!"
    print(f"  ✅ Генератор: {txt[:60]}...")
    
except Exception as e:
    кит_матюкается(f"Ошибка в мозгах: {e}")
    traceback.print_exc()
    sys.exit(1)

# === ШАГ 4: ПОЕХАЛИ ===
кит_говорит("Все проверки пройдены.")
кит_говорит("Запускаю интерфейс...")
print("")
print("  ┌─────────────────────────────────┐")
print("  │  Если окно не появилось —       │")
print("  │  Alt+Tab или сверни терминал.   │")
print("  │  Кит уже в космосе! 🚀          │")
print("  └─────────────────────────────────┘")
print("")

try:
    from ui_obod_qt import main
    main()
except Exception as e:
    кит_матюкается(f"Крушение при запуске: {e}")
    traceback.print_exc()
    print("")
    кит_говорит("План Б: python ui_obod_qt.py")
    print("  Запусти напрямую, там будет полный traceback.")
    sys.exit(1)