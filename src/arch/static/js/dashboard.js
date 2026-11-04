$(document).ready(function () {

    // ============ ЭЛЕМЕНТЫ ============
    const $messages = $('#chatMessages');
    const $empty = $('#chatEmpty');
    const $input = $('#chatInput');
    const $form = $('#chatForm');
    const $sendBtn = $('#sendBtn');
    const $modelSelect = $('#modelSelect');

    // История диалога в формате OpenAI: [{role, content}, ...]
    let conversation = [];
    let isStreaming = false;
    let abortController = null;

    // ============ САЙДБАР ============
    $('#menuToggle').on('click', () => {
        $('#sidebar').toggleClass('open');
        $('#sidebarOverlay').toggleClass('active');
    });
    $('#sidebarOverlay').on('click', () => {
        $('#sidebar').removeClass('open');
        $('#sidebarOverlay').removeClass('active');
    });

    // ============ МОДАЛКА ПОПОЛНЕНИЯ ============
    function openTopup() { $('#topupModal').addClass('active'); }
    function closeTopup() { $('#topupModal').removeClass('active'); }

    $('#openTopupBtn, #openTopupBtn2').on('click', openTopup);
    $('#closeTopupBtn, #cancelTopup').on('click', closeTopup);
    $('#topupModal').on('click', function (e) {
        if (e.target === this) closeTopup();
    });

    // Пресеты суммы
    $('.preset').on('click', function () {
        $('.preset').removeClass('active');
        $(this).addClass('active');
        const val = $(this).data('amount');
        $('#topupAmount').val(val);
        $('#payAmountLabel').text(formatMoney(val) + ' ₽');
    });
    $('#topupAmount').on('input', function () {
        const val = +$(this).val() || 0;
        $('#payAmountLabel').text(formatMoney(val) + ' ₽');
        $('.preset').removeClass('active');
    });

    $('#topupForm').on('submit', function (e) {
        e.preventDefault();
        const amount = +$('#topupAmount').val() || 0;
        if (amount < 100) {
            toast('Минимальная сумма — 100 ₽', 'error');
            return;
        }
        // Здесь можно вызвать /api/topup и получить ссылку на оплату
        toast(`Запрос на пополнение на ${formatMoney(amount)} ₽ отправлен`, 'success');
        closeTopup();
    });

    // ============ ЧАТ: ОТПРАВКА ============
    $form.on('submit', function (e) {
        e.preventDefault();
        sendMessage();
    });

    // Enter — отправить, Shift+Enter — новая строка
    $input.on('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Автоувеличение высоты textarea
    $input.on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });

    // Быстрые промпты
    $(document).on('click', '.quick-prompt', function () {
        $input.val($(this).data('prompt'));
        $input.trigger('input');
        sendMessage();
    });

    // Очистить чат
    $('#clearChatBtn').on('click', function () {
        if (conversation.length === 0) return;
        if (!confirm('Очистить историю диалога?')) return;
        conversation = [];
        $messages.empty().append($empty);
        $empty.show();
    });

    // ============ ОСНОВНАЯ ФУНКЦИЯ ОТПРАВКИ ============
    async function sendMessage() {
        const text = $input.val().trim();
        if (!text || isStreaming) return;

        // Скрываем заглушку
        $empty.detach();

        // Добавляем сообщение пользователя
        appendMessage('user', text);
        conversation.push({ role: 'user', content: text });

        // Очищаем ввод
        $input.val('').trigger('input');
        $input.focus();

        // Плейсхолдер ответа ассистента
        const $assistant = appendMessage('assistant', '', true);
        const $content = $assistant.find('.msg-content');
        isStreaming = true;
        setSendEnabled(false);

        try {
            abortController = new AbortController();

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: $modelSelect.val(),
                    messages: conversation,
                }),
                signal: abortController.signal,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullText = '';
            let finished = false;

            while (!finished) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const payload = line.slice(6).trim();
                    if (payload === '[DONE]') { finished = true; break; }

                    try {
                        const json = JSON.parse(payload);
                        if (json.error) throw new Error(json.error);
                        if (json.delta) {
                            fullText += json.delta;
                            renderStreaming($content, fullText);
                            scrollToBottom();
                        }
                    } catch (err) {
                        if (err.message && !err.message.includes('Unexpected')) {
                            throw err;
                        }
                    }
                }
            }

            // Финализируем ответ
            finalizeMessage($content, fullText);
            conversation.push({ role: 'assistant', content: fullText });

        } catch (err) {
            if (err.name === 'AbortError') return;
            $assistant.addClass('msg-error');
            $content.html(`<i class="ri-error-warning-line"></i> ${escapeHtml(err.message)}`);
        } finally {
            isStreaming = false;
            abortController = null;
            setSendEnabled(true);
            $input.focus();
        }
    }

    // ============ РЕНДЕР СООБЩЕНИЙ ============
    function appendMessage(role, text, withCursor = false) {
        const isUser = role === 'user';
        const $msg = $(`
            <div class="msg msg-${role}">
                <div class="msg-avatar">
                    <i class="ri-${isUser ? 'user-3-line' : 'sparkling-2-line'}"></i>
                </div>
                <div class="msg-body">
                    <div class="msg-role">${isUser ? 'Вы' : 'Ассистент'}</div>
                    <div class="msg-content"></div>
                </div>
            </div>
        `);

        const $content = $msg.find('.msg-content');

        if (isUser) {
            $content.text(text);
        } else if (withCursor) {
            $content.html('<span class="typing-cursor"></span>');
        }

        $messages.append($msg);
        scrollToBottom();
        return $msg;
    }

    function renderStreaming($el, text) {
        // Во время стрима просто как текст (без markdown), чтобы не мигало
        $el.html(escapeHtml(text) + '<span class="typing-cursor"></span>');
    }

    function finalizeMessage($el, text) {
        // Финал — рендерим Markdown + подкрашиваем код
        const html = DOMPurify.sanitize(marked.parse(text || ''));
        $el.html(html);
        $el.find('pre code').each(function () {
            if (window.hljs) hljs.highlightElement(this);
        });
        // Внешние ссылки — в новой вкладке
        $el.find('a').attr('target', '_blank').attr('rel', 'noopener');
    }

    // ============ УТИЛИТЫ ============
    function scrollToBottom() {
        const el = $messages[0];
        el.scrollTop = el.scrollHeight;
    }

    function setSendEnabled(enabled) {
        $sendBtn.prop('disabled', !enabled);
        $input.prop('disabled', !enabled);
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatMoney(n) {
        return Number(n).toLocaleString('ru-RU');
    }

    function toast(msg, type = 'info') {
        const $t = $(`<div class="toast ${type}"></div>`).text(msg);
        $('#toastContainer').append($t);
        setTimeout(() => {
            $t.css({ opacity: 0, transform: 'translateX(20px)' });
            setTimeout(() => $t.remove(), 250);
        }, 3500);
    }

    // ============ НАСТРОЙКА MARKED ============
    if (window.marked) {
        marked.setOptions({ breaks: true, gfm: true });
    }

    // Фокус на input при загрузке
    $input.focus();
});
