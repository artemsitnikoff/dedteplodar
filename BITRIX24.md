# Bitrix24 — интеграция бота как первой линии поддержки

Справочник по работе с Bitrix24 (Б24) для этого проекта. Собран из официальной документации
(ссылки в конце) и из реального перехваченного запроса. Цель — не ходить по URL каждый раз.

**Статус на 2026-09-21:** реализованы **этапы 1–2** (ветка `bitrix24`, в `main` не влито, на стенд не выкачено).
- Этап 1 — приём вебхука: `POST /api/v1/b24/events` (`admin/routers/b24.py`, парсер/верификация
  `src/b24/webhook.py`). Проверяет `application_token`, разбирает form-urlencoded, отвечает 200.
- Этап 2 — ответ клиенту: `admin/services/b24_service.py` (фон после 200: дедуп → плейсхолдер «ищу ответ» →
  `answer_with_meta` → журнал → правка плейсхолдера в ответ + кнопка «Позвать оператора»),
  REST-клиент `src/b24/client.py`, конвертер HTML→BBCode `src/b24/format.py`. Кнопка/слова «оператор»
  пока дают заглушку с телефонами — настоящая передача в этапе 3.
- Тесты: `PYTHONPATH=. pytest tests/ -q` (50 кейсов на реальной форме события).
- **Не проверено на живом портале:** регистр ключей клавиатуры (`fields.keyboard` + `TEXT/ACTION/...`),
  поведение `imbot.v2.Chat.Message.update` в чате линии, что `ACTION: SEND` приходит как `ONIMBOTV2MESSAGEADD`.
  Проверять первым делом после деплоя.

Разработчик Б24 со своей стороны уже зарегистрировал бота и тестовую линию; после деплоя ему нужно
переключить `webhookUrl` на `http://5.253.228.164:8001/api/v1/b24/events` (HTTPS — см. §2).

---

## 1. Задача и модель интеграции

Сейчас обращения клиентов из чата на сайте уходят в Б24 напрямую менеджеру. Нужно поставить наш
RAG-бот **перед** человеком: клиент пишет в чат → отвечает бот → если не помог, диалог переводится
оператору. Для нас это **ещё один канал вопросов**, рядом с Telegram и веб-чатом: та же
`answer_with_meta`, тот же журнал `query_logs`, тот же LLM-judge.

Механика на стороне Б24:

```
Клиент (виджет на сайте / online-страница линии)
   │
   ▼
Открытая линия (Open Lines) — очередь: [чат-бот] → [операторы]
   │  событие ONIMBOTV2MESSAGEADD
   ▼  POST form-urlencoded на наш webhookUrl
Наш сервер (FastAPI admin, публичный POST-эндпоинт)
   │  answer_with_meta(...)  ~30-40 с
   ▼
REST Б24: imopenlines.bot.session.message.send  (ответ клиенту от имени бота)
        или imbot.v2.Chat.Message.send           (то же, но с кнопками/вложениями)
   │
   ▼ если нужен человек
REST Б24: imopenlines.bot.session.operator | .transfer   (передача оператору/в очередь)
        imopenlines.bot.session.finish                   (закрыть диалог)
```

Что уже есть на стороне Б24 (сделал их разработчик):

| Что | Значение |
|---|---|
| Портал | `teplodar.bitrix24.ru` |
| Бот | `code = ai_dc_bot`, `id = 511`, локальное приложение `client_id = local.6aa90e31e70e69.*` |
| Scope | `imbot,imopenlines` — хватает и на ответы, и на передачу оператору |
| Тестовая линия | `id = 13`, публичная страница чата: https://teplodar.bitrix24.ru/online/demo-ai |
| Обработчик событий | пока указывает на `http://5.253.228.164:8001/health` (GET-only → Б24 получает 405) |
| `event_handler_id` | `111` |

---

## 2. Аутентификация и безопасность

В каждом webhook-запросе **два уровня** auth:

| Где | Что | Для чего |
|---|---|---|
| `auth.application_token` (верхний уровень) | Постоянный секрет портала для нашего приложения. Одинаковый во всех запросах. | **Проверять на входе.** Не совпал → 403. Хранить в `.env` как `B24_APPLICATION_TOKEN`. |
| `data.bot.auth.access_token` | OAuth-токен, живёт `expires_in = 3600` с. Приходит **свежий в каждом событии**. | Обратные вызовы REST от имени бота: ответить в чат, передать оператору. |
| `data.bot.auth.refresh_token` | Долгоживущий. | Обновление access_token. **Нам не нужен**: отвечаем сразу по токену из события. |
| `data.bot.auth.client_endpoint` | `https://teplodar.bitrix24.ru/rest/` | База для REST-вызовов. |

Вызов REST с OAuth: `POST {client_endpoint}{method}` с полем `auth=<access_token>` в теле (JSON или form).

Важно:

- **Текущий обработчик — `http://`, без TLS.** Токены доступа и обновления ушли по интернету
  открытым текстом (подтверждено перехватом). Для боевого вебхука нужен **домен + HTTPS** (nginx +
  Let's Encrypt перед портом 8001). Документация тоже требует HTTPS для `webhookUrl`.
- Порт 8001 открыт в интернет и его постоянно сканируют. Вебхук будет без basic-auth, поэтому
  проверка `application_token` обязательна, плюс лимит на размер тела и rate-limit.
- Обновление токена по refresh_token: страница OAuth в apidocs не нашлась (404). По общей схеме Б24:
  `GET https://oauth.bitrix24.tech/oauth/token/?grant_type=refresh_token&client_id=…&client_secret=…&refresh_token=…`.
  Нужен `client_secret` локального приложения — он у разработчика Б24. **Не проверено**, низкий приоритет.

---

## 3. События (imbot v2)

| Событие | Когда | Нам |
|---|---|---|
| `ONIMBOTV2MESSAGEADD` | Новое сообщение боту | **Основное.** Текст клиента → RAG |
| `ONIMBOTV2JOINCHAT` | Бота добавили в чат / пригласили | Можно слать приветствие; для линии обычно не нужно |
| `ONIMBOTV2COMMANDADD` | Нажата кнопка с `COMMAND` или введена слэш-команда | Кнопка «Позвать оператора», если делать через команды |
| `ONIMBOTV2MESSAGEUPDATE` / `DELETE` | Сообщение изменено / удалено | Игнорировать |
| `ONIMBOTV2CONTEXTGET` | Пользователь открыл диалог с контекстом | Игнорировать |
| `ONIMBOTV2REACTIONCHANGE` | Реакция на сообщение бота | Можно маппить на 👍/👎 в журнал (потом) |
| `ONIMBOTV2DELETE` | Бот удалён из портала | Логировать |

Подписка на события создаётся автоматически при регистрации бота с `eventMode: "webhook"`;
`event.bind` вручную не нужен. Режим `fetch` (`imbot.v2.Event.get`) — альтернатива без публичного
URL, но тогда нужен постоянный опрос; нам не подходит.

### 3.1. Формат webhook-запроса (подтверждено перехватом 2026-09-16)

```
POST /health HTTP/1.1
Host: 5.253.228.164:8001
User-Agent: Bitrix24 Webhook Engine
Content-Type: application/x-www-form-urlencoded
Content-Length: 4622
Accept-Encoding: gzip
Connection: close
```

- Тело — **не JSON**, а `http_build_query` (PHP): вложенные ключи `data[message][text]=…`.
  В Python: `urllib.parse.parse_qsl(body, keep_blank_values=True)` + сборка вложенного dict по `[...]`.
  FastAPI `await request.form()` даёт плоские ключи `data[message][text]`, их тоже надо разворачивать.
- **Все скаляры — строки**: `"511"`, `"0"`/`"1"` вместо bool, `""` вместо null. Приводить явно.
- Источники: `89.208.230.2` (VK Cloud), `195.208.184.200` (Corp Soft) — инфраструктура Bitrix24.ru.
  Не фильтровать по IP, они могут меняться; проверять `application_token`.

### 3.2. Поля `ONIMBOTV2MESSAGEADD`, которые нам нужны

| Поле | Пример | Использование |
|---|---|---|
| `event` | `ONIMBOTV2MESSAGEADD` | роутинг |
| `data.message.text` | `посоветуйте печь на 14 кубов` | вопрос → `answer_with_meta` |
| `data.message.id` | `1093189` | дедуп повторных доставок |
| `data.message.chatId` | `19167` | `CHAT_ID` для `imopenlines.bot.session.*` |
| `data.message.date` | `2026-09-16T11:05:01+03:00` | лог |
| `data.chat.dialogId` | `chat19167` | `dialogId` для `imbot.v2.Chat.Message.send` |
| `data.chat.type` / `entityType` | `lines` / `LINES` | **обрабатывать только `LINES`** |
| `data.chat.entityId` | `livechat\|13\|19165\|515` | коннектор \| id линии \| id сессии линии \| id пользователя |
| `data.chat.name` | `Синий гость №7 - Demo онлайн чат с AI ботом` | лог |
| `data.user.id` | `515` | синтетический `user_id` для журнала |
| `data.user.name` | `Гость` | клиент приходит как extranet-гость: `connector=1`, `externalAuthId=imconnector`, без email/телефона |
| `data.user.bot` | `0` | если `1` — игнорировать (сообщение от бота) |
| `data.bot.id` / `code` | `511` / `ai_dc_bot` | `botId` для отправки |
| `data.bot.auth.access_token` / `client_endpoint` | … | REST-вызовы |
| `data.language` | `ru` | |
| `auth.application_token` | `c76f868e…cd7c` | проверка подлинности |
| `ts` | `1789545901` | unix-время события |

Полный перехваченный payload (токены замаскированы) — в приложении A.

### 3.3. Требования к обработчику

- Б24 ждёт **HTTP 200**. Повторная доставка **не гарантируется**.
- Таймаут ответа в документации не указан. Наш RAG-ответ занимает 30–40 с — держать соединение
  столько нельзя. **Схема: сразу 200, обработка в фоне, ответ клиенту отдельным REST-вызовом.**
- В перехвате видно парные доставки одного события с разницей в микросекунды. Дедупить по
  `data.message.id`.

---

## 4. Ответ клиенту

Два способа. Оба требуют scope `imopenlines,imbot`, оба вызываются с `auth=<access_token из события>`.

### 4.1. `imopenlines.bot.session.message.send` — рекомендован туториалом для линий

| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `CHAT_ID` | int | да | `data.message.chatId` |
| `NAME` | string | нет | `DEFAULT` — взять текст из `MESSAGE`; `WELCOME` — приветствие из настроек линии |
| `MESSAGE` | string | нет | текст (BBCode) |

Ответ: `{"result": true}` — **без id сообщения**, факт доставки не подтверждается.
Ошибки: `CHAT_ID_EMPTY` (400), `WRONG_AUTH_TYPE` (403).

```bash
curl -X POST https://teplodar.bitrix24.ru/rest/imopenlines.bot.session.message.send \
  -H 'Content-Type: application/json' \
  -d '{"CHAT_ID": 19167, "NAME": "DEFAULT", "MESSAGE": "[b]Русь-12 Л[/b] подойдёт для парной 8–14 м³", "auth": "<access_token>"}'
```

### 4.2. `imbot.v2.Chat.Message.send` — когда нужны кнопки / вложения / id сообщения

| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `botId` | int | да | `data.bot.id` (511) |
| `dialogId` | string | да | `chat{chatId}` → `data.chat.dialogId` |
| `fields.message` | string | да* | текст BBCode, до 20 000 символов (*если нет attach) |
| `fields.keyboard` | array | нет | кнопки, см. §6 |
| `fields.attach` | array | нет | карточки-вложения |
| `fields.urlPreview` | bool | нет | превью ссылок (по умолчанию true) |
| `fields.replyId` | int | нет | ответ на сообщение |
| `fields.system` | bool | нет | системное сообщение |
| `botToken` | string | webhook-only | не нужен для OAuth-приложения (наш случай) |

Ответ: `{"result": {"id": 789, "uuidMap": {}}}`.
Ошибки: `BOT_ID_REQUIRED`, `BOT_NOT_FOUND`, `ACCESS_DENIED` (бот не в чате), `EMPTY_MESSAGE`, `SENDING_FAILED`.

```bash
curl -X POST https://teplodar.bitrix24.ru/rest/imbot.v2.Chat.Message.send \
  -H 'Content-Type: application/json' \
  -d '{"botId": 511, "dialogId": "chat19167", "fields": {"message": "Текст ответа", "keyboard": [{"TEXT": "Позвать оператора", "ACTION": "SEND", "ACTION_VALUE": "Позвать оператора", "BG_COLOR_TOKEN": "alert"}]}, "auth": "<access_token>"}'
```

Соседние методы: `imbot.v2.Chat.Message.update` (в т.ч. убрать клавиатуру: `KEYBOARD: "N"`),
`.delete`, `.read`, `.get`, `.getContext`, `.reaction.add/.delete`.

**Рекомендация:** первый этап — `imbot.v2.Chat.Message.send` (даёт id сообщения и кнопку
«Позвать оператора»). Если окажется, что в линии он ведёт себя иначе, откатиться на
`imopenlines.bot.session.message.send`.

---

## 5. Форматирование текста — только BBCode

Markdown и HTML **не поддерживаются**. Наш генератор отдаёт HTML (`b, i, code, a, br`) — нужен
конвертер HTML → BBCode для этого канала (аналог `_md_to_html`, но в другую сторону).

| HTML у нас | BBCode в Б24 |
|---|---|
| `<b>…</b>` | `[b]…[/b]` |
| `<i>…</i>` | `[i]…[/i]` |
| `<code>…</code>` | `[code]…[/code]` |
| `<a href="URL">текст</a>` | `[url=URL]текст[/url]` |
| голый URL | `[url]URL[/url]` или как есть (превью включено) |
| `<br>` / `\n` | `[br]` или `\n` |
| `&amp; &lt; &gt;` | раскодировать в `& < >` |

Прочее: `[u]`, `[s]`, `[size=8..30]`, `[color=#hex]`, цитата — строка с `>>`, `[user=id]Имя[/user]`,
`[put=текст]…[/put]` (вставить в поле ввода), `[send=текст]…[/send]` (отправить сразу),
`[call=+7…]…[/call]`, `[img size=small|medium|large]URL [/img]` (пробел перед закрытием),
`[icon=URL size=20 title=…]`, `[timestamp=UNIX format=…]`, `[disk=ID]`.

Внимание на URL с подчёркиваниями (`kaskad_12_t`) — как и в Telegram, ссылки не должны проходить
через какой-либо markdown-конвертер.

---

## 6. Клавиатура (кнопки под сообщением)

`fields.keyboard` — массив кнопок (сокращённая форма) или `{"BOT_ID": 511, "BUTTONS": [...]}`.

| Поле | Значения | Описание |
|---|---|---|
| `TEXT` | string | текст кнопки, обязателен |
| `TYPE` | `NEWLINE` | перенос ряда |
| `LINK` | URL | кнопка-ссылка |
| `COMMAND` / `COMMAND_PARAMS` | string | команда боту → событие `ONIMBOTV2COMMANDADD`; **требует `imbot.v2.Command.register`** |
| `ACTION` / `ACTION_VALUE` | `PUT`, `SEND`, `COPY`, `CALL`, `DIALOG` | действие без регистрации команды: `SEND` = отправить текст в чат от имени клиента |
| `BLOCK` | `Y/N` | заблокировать кнопку после нажатия (только COMMAND) |
| `DISABLED` | `Y/N` | неактивна |
| `DISPLAY` | `LINE` / `BLOCK` | в строке / отдельным блоком |
| `WIDTH` | int | ширина, px |
| `BG_COLOR` / `TEXT_COLOR` | HEX | цвета |
| `BG_COLOR_TOKEN` | `primary`, `secondary`, `alert`, `base` | цвет по токену |
| `CONTEXT` | `MOBILE`, `DESKTOP`, `ALL` | где показывать |

Два варианта кнопки «Позвать оператора»:

1. **`ACTION: SEND`** — нажатие отправляет в чат текст (например «Позвать оператора») как обычное
   сообщение клиента → приходит `ONIMBOTV2MESSAGEADD`, ловим по тексту. Регистрировать ничего не надо.
   **Проще, начать с него.**
2. **`COMMAND`** — приходит `ONIMBOTV2COMMANDADD` с `command.context = keyboard|textarea|menu`.
   Чище, но требует регистрации команды через `imbot.v2.Command.register` (делает владелец приложения).

Убрать клавиатуру после нажатия: `imbot.v2.Chat.Message.update` с `KEYBOARD: "N"` и `BOT_ID`.

---

## 7. Управление сессией Открытой линии (эскалация)

Все методы: scope `imopenlines,imbot`, ответ `{"result": true}`, `CHAT_ID` = `data.message.chatId`.
Сессионная авторизация запрещена (`WRONG_AUTH_TYPE`). `transfer` и `finish` доступны только
«пользователю приложения с зарегистрированным ботом» — т.е. по токену из `data.bot.auth`.

| Метод | Параметры | Что делает |
|---|---|---|
| `imopenlines.bot.session.operator` | `CHAT_ID` | Передать **первому свободному оператору** линии. Ошибка `WRONG_CHAT` — диалог уже у оператора. |
| `imopenlines.bot.session.transfer` | `CHAT_ID`, один из: `USER_ID` (сотрудник), `QUEUE_ID` (очередь, id из `imopenlines.config.list.get`), `TRANSFER_ID` (`<user_id>` или `queue<QUEUE_ID>`); `LEAVE` = `Y` (бот сразу выходит) / `N` (остаётся до подтверждения, по умолчанию); `CLIENT_ID` (только для webhook-ботов, для OAuth не нужен) | Передать конкретному оператору или в очередь. Ошибки `TRANSFER_ID_EMPTY`, `OPERATOR_WRONG`. |
| `imopenlines.bot.session.finish` | `CHAT_ID`, `CLIENT_ID` (только webhook) | Завершить диалог. Ошибка `BOT_ID_ERROR` — бот не зарегистрирован в приложении. |

После передачи новые сообщения клиента идут **оператору, а не боту**. При `LEAVE: N` бот остаётся
наблюдателем. Вся история (ответы бота, момент подключения оператора) видна в сессии линии.

```bash
curl -X POST https://teplodar.bitrix24.ru/rest/imopenlines.bot.session.operator \
  -H 'Content-Type: application/json' \
  -d '{"CHAT_ID": 19167, "auth": "<access_token>"}'
```

---

## 8. Регистрация бота и настройка линии (сторона Б24)

Делает разработчик Б24, нам важно знать параметры:

- `imbot.v2.Bot.register` (идемпотентен по `code`): `code`, `type: "bot"`, **`isSupportOpenline: true`**
  (без него бот не работает в линиях), `eventMode: "webhook"`, `webhookUrl` (**HTTPS**),
  `eventTypes` (минимум `MESSAGEADD, COMMANDADD, JOINCHAT, DELETE`), `properties: {name, workPosition, color, avatar}`,
  `botToken` ≤ 40 символов (только для webhook-авторизации; у OAuth-приложения не нужен).
- Сменить адрес обработчика: `imbot.v2.Bot.update`. **Именно это попросим сделать, когда появится наш эндпоинт.**
- Линия: Контакт-центр → Открытые линии → линия → блок «Чат-бот»: выбрать бота и момент подключения
  (при первом обращении). Без привязки к линии события не приходят.
- Бот получает события из **всех** своих чатов — фильтровать `data.chat.entityType == "LINES"`.
- Устаревшие `imbot.*` (v1) не использовать, только `imbot.v2.*`.

---

## 9. MCP-сервер Bitrix24 — для разработки, не для рантайма

`https://mcp-dev.bitrix24.tech/mcp` — публичный MCP-сервер **с документацией REST API** (без
доступа к данным портала, без авторизации). Инструменты: `bitrix-search`, `bitrix-method-details`,
`bitrix-event-details`, `bitrix-article-details`, `bitrix-app-development-doc-details`.
Для сценария «бот отвечает клиентам» не подходит, но полезен нам при написании кода — вместо ручных
походов по apidocs:

```bash
claude mcp add --transport http bitrix24-docs https://mcp-dev.bitrix24.tech/mcp
```

---

## 10. План нашего эндпоинта (не реализовано)

Цель — «ещё один канал» для `answer_with_meta`, максимально повторяющий `admin/routers/chat.py`.

1. ✅ **Роут** `POST /api/v1/b24/events` в admin (FastAPI), **без basic-auth** (префикс `/api/v1/b24/`
   в `_AUTH_FREE_PREFIXES` в `admin/main.py`), лимит тела 256 КиБ → 413. `GET` на тот же URL — проба для браузера.
2. ✅ **Проверка** `auth.application_token == settings.b24_application_token` (`compare_digest`) → иначе 403;
   токен не задан → 503 (fail closed).
3. ✅ **Разбор** form-urlencoded во вложенный dict (`src/b24/webhook.py:parse_php_form`) и типизация в
   `B24Event`; `B24Event.should_answer` = `ONIMBOTV2MESSAGEADD` + `entityType == LINES` + автор не бот + непустой текст.
4. ✅ **Дедуп** по `data.message.id` (LRU 2000 в `b24_service.mark_seen`), т.к. повторы приходят.
5. ✅ **Ответ 200 сразу**, работа — `asyncio.create_task` со strong-ref (`spawn_handle_event`).
6. **Состояние сессии** (новая таблица SQLite, ключ `chat_id`): `bot | handoff_pending | operator | closed`.
   Если `operator` — бот молчит. Сейчас бот stateless, это новое.
7. ✅ **Генерация**: `answer_with_meta(session, text, user_id=synthetic)` — история подтягивается из
   `query_logs` по синтетическому `user_id` (ключ — `chat_id`, окно 30 мин как у Telegram). Сразу шлётся
   плейсхолдер «Секунду, ищу ответ…», затем он редактируется в ответ (`imbot.v2.Chat.Message.update`);
   если правка не удалась — новое сообщение.
8. ✅ **Конвертация** HTML → BBCode (`src/b24/format.py`, §5), кнопка «Позвать оператора» (`ACTION: SEND`,
   `b24_service.operator_keyboard`).
9. **Эскалация** → `imopenlines.bot.session.operator` (или `transfer` в очередь, если Б24 скажут id).
   Триггеры: текст кнопки/«оператор»/«человек»; intent личного заказа (уже есть правило в
   `intent_extractor`); нет чанков / низкий `top_score`; N-й 👎 или переспрос. Перед передачей —
   отправить оператору сводку (транскрипт + категория) сообщением в чат, чтобы клиент не повторялся.
10. ✅ **Журнал**: `query_logs` с `user_id = synthetic_user_id("b24:chat<chat_id>")`,
    `username = "b24:<имя>#<user_id>"`, `bot_message_id` = id плейсхолдера; judge через общий
    `admin/services/judge_service.py` (туда же переехал judge веб-чата). Запрос оператора пишется как
    `query_type = OPERATOR`.
11. ✅(частично) **Env**: `B24_APPLICATION_TOKEN`, `B24_BOT_ID=511` — уже в `config.py`/`.env.example`; опц. `B24_OPERATOR_QUEUE_ID` / `B24_OPERATOR_USER_ID`,
    `B24_PUBLIC_URL` (для документации/логов). `client_endpoint` и `access_token` берём из события.
12. **Инфра**: домен + nginx + HTTPS перед 8001; после этого попросить Б24 обновить `webhookUrl`
    через `imbot.v2.Bot.update`. Деплой ручной: `ssh deploy@5.253.228.164`, `/var/www/dedteplodar`,
    `git pull && docker compose up -d --build admin`.

Отладка входящих запросов без кода: tcpdump в контейнере с сетью хоста (у `deploy` нет sudo, но
есть docker): `docker run -d --name cap --net=host --cap-add=NET_ADMIN --cap-add=NET_RAW -v ~/cap:/cap alpine sh -c 'apk add -q tcpdump && exec tcpdump -i eth0 -s0 -U -w /cap/b24.pcap tcp dst port 8001'`.
После — удалить дамп, в нём живые токены.

---

## 11. Открытые вопросы к разработчику Б24

- Будет ли у стенда домен для HTTPS, или нам поднимать nginx + certbot самим?
- Куда эскалировать: первому свободному (`operator`) или в конкретную очередь / сотруднику
  (`transfer`, нужен `QUEUE_ID` / `USER_ID`)?
- Ожидание по времени ответа бота: 30–40 с приемлемо? Нужно ли промежуточное «ищу ответ»?
- Есть ли у клиента в боевой линии контакты (телефон/почта) или он всегда «Гость»?
- Нужен ли `client_secret` для refresh_token (скорее нет) и кто его хранит?
- Регистрировать ли команду для кнопки оператора (`imbot.v2.Command.register`) или достаточно `ACTION: SEND`?
- Что делать после ответа оператора: закрывать сессию `finish` должен бот или оператор?

---

## 12. Источники

- События imbot v2: https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/events/events.html
- Отправка сообщения: https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/messages/chat-message-send.html
- Форматирование (BBCode): https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/messages/message-formatting.html
- Клавиатуры: https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/messages/message-keyboards.html
- Раздел «Сообщения» (update/delete/attach): https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/messages/index.html
- Регистрация бота: https://apidocs.bitrix24.ru/api-reference/chat-bots/chat-bots-v2/imbot.v2/bots/bot-register.html
- Боты в Открытых линиях (обзор): https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/chat-bots/index.html
  - https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/chat-bots/imopenlines-bot-session-message-send.html
  - https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/chat-bots/imopenlines-bot-session-operator.html
  - https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/chat-bots/imopenlines-bot-session-transfer.html
  - https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/chat-bots/imopenlines-bot-session-finish.html
- Туториал «бот для Открытых линий»: https://apidocs.bitrix24.ru/tutorials/chat-bots/open-lines-bot.html
- MCP-сервер документации: https://apidocs.bitrix24.ru/ai-tools/mcp.html

---

## Приложение A. Реальный `ONIMBOTV2MESSAGEADD` (перехват 2026-09-16 11:05 МСК, токены замаскированы)

Пригодится как фикстура для парсера. В исходном виде это form-urlencoded, здесь расшифровано.

```json
{
  "event": "ONIMBOTV2MESSAGEADD",
  "event_handler_id": "111",
  "data": {
    "bot": {
      "id": "511",
      "code": "ai_dc_bot",
      "auth": {
        "access_token": "6c5baa6a…2757",
        "expires": "1789549420",
        "expires_in": "3600",
        "scope": "imbot,imopenlines",
        "domain": "teplodar.bitrix24.ru",
        "server_endpoint": "https://oauth.bitrix24.tech/rest/",
        "status": "L",
        "client_endpoint": "https://teplodar.bitrix24.ru/rest/",
        "member_id": "61fe44d3770c22e3fab7bff06b17e7e3",
        "refresh_token": "5cdad16a…fe9e",
        "user_id": "511",
        "client_id": "local.6aa90e31e70e69.88323722",
        "application_token": "c76f868e…cd7c"
      }
    },
    "message": {
      "id": "1093189",
      "chatId": "19167",
      "chat_id": "19167",
      "authorId": "515",
      "author_id": "515",
      "date": "2026-09-16T11:05:01+03:00",
      "text": "ыфвфывфвывфы",
      "isSystem": "0",
      "viewedByOthers": "0"
    },
    "chat": {
      "id": "19167",
      "dialogId": "chat19167",
      "type": "lines",
      "entityType": "LINES",
      "entityId": "livechat|13|19165|515",
      "entityLink": { "type": "LINES", "url": "", "id": "livechat|13|19165|515" },
      "entityData1": "N|NONE|0|N|N|171|1789465580|0|0|0",
      "entityData2": "",
      "entityData3": "",
      "name": "Синий гость №7 - Demo онлайн чат с AI ботом",
      "messageType": "L",
      "owner": "0",
      "parentChatId": "0",
      "parentMessageId": "0",
      "avatar": "",
      "color": "#3e99ce",
      "description": "",
      "diskFolderId": "0",
      "extranet": "0",
      "containsCollaber": "0",
      "hasManageCapability": "0",
      "isNew": "0",
      "textFieldEnabled": "1",
      "permissions": {
        "manageUsersAdd": "member", "manageUsersDelete": "member", "manageUi": "member",
        "manageSettings": "owner", "manageMessages": "member", "manageMessagesAutoDelete": "manager",
        "manageGuestInvites": "manager", "manageDelete": "member", "canPost": "member"
      }
    },
    "user": {
      "id": "515",
      "active": "1",
      "name": "Гость",
      "firstName": "Гость",
      "lastName": "",
      "gender": "M",
      "birthday": "",
      "avatar": "",
      "color": "#3e99ce",
      "extranet": "1",
      "bot": "0",
      "connector": "1",
      "externalAuthId": "imconnector",
      "internalAccount": "0",
      "intranetUser": "0",
      "status": "online",
      "idle": "0",
      "lastActivityDate": "0",
      "mobileLastDate": "0",
      "desktopLastDate": "0",
      "absent": "0",
      "phones": "0",
      "type": "extranet",
      "website": "",
      "email": ""
    },
    "language": "ru"
  },
  "ts": "1789545901",
  "auth": {
    "access_token": "bd5baa6a…12c2",
    "expires": "1789549501",
    "expires_in": "3600",
    "scope": "imbot,imopenlines",
    "domain": "teplodar.bitrix24.ru",
    "server_endpoint": "https://oauth.bitrix24.tech/rest/",
    "status": "L",
    "client_endpoint": "https://teplodar.bitrix24.ru/rest/",
    "member_id": "61fe44d3770c22e3fab7bff06b17e7e3",
    "user_id": "515",
    "refresh_token": "addad16a…7550",
    "application_token": "c76f868e…cd7c"
  }
}
```
