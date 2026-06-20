# 🔥 Gothbreach OpenCode

> **Форк OpenCode (anomalyco/opencode) — без телеметрии, с мульти-агентами, deepseek-v4-pro по умолчанию**

## Что внутри

```
✅ Sentry выпилен — ничто не уходит на сервера OpenCode
✅ Встроенный прокси (opencode-llm-proxy) — любые модели через локальный gateway
✅ 10 специализированных агентов (build, plan, architect, critic, debugger, refactor, security, docs, test, react/python/go/rust)
✅ DeepSeek V4 Pro по умолчанию (базовая + малая модель)
✅ Алиасы провайдеров: gothbreach-proxy + gothbreach-direct
✅ Полный контроль — никаких лимитов, никакой телеметрии
```

## Быстрый старт

### 1. Установка

```bash
# Из корня репозитория
bun install

# Сборка CLI
bun run build --cwd packages/opencode

# Сборка Desktop
bun run build:desktop --cwd packages/desktop
```

### 2. Запуск прокси

```bash
# Вариант A: gothbreach-proxy (opencode-llm-proxy) — универсальный
cd packages/gothbreach-proxy
bun install
bun run start
# → слушает на http://127.0.0.1:4010

# Вариант B: gothbreach-direct (наш Python прокси)
python scripts/gothbreach_oc_proxy.py
# → слушает на http://127.0.0.1:20131
```

### 3. Конфигурация

```bash
# Скопировать конфиг в домашнюю директорию
cp gothbreach-config.json ~/.config/opencode/opencode.json

# Или использовать через OPENCODE_CONFIG
export OPENCODE_CONFIG=./gothbreach-config.json
opencode
```

### 4. Использование агентов

```bash
# Базовый режим — просто opencode в директории
opencode

# С конкретным агентом
opencode --agent architect
opencode --agent critic
opencode --agent security

# Мульти-агент (swarm) — все агенты работают параллельно
opencode --agent-swarm

# Планирование перед кодом
opencode --agent plan

# Тестирование
opencode --agent test
```

## Структура агентов

| Агент | Модель | Задача |
|-------|--------|--------|
| `build` | deepseek-v4-pro | Главный оркестратор |
| `plan` | deepseek-v4-pro | Планирование |
| `architect` | deepseek-v4-pro | Архитектура |
| `critic` | deepseek-v4-pro | Code review |
| `debugger` | deepseek-v4-pro | Отладка |
| `refactor` | deepseek-v4-pro | Рефакторинг |
| `security` | deepseek-v4-pro | Аудит безопасности |
| `docs` | deepseek-v4-pro | Документация |
| `test` | deepseek-v4-flash | Тестирование |
| `react` | deepseek-v4-pro | React/Next.js |
| `python` | deepseek-v4-pro | Python |
| `golang` | deepseek-v4-pro | Go |
| `rust` | deepseek-v4-pro | Rust |

## Провайдеры

| Алиас | URL | Назначение |
|-------|-----|-----------|
| `gothbreach-proxy` | `127.0.0.1:4010` | Универсальный LLM gateway (любые модели) |
| `gothbreach-direct` | `127.0.0.1:20131` | Прямой доступ к OpenCode Zen API |

## Отличие от оригинала

| Функция | Оригинал | Gothbreach |
|---------|----------|------------|
| Sentry | ✅ есть | ❌ выпилен |
| Телеметрия | ✅ PostHog | ❌ выпилена |
| Sourcemaps | ✅ включены | ❌ выключены |
| Модель по умолч. | tokenrouter/... | deepseek-v4-pro |
| Провайдеры | внешние | встроенные алиасы |
| Агенты | 3-5 | 13 специализированных |
| Прокси | нет | встроенный opencode-llm-proxy |
| Swarm | нет | ✅ agent_swarm: true |

## Сборка из исходников

```bash
# Требования
# - Bun 1.3+
# - Go (для нативных зависимостей)

cd gothbreach-opencode

# Установка всех зависимостей
bun install

# Сборка Linux/macOS CLI
bun run build --cwd packages/opencode

# Сборка Windows CLI
bun run build --cwd packages/opencode --target=windows-x64

# Сборка Desktop (Electron)
bun run build:desktop --cwd packages/desktop

# Результат в packages/opencode/dist/ или packages/desktop/dist/
```

## Лицензия

MIT (как и оригинальный OpenCode)
