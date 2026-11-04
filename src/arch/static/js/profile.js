$(function () {
    const $toast = $('#toastContainer');

    function toast(message, type) {
        const $item = $('<div class="toast"></div>').addClass(type || 'success').text(message);
        $toast.append($item);
        setTimeout(() => $item.fadeOut(200, () => $item.remove()), 3500);
    }

    async function request(url, options) {
        const response = await fetch(url, options);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `Ошибка ${response.status}`);
        return data;
    }

    async function loadProfile() {
        try {
            const profile = await request('/api/profile');
            $('#profileUsername').val(profile.username);
            $('#profileEmail').val(profile.email);
            $('#profileBalance').text(Number(profile.balance).toFixed(2) + ' ₽');
        } catch (error) {
            toast(error.message, 'error');
        }
    }

    $('#profileForm').on('submit', async function (event) {
        event.preventDefault();
        try {
            await request('/api/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: $('#profileUsername').val(),
                    email: $('#profileEmail').val(),
                    current_password: $('#profileCurrentPassword').val(),
                }),
            });
            $('#profileCurrentPassword').val('');
            toast('Данные профиля сохранены');
        } catch (error) {
            toast(error.message, 'error');
        }
    });

    $('#passwordForm').on('submit', async function (event) {
        event.preventDefault();
        if ($('#passwordNew').val() !== $('#passwordConfirm').val()) {
            toast('Новые пароли не совпадают', 'error');
            return;
        }
        try {
            await request('/api/profile/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    current_password: $('#passwordCurrent').val(),
                    new_password: $('#passwordNew').val(),
                }),
            });
            this.reset();
            toast('Пароль изменён');
        } catch (error) {
            toast(error.message, 'error');
        }
    });

    $('#topupProfileForm').on('submit', async function (event) {
        event.preventDefault();
        const amount = Number($('#profileTopupAmount').val());
        if (!Number.isFinite(amount) || amount <= 0) {
            toast('Введите сумму больше нуля', 'error');
            return;
        }
        try {
            const result = await request('/api/topup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount }),
            });
            $('#profileBalance').text(Number(result.balance).toFixed(2) + ' ₽');
            toast('Баланс пополнен');
        } catch (error) {
            toast(error.message, 'error');
        }
    });

    loadProfile();
});
