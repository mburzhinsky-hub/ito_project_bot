"""Build a standalone CMD with a verified embedded ZIP, using only stdlib."""
import base64
import hashlib
import io
from pathlib import Path
import textwrap
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def put(z, name, content):
    info = zipfile.ZipInfo(name, (2026, 9, 17, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, content)


def build():
    files = [ROOT / name for name in ('pyproject.toml', '.env.example', '.gitignore',
                                     'START_HERE.cmd', 'README.md')]
    files += sorted((ROOT / 'app').rglob('*.py'))
    files += sorted((ROOT / 'app' / 'prompts').glob('*.txt'))
    files += [ROOT / 'scripts' / name for name in (
        'setup-windows.ps1', 'configure-native.py', 'run-native.ps1',
        'status-windows.ps1', 'update-windows.ps1', 'backup-windows.ps1')]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for p in sorted(files):
            content = p.read_bytes()
            if p.suffix in ('.ps1', '.cmd'):
                content.decode('ascii')
                content = content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            put(z, p.relative_to(ROOT).as_posix(), content)
    payload = buf.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    bootstrap = (ROOT / 'scripts/unpack-installer.ps1').read_text('ascii')
    bootstrap = bootstrap.replace('__PAYLOAD_SHA256__', digest)
    header = '''@echo off
setlocal DisableDelayedExpansion
title ITO Project Bot Installer
set "ITO_BUNDLE=%~f0"
echo ITO PROJECT BOT - standalone installer - no Docker
echo All project files are included. Internet is needed for Python and APIs.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { $s=[IO.File]::ReadAllText($env:ITO_BUNDLE); $m=[regex]::Match($s,'(?s):ITO_SCRIPT_BEGIN\\r?\\n(.*?)\\r?\\n:ITO_SCRIPT_END'); if (-not $m.Success) { throw 'Incomplete installer' }; & ([scriptblock]::Create($m.Groups[1].Value)) } catch { Write-Host $_.Exception.Message; exit 1 }"
set "ITO_RESULT=%ERRORLEVEL%"
if not "%ITO_RESULT%"=="0" echo SETUP FAILED. Keep this window open and send a screenshot.
if "%ITO_RESULT%"=="0" echo Setup finished.
if not "%ITO_UNPACK_ONLY%"=="1" pause
exit /b %ITO_RESULT%
:ITO_SCRIPT_BEGIN
'''
    cmd = header + bootstrap.rstrip() + '\n:ITO_SCRIPT_END\n:ITO_ARCHIVE\n'
    cmd += '\n'.join(textwrap.wrap(base64.b64encode(payload).decode('ascii'), 76)) + '\n'
    cmd_bytes = cmd.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')
    instructions = '''ITO Project Bot — установка без Docker

1. Откройте START_HERE.cmd двойным щелчком. Можно прямо из этого ZIP.
2. Дождитесь установки Python и зависимостей (нужен интернет).
3. Вставьте Telegram Bot Token и OpenAI API Key. Ввод скрытый.

Весь проект встроен в START_HERE.cmd: соседние файлы ему не нужны.
Папка установки: %LOCALAPPDATA%\\ITOProjectBot
Ключи: .env в этой папке. База: data\\bot.db. Повторная распаковка их сохраняет.
Настройки: Москва, ежедневный отчёт в 18:00.
Старые данные из других папок автоматически не переносятся.

В Telegram: BotFather -> /setprivacy -> ваш бот -> Disable.
Добавьте бота в группу. Администратор группы отправляет /setup, затем /status.
Эти действия выполняет владелец Telegram; установщик не может сделать их за вас.

Окно установки можно закрыть после успеха. Отдельное свёрнутое окно бота
оставьте открытым. Автозапуск срабатывает при входе в Windows.
Во время сна или выключения компьютера бот не работает.
При ошибке отправьте скриншот окна без ключей. Не присылайте .env.
'''
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    (out / 'START_HERE.cmd').write_bytes(cmd_bytes)
    archive = out / 'ITO_BOT_WINDOWS.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        put(z, 'START_HERE.cmd', cmd_bytes)
        put(z, 'READ_ME.txt', instructions.encode('utf-8-sig'))
    print(f'{archive}: {archive.stat().st_size} bytes, {len(files)} embedded files')
    print('SHA256:', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
