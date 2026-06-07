# ui_obod_qt.py — ОБОД · Образная Обработка Данных
# v4.2 · финальные правки · готов к запуску
import sys
import os
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field

# Это должно быть ДО создания QApplication
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-logging --log-level=3"

from PySide6.QtCore import QUrl, QObject, Slot, QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

from core_data import (
    get_all_numbers,
    analyze_mandala,
    check_compatibility,
    reduce_to_single,
    NUMBER_MEANINGS,
    get_all_situational_scenarios,
    generate_full_report
)
from text_generator import OBDGenerator

# ══════════════════════════════════════════════════════════════
# ЛОГИРОВАНИЕ
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("OBOD")

HTML_FILE = os.path.join(os.path.dirname(__file__), 'obod.html')


# ══════════════════════════════════════════════════════════════
# БЕЗОПАСНОСТЬ — ИСПРАВЛЕНО
# ══════════════════════════════════════════════════════════════

def js_str(s):
    """Безопасная упаковка строки в JavaScript-литерал."""
    if s is None:
        return 'null'
    # json.dumps сам экранирует кавычки, переводы строк и спецсимволы
    return json.dumps(str(s), ensure_ascii=False)


def validate_date(d, m, y):
    """Строгая проверка даты через datetime."""
    try:
        datetime(y, m, d)
        return True
    except ValueError:
        return False


# ══════════════════════════════════════════════════════════════
# СОСТОЯНИЕ
# ══════════════════════════════════════════════════════════════

@dataclass
class OBODState:
    """Централизованное состояние приложения."""
    results: dict = None
    mandala: dict = None
    gen: object = None
    day: int = None
    month: int = None
    year: int = None
    tobolog: dict = field(default_factory=dict)
    vkb: dict = field(default_factory=dict)
    alexi: list = field(default_factory=list)

    def reset(self):
        """Полный сброс состояния."""
        self.results = None
        self.mandala = None
        self.gen = None
        self.day = None
        self.month = None
        self.year = None
        self.tobolog.clear()
        self.vkb.clear()
        self.alexi.clear()


# ══════════════════════════════════════════════════════════════
# АСИНХРОННЫЙ ВОРКЕР
# ══════════════════════════════════════════════════════════════

class ScanWorker(QThread):
    """Фоновый поток для тяжёлых вычислений."""
    finished = Signal(dict, dict)  # results, mandala
    error = Signal(str)

    def __init__(self, d, m, y):
        super().__init__()
        self.d = d
        self.m = m
        self.y = y

    def run(self):
        try:
            results = get_all_numbers(self.d, self.m, self.y)
            mandala = analyze_mandala(self.d, self.m, self.y)
            self.finished.emit(results, mandala)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════
# МОСТ — ИСПРАВЛЕНО (alexi_save + проверки)
# ══════════════════════════════════════════════════════════════

class Bridge(QObject):
    """Мост между Python и JavaScript."""

    def __init__(self, win):
        super().__init__()
        self.w = win
        self._scan_worker = None

    def _check_ready(self):
        """Проверяет, что HTML загружен и есть данные."""
        if not self.w._loaded:
            logger.warning("HTML ещё не загружен — вызов проигнорирован")
            return False
        return True

    @Slot(str)
    def scan(self, date_str):
        """Запуск сканирования по дате."""
        if not self._check_ready():
            return

        # Останавливаем предыдущее сканирование
        if self._scan_worker and self._scan_worker.isRunning():
            logger.warning("Прерывание предыдущего сканирования")
            self._scan_worker.quit()
            if not self._scan_worker.wait(2000):
                self._scan_worker.terminate()
                self._scan_worker.wait()
            self._scan_worker.deleteLater()
            self._scan_worker = None

        try:
            parts = date_str.strip().split('.')
            if len(parts) != 3:
                raise ValueError("Нужен формат ДД.ММ.ГГГГ")
            d, m, y = map(int, parts)
            if not validate_date(d, m, y):
                raise ValueError("Некорректная дата")
        except Exception as e:
            logger.warning(f"Ошибка даты: {e}")
            self.w.js(
                f"document.getElementById('bottomStatus').textContent="
                f"{js_str('❌ ошибка даты: ' + str(e)[:50])}"
            )
            return

        logger.info(f"Сканирование: {d:02d}.{m:02d}.{y}")
        self.w.js(
            "document.getElementById('bottomStatus').textContent='⏳ сканирование...'"
        )

        self._scan_worker = ScanWorker(d, m, y)
        self._scan_worker.finished.connect(self._on_scan_complete)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_worker.start()

    def _on_scan_complete(self, results, mandala):
        """Обработчик завершения сканирования."""
        self.w.state.results = results
        self.w.state.mandala = mandala
        self.w.state.day = self._scan_worker.d
        self.w.state.month = self._scan_worker.m
        self.w.state.year = self._scan_worker.y

        self.w.state.gen = OBDGenerator(
            self.w.state.results,
            self.w.state.mandala,
            self.w.state.tobolog,
            self.w.state.vkb,
            self.w.state.alexi
        )
        logger.info(
            f"Сканирование завершено: ECU={results.get('fate')}, "
            f"Ключ={results.get('soul')}"
        )
        self.w.update_all()
        self._scan_worker = None

    def _on_scan_error(self, error_msg):
        """Обработчик ошибки сканирования."""
        logger.error(f"ScanWorker failed: {error_msg}")
        self.w.js(
            f"document.getElementById('bottomStatus').textContent="
            f"{js_str('❌ ошибка сканирования: ' + error_msg[:50])}"
        )
        self._scan_worker = None

    @Slot(str)
    def compat(self, val):
        """Проверка совместимости с партнёром."""
        if not self._check_ready():
            return

        gen = self.w.state.gen
        results = self.w.state.results
        if not results or not gen:
            self.w.js(
                "document.getElementById('compatText').innerHTML="
                "'❌ Сначала выполните сканирование даты'"
            )
            self.w.js(
                "document.getElementById('compatResult').classList.add('visible')"
            )
            return

        try:
            val = val.strip()
            if not val.isdigit():
                raise ValueError("Введите число")
            num = int(val)
            if num < 1 or num > 1000:
                raise ValueError("Число от 1 до 1000")
            p = reduce_to_single(num)
            c = check_compatibility(results['fate'], p)
            txt = gen.compatibility_blob(c).replace("\n", "<br>")
            self.w.js(
                f"document.getElementById('compatText').innerHTML={js_str(txt)}"
            )
            self.w.js(
                "document.getElementById('compatResult').classList.add('visible')"
            )
        except ValueError as e:
            self.w.js(
                f"document.getElementById('compatText').innerHTML="
                f"{js_str('❌ ' + str(e))}"
            )
            self.w.js(
                "document.getElementById('compatResult').classList.add('visible')"
            )
        except Exception as e:
            logger.error(f"Ошибка совместимости: {e}")
            self.w.js(
                "document.getElementById('compatText').innerHTML="
                "'❌ Внутренняя ошибка'"
            )

    @Slot()
    def journal(self):
        """Показать бортовой журнал."""
        if not self._check_ready():
            return
        if not self.w.state.results or not self.w.state.gen:
            return

        scenarios = get_all_situational_scenarios(self.w.state.results)
        r = self.w.state.gen.full_story(scenarios=scenarios)
        self.w.js(
            f"document.getElementById('journalBody').textContent={js_str(r)}"
        )
        self.w.js(
            "document.getElementById('journalWindow').classList.add('visible')"
        )
        logger.info("Бортовой журнал открыт")

    @Slot()
    def clear_all(self):
        """Полный сброс системы."""
        logger.info("Сброс системы")
        self.w.state.reset()
        self.w.js("resetUI()")

    @Slot(str)
    def tobolog_save(self, json_str):
        """Сохранение результатов опросника ТОБОЛ."""
        if not self._check_ready():
            return
        try:
            arr = json.loads(json_str)
            self.w.state.tobolog.clear()
            for i, v in enumerate(arr):
                self.w.state.tobolog[i] = v
            self._regen()
            self.w.js(
                "document.getElementById('testsStatus').textContent"
                "='✅ стиль реакции сохранён'"
            )
            self.w.update_all()
            logger.info("ТОБОЛ сохранён")
        except Exception as e:
            logger.warning(f"Ошибка сохранения ТОБОЛ: {e}")

    @Slot(int)
    def vkb_save(self, level):
        """Сохранение уровня сигнала ВКБ."""
        if not self._check_ready():
            return
        try:
            level = int(level)
        except (TypeError, ValueError):
            return
        if 1 <= level <= 4:
            self.w.state.vkb['level'] = level
            self._regen()
            self.w.js(
                "document.getElementById('testsStatus').textContent"
                "='✅ уровень сигнала сохранён'"
            )
            self.w.update_all()
            logger.info(f"ВКБ сохранён: уровень {level}")

    @Slot(str)
    def alexi_save(self, json_str):
        """Сохранение результатов шкалы алекситимии."""
        if not self._check_ready():
            return
        try:
            self.w.state.alexi = json.loads(json_str)
            self._regen()
            self.w.js(
                "document.getElementById('testsStatus').textContent"
                "='✅ фильтр эмоций сохранён'"
            )
            self.w.update_all()
            logger.info("Алекситимия сохранена")
        except Exception as e:
            logger.warning(f"Ошибка сохранения алекситимии: {e}")

    def _regen(self):
        """Пересоздать генератор с текущим состоянием."""
        if self.w.state.results:
            self.w.state.gen = OBDGenerator(
                self.w.state.results,
                self.w.state.mandala,
                self.w.state.tobolog,
                self.w.state.vkb,
                self.w.state.alexi
            )


# ══════════════════════════════════════════════════════════════
# ГЛАВНОЕ ОКНО
# ══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Главное окно приложения ОБОД."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('ОБОД — Образная Обработка Данных')
        self.resize(600, 900)

        if not os.path.exists(HTML_FILE):
            logger.critical(f"Файл не найден: {os.path.abspath(HTML_FILE)}")
            QMessageBox.critical(
                self, "Ошибка",
                f"Файл не найден:\n{os.path.abspath(HTML_FILE)}"
            )
            sys.exit(1)

        self.state = OBODState()
        self._loaded = False
        self._update_pending = False

        self.web = QWebEngineView()
        self.setCentralWidget(self.web)
        
        settings = self.web.settings()
        settings.setFontFamily(settings.FontFamily.SansSerifFont, 'Share Tech Mono')
        settings.setFontFamily(settings.FontFamily.SansSerifFont, 'Share Tech Mono')
        settings.setFontFamily(settings.FontFamily.SansSerifFont, 'Share Tech Mono')
        settings.setFontFamily(settings.FontFamily.SansSerifFont, 'Share Tech Mono')
        
        # Настройки WebEngine
        settings = self.web.settings()
        settings.setDefaultTextEncoding('utf-8')
        
        # WebChannel ДО загрузки HTML
        page = self.web.page()
        ch = QWebChannel(page)
        self.bridge = Bridge(self)
        ch.registerObject('pybridge', self.bridge)
        page.setWebChannel(ch)
        
        # Загружаем qwebchannel.js
        qwebchannel_path = os.path.join(os.path.dirname(__file__), 'qwebchannel.js')
        qwebchannel_code = ''
        if os.path.exists(qwebchannel_path):
            with open(qwebchannel_path, 'r', encoding='utf-8') as f:
                qwebchannel_code = f.read()
        
        # Загружаем HTML
        with open(HTML_FILE, 'r', encoding='utf-8-sig') as f:
            html_content = f.read()

        # Вшиваем шрифт напрямую
        font_css = """
        @font-face {
            font-family: 'Share Tech Mono';
            src: url('ShareTechMono-Regular.ttf') format('truetype');
        }
        * { font-family: 'Share Tech Mono', monospace !important; }
        """
        html_content = html_content.replace('</head>', f'<style>{font_css}</style></head>')
        
        self.web.loadFinished.connect(self._on_load)
        self.web.setHtml(html_content, QUrl.fromLocalFile(os.path.abspath(HTML_FILE)))

        logger.info("Приложение запущено")

    def _on_load(self, ok):
        """Обработчик завершения загрузки HTML."""
        self._loaded = ok
        if ok:
            self.js("console.log('ОБОД: мост активирован')")
            logger.info("HTML загружен успешно")
        else:
            logger.error(f"Ошибка загрузки HTML: {os.path.abspath(HTML_FILE)}")

    def js(self, code):
        """Выполнить JavaScript в WebEngine."""
        if self._loaded:
            self.web.page().runJavaScript(code)
        else:
            logger.debug(f"JS отложен (HTML не загружен): {code[:80]}...")

    def update_all(self):
        """Запланировать обновление UI."""
        if self._update_pending:
            return
        self._update_pending = True
        QTimer.singleShot(50, self._do_update)

    def _do_update(self):
        """Фактическое обновление UI."""
        self._update_pending = False

        if not self._loaded:
            return

        r = self.state.results
        g = self.state.gen
        if not r or not g:
            return

        try:
            fate, soul = r['fate'], r['soul']
            fd = NUMBER_MEANINGS.get(fate, {})
            sd = NUMBER_MEANINGS.get(soul, {})
            ps = r.get('protocol_state', {})
            dr = r.get('driver_human', {})

            script = []

            # ECU ID
            script.append(
                f"document.getElementById('ecuNum').textContent={js_str(fate)}"
            )
            script.append(
                f"document.getElementById('ecuName').textContent={js_str(fd.get('name',''))}"
            )
            script.append(
                f"document.getElementById('ecuDesc').innerHTML={js_str(g.ecu_blob())}"
            )

            # Активационный ключ
            script.append(
                f"document.getElementById('keyNum').textContent={js_str(soul)}"
            )
            script.append(
                f"document.getElementById('keyName').textContent={js_str(sd.get('name',''))}"
            )
            script.append(
                f"document.getElementById('keyDesc').innerHTML={js_str(g.activation_blob())}"
            )

            # Связка ECU + Ключ
            script.append(
                f"document.getElementById('ecuLink').textContent={js_str(g.ecu_key_connection())}"
            )

            # Драйвер
            if dr:
                script.append(
                    f"document.getElementById('driverTitle').textContent="
                    f"{js_str('🔧 ДРАЙВЕР: ' + dr.get('name',''))}"
                )
                script.append(
                    f"document.getElementById('driverShort').textContent={js_str(dr.get('short',''))}"
                )
                script.append(
                    f"document.getElementById('driverDesc').textContent={js_str(dr.get('description',''))}"
                )
                script.append(
                    f"document.getElementById('driverStrength').textContent={js_str(dr.get('strength',''))}"
                )
                script.append(
                    f"document.getElementById('driverWeakness').textContent={js_str(dr.get('weakness',''))}"
                )

            # Диагностика прошивки
            if ps:
                script.append(
                    f"document.getElementById('diagName').textContent={js_str(ps.get('name',''))}"
                )
                script.append(
                    f"document.getElementById('diagRisk').textContent={js_str(ps.get('risk',''))}"
                )
                script.append(
                    f"document.getElementById('diagPractice').textContent={js_str(ps.get('practice',''))}"
                )
                warn = ps.get('emergency', '')
                if warn:
                    script.append(
                        f"document.getElementById('warnPlate').textContent="
                        f"{js_str('🚨 АВАРИЙНЫЙ ПРОТОКОЛ: ' + warn)}"
                    )
                    script.append(
                        "document.getElementById('warnPlate').style.display='block'"
                    )
                    script.append(
                        "document.getElementById('lampAlarm').className='lamp lamp-red'"
                    )

            # Ситуативные сценарии (шкалы)
            sc = get_all_situational_scenarios(r)
            if sc:
                for k in ['engine', 'memory', 'fuel', 'injection']:
                    s = sc.get(k, {})
                    sv = s.get('status_number', 5)
                    v = sv * 10
                    color = 'green' if v > 60 else ('amber' if v > 30 else 'red')
                    level = 'normal' if 4 <= sv <= 7 else ('low' if sv < 4 else 'high')
                    desc = g.scenario_blob(k, level)
                    # Добавьте эту строку:
                    script.append(
                        f"document.getElementById('{k}Desc').textContent={js_str(level)}"
                    )
                    script.append(
                        f"document.getElementById('{k}Fill').style.width='{v}%'"
                    )
                    script.append(
                        f"document.getElementById('{k}Fill').className='active-fill {color} pulse'"
                    )
                    script.append(
                        f"document.getElementById('{k}Val').textContent='{v}%'"
                    )
                    script.append(
                        f"document.getElementById('{k}Val').className='scale-value {color}'"
                    )
                    script.append(f"try{{window._details[{js_str(k)}]={{tech:{js_str(str(v)+'%')},human:{js_str(desc)}}}}}catch(e){{}}")

            # Мандала
            if self.state.day:
                script.append(
                    f"updateMandala({self.state.day},{self.state.month},{self.state.year})"
                )
            rich = [str(d) for d in self.state.mandala.get('rich', [])]
            empty = [str(d) for d in self.state.mandala.get('empty', [])]
            script.append(
                f"document.getElementById('mandalaRich').textContent="
                f"{js_str(' · '.join(rich) if rich else '--')}"
            )
            script.append(
                f"document.getElementById('mandalaEmpty').textContent="
                f"{js_str(' · '.join(empty) if empty else '--')}"
            )

            # Тесты
            script.append(
                f"document.getElementById('testsIntro').textContent={js_str(g.tests_intro())}"
            )

            # Индикаторы
            script.append(
                "document.getElementById('lampSystem').className='lamp lamp-green'"
            )
            script.append(
                "document.getElementById('bottomStatus').textContent='борт активен'"
            )

            # Собираем и выполняем
            js_code = ";".join(script)
            self.js(js_code)

        except Exception as e:
            logger.error(f"Ошибка в _do_update: {e}", exc_info=True)
            self.js(
                "document.getElementById('bottomStatus').textContent='❌ ошибка интерфейса'"
            )

    def closeEvent(self, event):
        """Ручная очистка для предотвращения утечек памяти."""
        logger.info("Закрытие приложения")
        if self.bridge._scan_worker and self.bridge._scan_worker.isRunning():
            self.bridge._scan_worker.quit()
            self.bridge._scan_worker.wait(1000)

        self.web.page().setWebChannel(None)
        self.bridge.deleteLater()
        self.web.deleteLater()
        event.accept()


# ══════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()